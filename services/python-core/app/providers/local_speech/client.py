from __future__ import annotations

import asyncio
import io
import wave
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx

from app.domain.tts_config import DEFAULT_SPEECH_URL
from app.runtime.task_cancellation import TaskCancellationRequested


class LocalSpeechError(RuntimeError):
    """An actionable service error without local model implementation details."""


class LocalSpeechClient:
    def __init__(
        self,
        base_url: str = DEFAULT_SPEECH_URL,
        *,
        read_timeout: float = 1800,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if not self.base_url.endswith("/v1"):
            self.base_url += "/v1"
        if read_timeout < 180:
            raise ValueError("Local speech read_timeout must be at least 180 seconds.")
        self.timeout = httpx.Timeout(connect=5, read=read_timeout, write=180, pool=5)
        self.transport = transport

    def _request(
        self,
        method: str,
        url: str,
        *,
        should_cancel: Callable[[], bool] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        async def perform() -> httpx.Response:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self.transport, trust_env=False
            ) as client:
                job = asyncio.create_task(client.request(method, url, **kwargs))
                try:
                    while not job.done():
                        if should_cancel and should_cancel():
                            raise TaskCancellationRequested("Local speech request cancelled.")
                        await asyncio.wait({job}, timeout=0.2)
                    return await job
                finally:
                    if not job.done():
                        job.cancel()
                        with suppress(asyncio.CancelledError):
                            await job

        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                response = asyncio.run(perform())
            else:
                # Preserve the synchronous provider contract for callers that
                # already own an event loop; network work owns its own loop.
                with ThreadPoolExecutor(max_workers=1) as executor:
                    response = executor.submit(lambda: asyncio.run(perform())).result()
        except httpx.ConnectError as exc:
            raise LocalSpeechError(
                f"Cannot reach the local speech service at {self.base_url}. From the Aodcast repository root, run "
                "./speech-service/service.sh start, then try again."
            ) from exc
        except httpx.TimeoutException as exc:
            raise LocalSpeechError(
                "The local speech service timed out. The first request may still be downloading the model; check the service logs and GPU queue."
            ) from exc
        except httpx.HTTPError as exc:
            raise LocalSpeechError(f"Lost connection to the local speech service: {exc}") from exc
        if response.is_error:
            try:
                message = response.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                message = response.text[:300]
            raise LocalSpeechError(f"The local speech service returned HTTP {response.status_code}: {message}")
        return response

    def health(self) -> dict[str, Any]:
        response = self._request("GET", self.base_url.removesuffix("/v1") + "/health", timeout=5)
        payload = response.json()
        if not isinstance(payload, dict) or "models" not in payload:
            raise LocalSpeechError("The local speech service returned an invalid health status.")
        return payload

    def synthesize(
        self,
        text: str,
        voice: str = "默认中文音色",
        *,
        model: str = "tts-1",
        should_cancel: Callable[[], bool] | None = None,
    ) -> bytes:
        if not text.strip():
            raise ValueError("Speech input cannot be empty.")
        response = self._request(
            "POST",
            self.base_url + "/audio/speech",
            should_cancel=should_cancel,
            json={
                "input": text,
                "voice": voice,
                "model": model,
                "response_format": "wav",
            },
        )
        audio = response.content
        try:
            with wave.open(io.BytesIO(audio), "rb") as wav:
                if wav.getnframes() == 0 or wav.getsampwidth() != 2:
                    raise ValueError("Expected non-empty PCM16 WAV audio.")
        except (wave.Error, EOFError) as exc:
            raise LocalSpeechError("The local speech service did not return valid WAV audio.") from exc
        return audio

    def transcribe(self, path: str | Path, language: str | None = None) -> str:
        source = Path(path)
        data = {"model": "whisper-1", "response_format": "json"}
        if language:
            data["language"] = language
        with source.open("rb") as audio:
            response = self._request(
                "POST",
                self.base_url + "/audio/transcriptions",
                files={"file": (source.name, audio)},
                data=data,
            )
        result = response.json()
        if not isinstance(result, dict) or not isinstance(result.get("text"), str):
            raise LocalSpeechError("The local speech service did not return a valid transcription.")
        return result["text"]
