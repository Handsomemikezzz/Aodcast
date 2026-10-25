import asyncio
import io
import shutil
import subprocess
import threading
import time
from pathlib import Path

import httpx
import numpy as np
import pytest
import soundfile as sf

from speech_server.app import create_app
from speech_server.audio import WavSplicer, trim_silence
from speech_server.config import CLONE_MODELS, Settings
from speech_server.engine import CLONE_SAMPLE_RATE, ServiceError, SpeechEngine
from speech_server.text import split_paragraph, split_text


class FakeBackend:
    def __init__(self, settings):
        self.settings = settings
        self.models = {}
        self.calls = []
        self.thread_ids = set()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = False
        self.cleanups = 0

    def memory_guard(self):
        pass

    def load(self, model_id):
        if model_id not in self.models and self.settings.single_resident:
            self.models.clear()
        self.models[model_id] = True
        self.thread_ids.add(threading.get_ident())

    def tts(self, text, voice, seed):
        self.load(self.settings.tts_model)
        self.calls.append((text, voice, seed))
        self.entered.set()
        if self.block:
            assert self.release.wait(5)
        return np.sin(np.arange(2400, dtype=np.float32) * 0.05) * 0.5, 24000

    def clone(self, text, model_id, reference, reference_text, language, seed):
        self.load(model_id)
        self.calls.append((text, model_id, len(reference), reference_text, language, seed))
        return np.sin(np.arange(2400, dtype=np.float32) * 0.05) * 0.5, CLONE_SAMPLE_RATE

    def asr(self, audio, language):
        self.load(self.settings.asr_model)
        self.calls.append((len(audio), language))
        return "测试文字"

    def cleanup(self):
        self.cleanups += 1

    def unload(self):
        self.models.clear()

    def snapshot(self):
        return {
            "loaded": list(self.models),
            "metal_active_bytes": len(self.models) * 100,
            "metal_cache_bytes": 0,
            "metal_peak_bytes": 100,
        }


@pytest.fixture
def setup_engine():
    def make(**kwargs):
        settings = Settings(min_available_gb=0, **kwargs)
        backend = FakeBackend(settings)
        engine = SpeechEngine(settings, lambda _: backend)
        return settings, backend, engine

    return make


def wav_bytes(seconds=0.1):
    output = io.BytesIO()
    sf.write(
        output,
        np.sin(np.arange(int(16000 * seconds)) * 0.1) * 0.3,
        16000,
        format="WAV",
        subtype="PCM_16",
    )
    return output.getvalue()


@pytest.mark.parametrize("length", [1, 19, 79, 80, 120, 121, 159, 160, 239, 241, 1001, 20000])
def test_slices_preserve_text_and_bounds(length):
    text = ("这是一个用于验证文字不会丢失的测试句子，" * 2000)[:length]
    parts = split_paragraph(text)
    assert "".join(parts) == text
    assert all(0 < len(p) <= 120 for p in parts)
    if length >= 80 and length >= 80 * len(parts):
        assert min(map(len, parts)) >= 80


def test_short_sentence_merges_forward_and_prefers_punctuation():
    text = "甲" * 90 + "。" + "短句。" + "乙" * 85 + "，" + "丙" * 85 + "。"
    parts = split_paragraph(text)
    assert "".join(parts) == text
    assert parts[0].endswith("。")
    assert not any(p.endswith("短句。") for p in parts)
    assert all(len(p) <= 120 for p in parts)


def test_paragraph_flags_and_short_paragraph_merge():
    chunks = split_text("简短标题\n" + "甲" * 200 + "\n" + "乙" * 100)
    assert [c.paragraph_end for c in chunks] == [False, True, True]
    assert chunks[0].text.startswith("简短标题 ")
    assert not split_text(" \n\t")


def test_trim_and_crossfade_wav_duration(tmp_path):
    rate = 24000
    tone = np.full(rate, 0.4, dtype=np.float32)
    padded = np.pad(tone, (rate // 2, rate // 2))
    trimmed = trim_silence(padded, rate)
    assert rate <= len(trimmed) <= rate + int(rate * 0.05)
    path = tmp_path / "joined.wav"
    with WavSplicer(path, rate, 10, 300) as writer:
        writer.add(tone, False)
        writer.add(-tone, True)
        writer.add(tone, True)
    audio, sr = sf.read(path)
    # First join overlaps 10 ms; paragraph join retains 300 ms quiet.
    assert sr == rate
    assert len(audio) == 3 * rate - int(rate * 0.01) + int(rate * 0.3)
    assert abs(audio[0]) < 1e-4 and abs(audio[-1]) < 1e-4
    assert np.max(np.abs(np.diff(audio))) < 0.01
    assert np.count_nonzero(audio == 0) >= int(rate * 0.3)


@pytest.mark.parametrize("audio", [np.zeros(10), np.array([float("nan")]), np.array([])])
def test_invalid_generated_audio_rejected(audio):
    with pytest.raises(RuntimeError):
        trim_silence(audio, 24000)


async def test_1000_char_synthesis_is_serial_and_uses_fixed_voice_seed(setup_engine):
    _, backend, engine = setup_engine()
    text = "这是超过一千字的中文语音合成测试，验证切片串行执行并保持固定音色。" * 40
    try:
        path, count = await engine.run("tts", text, "Vivian", 42)
        assert count == len(backend.calls) > 8
        assert all(len(c[0]) <= 120 and c[1:] == ("Vivian", 42) for c in backend.calls)
        assert len(backend.thread_ids) == 1
        assert backend.cleanups >= count
        assert sf.info(path).frames > 0
        Path(path).unlink()
    finally:
        await engine.close()


async def test_cancellation_keeps_gpu_locked_until_thread_returns(setup_engine):
    _, backend, engine = setup_engine()
    backend.block = True
    first = asyncio.create_task(engine.run("tts", "第一段文字", "Vivian", 42))
    try:
        for _ in range(100):
            if backend.entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert backend.entered.is_set()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(engine.run("tts", "第二段文字", "Vivian", 42))
        await asyncio.sleep(0.05)
        assert engine.busy
        assert engine.gpu_lock.locked()
        assert len(backend.calls) == 1
        backend.block = False
        backend.release.set()
        path, _ = await second
        Path(path).unlink()
        assert len(backend.calls) == 2
    finally:
        backend.release.set()
        await engine.close()


async def test_queue_timeout_deletes_abandoned_asr_upload(setup_engine, tmp_path):
    _, _, engine = setup_engine(queue_timeout=0.01)
    upload = tmp_path / "pending.wav"
    upload.write_bytes(wav_bytes())
    await engine.gpu_semaphore.acquire()
    try:
        with pytest.raises(ServiceError, match="timed out"):
            await engine.run("asr", upload, None)
        assert not upload.exists()
    finally:
        engine.gpu_semaphore.release()
        await engine.close()


async def test_cancelled_queue_deletes_upload_without_entering_worker(setup_engine, tmp_path):
    _, backend, engine = setup_engine()
    upload = tmp_path / "pending.wav"
    upload.write_bytes(wav_bytes())
    await engine.gpu_semaphore.acquire()
    job = asyncio.create_task(engine.run("asr", upload, None))
    try:
        await asyncio.sleep(0.01)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert not upload.exists()
        assert not backend.calls
    finally:
        engine.gpu_semaphore.release()
        await engine.close()


async def test_stale_idle_unload_does_not_evict_recent_request(setup_engine):
    _, _, engine = setup_engine(idle_seconds=1)
    try:
        path, _ = await engine.run("tts", "你好", "Vivian", 42)
        Path(path).unlink()
        await engine.run("idle_unload")
        assert engine.health()["models"]["tts"]["loaded"]
    finally:
        await engine.close()


async def test_idle_unload_then_lazy_reload(setup_engine):
    _, backend, engine = setup_engine(idle_seconds=0.05)
    await engine.start()
    try:
        path, _ = await engine.run("tts", "你好", "Vivian", 42)
        Path(path).unlink()
        assert engine.health()["models"]["tts"]["loaded"]
        for _ in range(30):
            await asyncio.sleep(0.02)
            if not engine.health()["models"]["tts"]["loaded"]:
                break
        assert not backend.models
        assert not engine.health()["models"]["tts"]["loaded"]
        path, _ = await engine.run("tts", "再次请求", "Vivian", 42)
        Path(path).unlink()
        assert engine.health()["models"]["tts"]["loaded"]
    finally:
        await engine.close()


async def test_api_health_wav_and_validation(setup_engine):
    settings, backend, engine = setup_engine(max_chars=120)
    app = create_app(settings, engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            health = await client.get("/health")
            assert not health.json()["models"]["tts"]["loaded"]
            response = await client.post("/v1/audio/speech", json={"input": "你好"})
            assert response.status_code == 200
            assert response.content[:4] == b"RIFF"
            assert response.headers["content-type"] == "audio/wav"
            assert backend.calls[0][1] == "Vivian"
            for payload, code in [
                ({"input": " "}, 400),
                ({"input": "甲" * 121}, 413),
                ({"input": "你好", "response_format": "mp3"}, 400),
                ({"input": "你好", "speed": 2}, 400),
            ]:
                response = await client.post("/v1/audio/speech", json=payload)
                assert response.status_code == code


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is not installed")
@pytest.mark.parametrize("extension", ["wav", "mp3", "m4a"])
async def test_real_ffmpeg_decode_and_bounded_asr(setup_engine, tmp_path, extension):
    settings, backend, engine = setup_engine(asr_chunk_seconds=1)
    source = tmp_path / "input.wav"
    source.write_bytes(wav_bytes(2.2))
    if extension == "wav":
        upload = source
    else:
        upload = tmp_path / f"input.{extension}"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), str(upload)], check=True)
    app = create_app(settings, engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/audio/transcriptions",
                files={"file": (upload.name, upload.read_bytes())},
                data={"model": "whisper-1", "language": "zh"},
            )
            assert response.status_code == 200, response.text
            assert "测试文字" in response.json()["text"]
            assert len(backend.calls) >= 3
            assert all(length <= 16000 and lang == "Chinese" for length, lang in backend.calls)
            assert engine.health()["models"]["asr"]["loaded"]


async def test_raw_chunked_body_limit_before_parser(setup_engine):
    settings, _, engine = setup_engine(max_chars=120)
    app = create_app(settings, engine)

    async def body():
        for _ in range(20):
            yield b"x" * 1024

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            result = await client.post("/v1/audio/speech", content=body())
            assert result.status_code == 413


async def test_health_stays_responsive_during_native_work(setup_engine):
    settings, backend, engine = setup_engine()
    backend.block = True
    app = create_app(settings, engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            job = asyncio.create_task(client.post("/v1/audio/speech", json={"input": "你好"}))
            try:
                for _ in range(100):
                    if backend.entered.is_set():
                        break
                    await asyncio.sleep(0.01)
                start = time.monotonic()
                response = await client.get("/health")
                assert response.status_code == 200 and response.json()["busy"]
                assert time.monotonic() - start < 0.5
            finally:
                backend.release.set()
                await job


async def test_admission_returns_429_while_request_running(setup_engine):
    settings, backend, engine = setup_engine(max_pending=1)
    backend.block = True
    app = create_app(settings, engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            job = asyncio.create_task(client.post("/v1/audio/speech", json={"input": "你好"}))
            try:
                for _ in range(100):
                    if backend.entered.is_set():
                        break
                    await asyncio.sleep(0.01)
                response = await client.post("/v1/audio/speech", json={"input": "第二个请求"})
                assert response.status_code == 429
                assert (await client.get("/health")).status_code == 200
            finally:
                backend.release.set()
                await job


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is not installed")
async def test_decoded_audio_duration_is_capped(setup_engine, tmp_path):
    _, backend, engine = setup_engine(max_audio_seconds=1)
    source = tmp_path / "long.wav"
    source.write_bytes(wav_bytes(2))
    try:
        with pytest.raises(ServiceError, match="MAX_AUDIO_SECONDS"):
            await engine.run("asr", source, None)
        assert not source.exists()
        assert not backend.calls
    finally:
        await engine.close()


def tone_wav(seconds, rate=48000, lead_silence=0.0):
    output = io.BytesIO()
    audio = np.concatenate(
        (
            np.zeros(int(rate * lead_silence), dtype=np.float32),
            np.sin(np.arange(int(rate * seconds)) * 0.05).astype(np.float32) * 0.3,
        )
    )
    sf.write(output, audio, rate, format="WAV", subtype="PCM_16")
    return output.getvalue()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is not installed")
async def test_clone_api_conditions_every_slice_on_trimmed_reference(setup_engine):
    settings, backend, engine = setup_engine()
    app = create_app(settings, engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            health = (await client.get("/health")).json()
            assert [m["id"] for m in health["models"]["clone"]] == list(CLONE_MODELS)
            assert health["clone_reference"] == {"min_seconds": 3, "max_seconds": 30}
            text = "这是一段用于验证声音克隆切片的较长中文文本，每一片都要带上同一份参考声音。" * 6
            response = await client.post(
                "/v1/audio/speech/clone",
                files={"reference": ("friend.wav", tone_wav(4, lead_silence=1))},
                data={
                    "input": text,
                    "reference_text": " 你好，这是我的声音。 ",
                    "model": CLONE_MODELS[1],
                    "language": "zh",
                },
            )
            assert response.status_code == 200, response.text
            assert response.content[:4] == b"RIFF"
            assert int(response.headers["x-tts-chunks"]) == len(backend.calls) > 1
            for _, model, samples, ref_text, language, seed in backend.calls:
                assert model == CLONE_MODELS[1]
                # 48 kHz upload is decoded to 24 kHz and its leading silence trimmed.
                assert abs(samples - 4 * CLONE_SAMPLE_RATE) < CLONE_SAMPLE_RATE * 0.1
                assert (ref_text, language, seed) == ("你好，这是我的声音。", "Chinese", 42)
            assert engine.health()["models"]["clone"][1]["loaded"]
            assert not engine.health()["models"]["tts"]["loaded"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is not installed")
async def test_clone_defaults_to_small_model_and_preset_route_still_works(setup_engine):
    settings, backend, engine = setup_engine()
    app = create_app(settings, engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/audio/speech/clone",
                files={"reference": ("friend.wav", tone_wav(5))},
                data={"input": "你好", "reference_text": "参考文本"},
            )
            assert response.status_code == 200, response.text
            assert backend.calls[-1][1] == CLONE_MODELS[0]
            assert backend.calls[-1][4] == "auto"
            response = await client.post("/v1/audio/speech", json={"input": "你好"})
            assert response.status_code == 200
            # Single-resident mode swaps the clone model out for the preset model.
            loaded = engine.health()["models"]
            assert loaded["tts"]["loaded"] and not any(m["loaded"] for m in loaded["clone"])


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is not installed")
@pytest.mark.parametrize(
    ("seconds", "data", "code", "message"),
    [
        (1.5, {}, 422, "needs 3-30s"),
        (31, {}, 422, "needs 3-30s"),
        (5, {"reference_text": " "}, 400, "exact transcript"),
        (5, {"model": "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"}, 400, "clone model"),
        (5, {"response_format": "mp3"}, 400, "response_format"),
    ],
)
async def test_clone_rejects_unusable_requests(setup_engine, seconds, data, code, message):
    settings, backend, engine = setup_engine()
    app = create_app(settings, engine)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/audio/speech/clone",
                files={"reference": ("friend.wav", tone_wav(seconds))},
                data={"input": "你好", "reference_text": "参考文本", **data},
            )
            assert response.status_code == code
            assert message in response.json()["error"]["message"]
            assert not backend.calls


async def test_cancelled_clone_queue_deletes_reference_upload(setup_engine, tmp_path):
    _, backend, engine = setup_engine()
    upload = tmp_path / "reference.wav"
    upload.write_bytes(tone_wav(4))
    await engine.gpu_semaphore.acquire()
    job = asyncio.create_task(
        engine.run("clone", "你好", CLONE_MODELS[0], upload, "参考文本", "auto", 42)
    )
    try:
        await asyncio.sleep(0.01)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert not upload.exists()
        assert not backend.calls
    finally:
        engine.gpu_semaphore.release()
        await engine.close()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is not installed")
async def test_repeated_reference_is_decoded_once(setup_engine, tmp_path, monkeypatch):
    _, backend, engine = setup_engine()
    decodes = []
    original = SpeechEngine._decode

    def counting(self, source, rate, folder):
        decodes.append(source)
        return original(self, source, rate, folder)

    monkeypatch.setattr(SpeechEngine, "_decode", counting)
    try:
        for index in range(3):
            upload = tmp_path / f"segment-{index}.wav"
            upload.write_bytes(tone_wav(4))
            args = ("你好", CLONE_MODELS[0], upload, "参考文本", "auto", 42)
            path, _ = await engine.run("clone", *args)
            Path(path).unlink()
            assert not upload.exists()
        assert len(decodes) == 1 and len(backend.calls) == 3
        other = tmp_path / "other.wav"
        other.write_bytes(tone_wav(5))
        path, _ = await engine.run("clone", "你好", CLONE_MODELS[0], other, "参考文本", "auto", 42)
        Path(path).unlink()
        assert len(decodes) == 2
    finally:
        await engine.close()
