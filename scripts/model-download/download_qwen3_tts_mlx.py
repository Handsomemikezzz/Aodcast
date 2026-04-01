#!/usr/bin/env python3
"""Download mlx-community Qwen3-TTS weights from Hugging Face (standalone).

This script is not imported by Aodcast. After download, point TTS
``local_model_path`` at the output directory (it must contain .safetensors).

Examples:
  uv run --with huggingface_hub scripts/model-download/download_qwen3_tts_mlx.py

  AODCAST_HF_MODEL_BASE=/path/to/models \\
    uv run --with huggingface_hub scripts/model-download/download_qwen3_tts_mlx.py

  HF_TOKEN=hf_... uv run --with huggingface_hub ...  # if the repo requires auth
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


DEFAULT_BASE = Path("/Users/chuhaonan/codeMIni-hn/model")
DEFAULT_REPO = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit"
PROGRESS_MARKER = "AODCAST_PROGRESS"


def _default_output_dir(base: Path, repo_id: str) -> Path:
    name = repo_id.rstrip("/").split("/")[-1]
    return base / name


def _build_progress_tqdm():
    # Imported lazily so this script still errors cleanly if huggingface_hub/tqdm
    # are missing in the current interpreter environment.
    from tqdm.auto import tqdm

    class _ProgressTqdm(tqdm):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._last_reported = -1

        def update(self, n=1):
            out = super().update(n)
            self._report()
            return out

        def refresh(self, *args, **kwargs):
            out = super().refresh(*args, **kwargs)
            self._report()
            return out

        def _report(self) -> None:
            if not self.total:
                return
            percent = int(max(0, min(100, (self.n / self.total) * 100)))
            if percent != self._last_reported:
                self._last_reported = percent
                print(f"{PROGRESS_MARKER} {percent}", flush=True)

    return _ProgressTqdm


def main() -> int:
    env_base = os.environ.get("AODCAST_HF_MODEL_BASE")
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--repo-id",
        default=DEFAULT_REPO,
        help=f"Hugging Face repo id (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path(env_base) if env_base else DEFAULT_BASE,
        help=f"Parent folder for the model directory (default: {DEFAULT_BASE})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Exact directory to download into (default: <base-dir>/<repo tail>)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("HF_TOKEN"),
        help="Hugging Face token (else HF_TOKEN env)",
    )
    args = parser.parse_args()

    out: Path = args.output_dir or _default_output_dir(args.base_dir, args.repo_id)
    out.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print(
            "Missing dependency: huggingface_hub\n"
            "Install with: uv run --with huggingface_hub "
            f"{Path(__file__).resolve()}",
            file=sys.stderr,
        )
        return 1

    print(f"Repo:      {args.repo_id}")
    print(f"Output:    {out.resolve()}")
    print("Downloading (this may take a while)...")
    progress_tqdm = None
    try:
        progress_tqdm = _build_progress_tqdm()
    except Exception:
        # Fallback: keep download functional even if tqdm hooks are unavailable.
        progress_tqdm = None

    if progress_tqdm is not None:
        try:
            snapshot_download(
                repo_id=args.repo_id,
                local_dir=str(out),
                token=args.token,
                local_dir_use_symlinks=False,
                resume_download=True,
                tqdm_class=progress_tqdm,
            )
        except TypeError:
            # Older huggingface_hub may not support tqdm_class.
            snapshot_download(
                repo_id=args.repo_id,
                local_dir=str(out),
                token=args.token,
                local_dir_use_symlinks=False,
                resume_download=True,
            )
    else:
        snapshot_download(
            repo_id=args.repo_id,
            local_dir=str(out),
            token=args.token,
            local_dir_use_symlinks=False,
            resume_download=True,
        )
    print("Done.")
    print(f"For Aodcast later: set local_model_path to {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
