from __future__ import annotations

import asyncio
import io
import json
import tempfile
import time
import unittest
import unittest.mock
import wave
from pathlib import Path

import httpx

from app.domain.tts_config import DEFAULT_LOCAL_CLONE_MODEL, KOKORO_TTS_MODEL, LOCAL_CLONE_MODELS, TTSProviderConfig
from tests.audio_utils import synthesize_sine_wave_bytes
from app.providers.local_speech.capabilities import (
    capability_contract_for_model,
    detect_local_speech_capability,
)
from app.providers.local_speech.client import LocalSpeechClient, LocalSpeechError
from app.providers.local_speech.provider import LocalSpeechTTSProvider
from app.providers.tts_api.base import TTSGenerationRequest
from app.runtime.task_cancellation import TaskCancellationRequested


class LocalSpeechTests(unittest.TestCase):
    def test_long_text_is_one_http_request_with_correct_payload_and_timeout(self):
        requests = []
        audio = synthesize_sine_wave_bytes(1)
        text = "这是不会在业务端切片的长篇中文播客文稿。" * 80

        def handler(request):
            requests.append(request)
            return httpx.Response(200, content=audio)

        client = LocalSpeechClient(transport=httpx.MockTransport(handler))
        result = client.synthesize(text, "Vivian")
        self.assertEqual(result, audio)
        self.assertEqual(len(requests), 1)
        self.assertEqual(str(requests[0].url), "http://127.0.0.1:8090/v1/audio/speech")
        self.assertEqual(
            json.loads(requests[0].content),
            {
                "input": text,
                "voice": "Vivian",
                "model": "tts-1",
                "response_format": "wav",
            },
        )
        self.assertEqual(requests[0].extensions["timeout"]["read"], 1800)

    def test_transcription_upload_and_text_contract(self):
        def handler(request):
            self.assertEqual(request.url.path, "/v1/audio/transcriptions")
            self.assertIn(b'filename="sample.wav"', request.content)
            self.assertIn(b"whisper-1", request.content)
            return httpx.Response(200, json={"text": "真实的问题"})

        client = LocalSpeechClient(transport=httpx.MockTransport(handler))
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "sample.wav"
            source.write_bytes(synthesize_sine_wave_bytes(1))
            self.assertEqual(client.transcribe(source, "zh"), "真实的问题")

    def test_service_down_message_is_actionable(self):
        def handler(request):
            raise httpx.ConnectError("connection refused", request=request)

        client = LocalSpeechClient(transport=httpx.MockTransport(handler))
        with self.assertRaisesRegex(LocalSpeechError, r"service.sh start"):
            client.synthesize("你好")

    def test_connect_timeout_message_distinguishes_tcp_handshake(self):
        def handler(request):
            raise httpx.ConnectTimeout("connection timed out", request=request)

        client = LocalSpeechClient(transport=httpx.MockTransport(handler))
        self.assertEqual(client.timeout.connect, 30)
        self.assertEqual(client.timeout.pool, 30)
        with self.assertRaisesRegex(LocalSpeechError, r"timed out during TCP handshake"):
            client.synthesize("你好")

    def test_read_timeout_distinguishes_health_and_speech_endpoints(self):
        def health_handler(request):
            self.assertEqual(request.extensions["timeout"]["read"], 30)
            raise httpx.ReadTimeout("read timed out", request=request)

        client = LocalSpeechClient(transport=httpx.MockTransport(health_handler))
        with self.assertRaisesRegex(LocalSpeechError, r"Health check probe timed out"):
            client.health()

        def speech_handler(request):
            raise httpx.ReadTimeout("read timed out", request=request)

        client = LocalSpeechClient(transport=httpx.MockTransport(speech_handler))
        with self.assertRaisesRegex(LocalSpeechError, r"Speech synthesis timed out"):
            client.synthesize("你好")

        def transcription_handler(request):
            raise httpx.ReadTimeout("read timed out", request=request)

        client = LocalSpeechClient(transport=httpx.MockTransport(transcription_handler))
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "sample.wav"
            source.write_bytes(synthesize_sine_wave_bytes(1))
            with self.assertRaisesRegex(LocalSpeechError, r"Speech transcription timed out"):
                client.transcribe(source)

    def test_invalid_audio_and_server_errors_are_not_success(self):
        for response in [
            httpx.Response(200, content=b"invalid"),
            httpx.Response(503, json={"error": {"message": "memory too low"}}),
        ]:
            client = LocalSpeechClient(
                transport=httpx.MockTransport(lambda _, response=response: response)
            )
            with self.assertRaises(LocalSpeechError):
                client.synthesize("你好")

    def test_cancellation_closes_pending_http_request(self):
        cancelled = []

        async def handler(request):
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise
            return httpx.Response(200)

        start = time.monotonic()
        client = LocalSpeechClient(transport=httpx.MockTransport(handler))
        with self.assertRaises(TaskCancellationRequested):
            client.synthesize("你好", should_cancel=lambda: time.monotonic() - start > 0.05)
        self.assertTrue(cancelled)
        self.assertLess(time.monotonic() - start, 1)

    def test_provider_preserves_response_and_maps_business_voice(self):
        audio = synthesize_sine_wave_bytes(1)
        received = []

        def handler(request):
            if request.method == "GET":
                return httpx.Response(
                    200, json={"models": {"tts": {"id": TTSProviderConfig().model}}}
                )
            received.append(json.loads(request.content))
            return httpx.Response(200, content=audio)

        provider = LocalSpeechTTSProvider(TTSProviderConfig())
        provider.client = LocalSpeechClient(transport=httpx.MockTransport(handler))
        response = provider.synthesize(
            TTSGenerationRequest("session", "你好", "warm_narrator", "wav")
        )
        self.assertEqual(received[0]["voice"], "Vivian")
        self.assertEqual(response.provider_name, "local_http")
        self.assertEqual(response.file_extension, "wav")
        with wave.open(io.BytesIO(response.audio_bytes)) as wav:
            self.assertEqual(response.sample_rate_hz, wav.getframerate())
            self.assertEqual(response.channels, wav.getnchannels())

    def test_provider_rejects_unsupported_features_explicitly(self):
        provider = LocalSpeechTTSProvider(TTSProviderConfig())
        for options in [
            {"speed": 1.1},
            {"style_prompt": "happy"},
            {"reference_audio_path": "/tmp/reference.wav"},
            {"context_audio_path": "/tmp/previous.wav"},
        ]:
            with self.assertRaises(ValueError):
                provider.synthesize(TTSGenerationRequest("s", "你好", "Vivian", "wav", **options))
        with self.assertRaisesRegex(ValueError, "preset voices only; choose a Qwen3 Base model"):
            provider.synthesize(
                TTSGenerationRequest("s", "你好", "Vivian", "wav", reference_audio_path="/tmp/r.wav", reference_text="参考")
            )

    def test_clone_model_uploads_reference_and_reports_requested_model(self):
        audio = synthesize_sine_wave_bytes(1)
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, content=audio)

        with tempfile.TemporaryDirectory() as folder:
            reference = Path(folder) / "friend.wav"
            reference.write_bytes(synthesize_sine_wave_bytes(4, frequency=220.0))
            for model in LOCAL_CLONE_MODELS:
                provider = LocalSpeechTTSProvider(TTSProviderConfig(model=model))
                provider.client = LocalSpeechClient(transport=httpx.MockTransport(handler))
                result = provider.synthesize(
                    TTSGenerationRequest(
                        "s",
                        "这是需要克隆朋友声音的一整段文稿。",
                        "warm_narrator",
                        "wav",
                        language="zh",
                        reference_audio_path=str(reference),
                        reference_text="你好，这是我的声音。",
                    )
                )
                self.assertEqual(result.model_name, model)
                self.assertEqual(result.adapter_version, "local-http-clone-v1")
                body = requests[-1].content
                self.assertEqual(requests[-1].url.path, "/v1/audio/speech/clone")
                self.assertIn(b'name="reference"; filename="friend.wav"', body)
                self.assertIn(reference.read_bytes(), body)
                self.assertIn("你好，这是我的声音。".encode(), body)
                self.assertIn(model.encode(), body)
                self.assertIn(b'name="language"\r\n\r\nzh', body)
        # No health probe: the clone model is chosen per request, not by service config.
        self.assertEqual([r.method for r in requests], ["POST", "POST"])

    def test_clone_model_requires_a_speaker_reference(self):
        provider = LocalSpeechTTSProvider(TTSProviderConfig(model=DEFAULT_LOCAL_CLONE_MODEL))
        with self.assertRaisesRegex(ValueError, "Select a Speaker Reference"):
            provider.synthesize(TTSGenerationRequest("s", "你好", "Vivian", "wav"))
        with self.assertRaisesRegex(ValueError, "preceding audio"):
            provider.synthesize(
                TTSGenerationRequest(
                    "s", "你好", "Vivian", "wav",
                    reference_audio_path="/tmp/r.wav", reference_text="参考", context_audio_path="/tmp/p.wav",
                )
            )

    def test_capability_reads_clone_models_and_reference_limits_from_health(self):
        def handler(request):
            return httpx.Response(
                200,
                json={
                    "models": {
                        "tts": {"id": TTSProviderConfig().model, "loaded": False},
                        "clone": [{"id": model, "loaded": False} for model in LOCAL_CLONE_MODELS],
                    },
                    "clone_reference": {"min_seconds": 3, "max_seconds": 30},
                },
            )

        transport = httpx.MockTransport(handler)
        original = LocalSpeechClient.__init__

        def patched(client, base_url="", **kwargs):
            original(client, base_url or "http://127.0.0.1:8090", transport=transport)

        with unittest.mock.patch.object(LocalSpeechClient, "__init__", patched):
            capability = detect_local_speech_capability(TTSProviderConfig()).to_dict()
        self.assertEqual(capability["clone_models"], list(LOCAL_CLONE_MODELS))
        self.assertEqual(capability["min_reference_duration_ms"], 3000)
        self.assertEqual(capability["max_reference_duration_ms"], 30000)

    def test_service_model_switch_updates_voice_mapping_and_response_metadata(self):
        received = []

        def handler(request):
            if request.method == "GET":
                return httpx.Response(200, json={"models": {"tts": {"id": KOKORO_TTS_MODEL}}})
            received.append(json.loads(request.content))
            return httpx.Response(200, content=synthesize_sine_wave_bytes(1))

        provider = LocalSpeechTTSProvider(TTSProviderConfig())
        provider.client = LocalSpeechClient(transport=httpx.MockTransport(handler))
        result = provider.synthesize(TTSGenerationRequest("s", "你好", "warm_narrator", "wav"))
        self.assertEqual(received[0]["model"], KOKORO_TTS_MODEL)
        self.assertEqual(received[0]["voice"], "zf_xiaobei")
        self.assertEqual(result.model_name, KOKORO_TTS_MODEL)

    def test_config_has_no_local_weight_fields_and_capabilities_are_truthful(self):
        config = TTSProviderConfig()
        self.assertEqual(
            set(config.to_dict()),
            {"provider", "model", "base_url", "api_key", "voice", "audio_format"},
        )
        contract = capability_contract_for_model(config.model).to_dict()
        self.assertEqual(contract["capabilities"]["speaker_cloning"], "unsupported")
        self.assertEqual(contract["capabilities"]["explicit_breaks"], "approximated")
        self.assertGreaterEqual(contract["limits"]["max_segment_characters"], 1000)


if __name__ == "__main__":
    unittest.main()
