import asyncio
import logging
import tempfile
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .engine import ServiceError, SpeechEngine

log = logging.getLogger(__name__)


def error_response(status: int, message: str):
    return JSONResponse(
        {
            "error": {
                "message": message,
                "type": "invalid_request_error" if status < 500 else "server_error",
                "code": status,
            }
        },
        status_code=status,
        headers={"Retry-After": "5"} if status in (429, 503) else None,
    )


class TemporaryWavResponse(FileResponse):
    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            Path(self.path).unlink(missing_ok=True)


class BoundedRequests:
    """Bound admission AND raw bodies before JSON/multipart parsing.

    Buffer uploads on disk; never read an unbounded request into Python RAM.
    This also covers chunked HTTP uploads with no Content-Length header.
    """

    def __init__(self, app, engine: SpeechEngine, settings: Settings):
        self.app = app
        self.engine = engine
        self.settings = settings
        self.inflight = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        self.engine.touch()  # Includes /health: polling intentionally resets idle timeout.
        if scope["path"] not in ("/v1/audio/speech", "/v1/audio/transcriptions"):
            return await self.app(scope, receive, send)
        if self.inflight >= self.settings.max_pending:
            return await error_response(429, "Too many pending requests")(scope, receive, send)
        limit = (
            self.settings.max_chars * 12 + 4096
            if scope["path"].endswith("speech")
            else self.settings.max_upload_bytes + 65536
        )
        headers = dict(scope["headers"])
        if b"content-length" in headers:
            try:
                length = int(headers[b"content-length"])
            except ValueError:
                return await error_response(400, "Invalid Content-Length")(scope, receive, send)
            if length < 0 or length > limit:
                return await error_response(413, "Request body exceeds size limit")(
                    scope, receive, send
                )
        self.inflight += 1
        try:
            with tempfile.SpooledTemporaryFile(max_size=1024**2) as body:
                total = 0
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    data = message.get("body", b"")
                    total += len(data)
                    if total > limit:
                        return await error_response(413, "Request body exceeds size limit")(
                            scope, receive, send
                        )
                    await run_in_threadpool(body.write, data)
                    if not message.get("more_body", False):
                        break
                await run_in_threadpool(body.seek, 0)
                delivered = 0

                async def replay():
                    nonlocal delivered
                    if delivered >= total:
                        # First empty body is still an HTTP request event.
                        if delivered == total:
                            delivered += 1
                            return {"type": "http.request", "body": b"", "more_body": False}
                        return await receive()
                    chunk = await run_in_threadpool(body.read, 65536)
                    delivered += len(chunk)
                    if delivered == total:
                        delivered += 1
                    return {"type": "http.request", "body": chunk, "more_body": delivered < total}

                await self.app(scope, replay, send)
        finally:
            self.inflight -= 1


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: str = Field(min_length=1)
    model: str | None = None
    voice: str = Field(default="默认中文音色", min_length=1, max_length=80)
    response_format: Literal["wav"] = "wav"
    seed: int | None = Field(default=None, ge=0, lt=2**32)
    speed: Literal[1.0] = 1.0


async def run_until_disconnect(request: Request, engine: SpeechEngine, operation: str, *args):
    job = asyncio.create_task(engine.run(operation, *args))

    async def watch():
        while not job.done():
            await asyncio.sleep(0.5)
            if await request.is_disconnected():
                job.cancel()
                return

    watcher = asyncio.create_task(watch())
    try:
        return await job
    finally:
        watcher.cancel()
        with suppress(asyncio.CancelledError):
            await watcher


def create_app(settings: Settings | None = None, engine: SpeechEngine | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = engine or SpeechEngine(settings)

    @asynccontextmanager
    async def lifespan(_):
        await engine.start()
        yield
        await engine.close()

    app = FastAPI(title="Local MLX Speech", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.add_middleware(BoundedRequests, engine=engine, settings=settings)

    @app.exception_handler(ServiceError)
    async def service_error(_, exc):
        return error_response(exc.status, str(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc):
        # Do not include the entire input text or upload in validation messages.
        errors = [
            {"field": ".".join(str(v) for v in e["loc"]), "message": e["msg"]} for e in exc.errors()
        ]
        return error_response(400, str(errors))

    @app.exception_handler(Exception)
    async def unexpected_error(_, exc):
        log.error("Speech request failed", exc_info=exc)
        if isinstance(exc, MemoryError) or "out of memory" in str(exc).lower():
            return error_response(503, "Memory limit reached; free system memory and retry")
        return error_response(500, "Speech processing failed; see service logs")

    @app.get("/health")
    async def health():
        return engine.health()

    @app.post("/v1/audio/speech")
    async def speech(body: SpeechRequest, request: Request):
        if len(body.input) > settings.max_chars:
            raise ServiceError(413, f"input exceeds MAX_TEXT_CHARS={settings.max_chars}")
        if not body.input.strip():
            raise ServiceError(400, "input must contain non-whitespace text")
        if body.model not in (None, "tts-1", "tts-1-hd", settings.tts_model):
            raise ServiceError(400, "Unknown model; use tts-1 or the configured TTS model ID")
        voice = settings.voice if body.voice in ("默认中文音色", "default") else body.voice
        if not voice.replace("_", "").isalnum() or not voice.isascii():
            raise ServiceError(400, "Use a preset voice ID such as Vivian or zf_xiaobei")
        path, chunks = await run_until_disconnect(
            request,
            engine,
            "tts",
            body.input,
            voice,
            settings.seed if body.seed is None else body.seed,
        )
        return TemporaryWavResponse(
            path,
            media_type="audio/wav",
            filename="speech.wav",
            headers={"X-TTS-Chunks": str(chunks)},
        )

    @app.post("/v1/audio/transcriptions")
    async def transcriptions(
        request: Request,
        file: Annotated[UploadFile, File()],
        model: Annotated[str, Form()] = "whisper-1",
        language: Annotated[str | None, Form(max_length=40)] = None,
        response_format: Annotated[Literal["json", "text"], Form()] = "json",
    ):
        # 'whisper-1' is a routing alias; the actual model is always Qwen3-ASR.
        if model not in ("whisper-1", settings.asr_model):
            raise ServiceError(400, "Unknown model; use whisper-1 or the configured ASR model ID")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in (".wav", ".mp3", ".m4a"):
            raise ServiceError(400, "Supported filename extensions: wav, mp3, m4a")
        # Qwen expects language names; map common OpenAI ISO language codes.
        languages = {
            "zh": "Chinese",
            "en": "English",
            "ja": "Japanese",
            "ko": "Korean",
            "de": "German",
            "fr": "French",
            "es": "Spanish",
            "ru": "Russian",
        }
        language = languages.get(language, language) if language else None
        name = None
        handed_off = False
        try:
            with tempfile.NamedTemporaryFile(
                prefix="local-upload-", suffix=suffix, delete=False
            ) as out:
                name = Path(out.name)
                size = 0
                while chunk := await file.read(65536):
                    size += len(chunk)
                    if size > settings.max_upload_bytes:
                        raise ServiceError(413, "Upload exceeds MAX_UPLOAD_MB")
                    await run_in_threadpool(out.write, chunk)
            if not size:
                raise ServiceError(400, "Uploaded file is empty")
            handed_off = True  # Engine owns deletion even if queued work is cancelled.
            text = await run_until_disconnect(request, engine, "asr", name, language)
        finally:
            await file.close()
            if name and not handed_off:
                name.unlink(missing_ok=True)
        return PlainTextResponse(text) if response_format == "text" else {"text": text}

    return app
