# Import config first: .env must be read before MLX/Hugging Face imports.
import logging
import os

from .config import Settings


def main():
    import platform
    import shutil

    import uvicorn

    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("This service requires native Apple Silicon macOS Python (arm64).")
    if not shutil.which("ffmpeg"):
        raise SystemExit("FFmpeg is required: brew install ffmpeg")
    Settings()  # Fail fast on invalid configuration, without downloading any model.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    uvicorn.run(
        "speech_server.app:create_app",
        factory=True,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8090")),
        workers=1,
        timeout_keep_alive=5,
        log_level="info",
    )


if __name__ == "__main__":
    main()
