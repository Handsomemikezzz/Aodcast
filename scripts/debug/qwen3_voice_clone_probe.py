#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_CORE = REPO_ROOT / "services" / "python-core"
if str(PYTHON_CORE) not in sys.path:
    sys.path.insert(0, str(PYTHON_CORE))


DEFAULT_TEXTS = {
    "short": "欢迎收听今天的测试音频。这是一段很短的声音克隆验证。",
    "medium": (
        "欢迎收听今天的测试音频。我们会用同一个参考音频生成更长一点的内容，"
        "观察说话人的音色、气息、语速和情绪是否保持稳定。"
    ),
    "long": (
        "欢迎收听今天的测试音频。这个版本会刻意拉长文本，模拟播客正文的生成场景。"
        "如果模型只在短句里保持相似，而在长文本里逐渐变成另一个声音，那么问题更可能是长文本生成时的音色漂移。"
        "如果短句、中句和长句都不像参考音频，那么我们需要优先判断参考音频质量、参考文本是否准确，以及当前模型版本是否适合做声音克隆。"
    ),
}


def _load_texts(path: str) -> dict[str, str]:
    if not path:
        return dict(DEFAULT_TEXTS)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("--texts-json must point to an object mapping labels to text.")
    texts: dict[str, str] = {}
    for key, value in payload.items():
        text = str(value).strip()
        if text:
            texts[str(key)] = text
    if not texts:
        raise ValueError("--texts-json did not contain any non-empty text values.")
    return texts


def _write_audio(path: Path, audio: object, sample_rate: int) -> None:
    from mlx_audio.audio_io import write as audio_write  # type: ignore

    path.parent.mkdir(parents=True, exist_ok=True)
    audio_write(str(path), audio, sample_rate, format=path.suffix.lstrip(".") or "wav")


def _load_script_text(path: str) -> tuple[str, dict[str, object]]:
    if not path:
        return "", {}
    script_path = Path(path).expanduser().resolve()
    payload = json.loads(script_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("--script-json must point to a script JSON object.")
    text = str(payload.get("final") or payload.get("draft") or "").strip()
    if not text:
        raise ValueError("--script-json did not contain non-empty final/draft text.")
    return text, {
        "path": str(script_path),
        "script_id": str(payload.get("script_id") or ""),
        "name": str(payload.get("name") or ""),
        "chars": len(text),
    }


def _generate_one(
    model: object,
    *,
    text: str,
    ref_audio: Path,
    ref_text: str,
    language: str,
    temperature: float,
    top_k: int,
    top_p: float,
    max_tokens: int,
) -> object:
    results = list(
        model.generate(
            text=text,
            ref_audio=str(ref_audio),
            ref_text=ref_text,
            lang_code=language,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            max_tokens=max_tokens,
        )
    )
    if not results:
        raise RuntimeError("Model produced no result.")
    return results[0].audio


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Direct Qwen3-TTS Base voice-clone probe. Bypasses Aodcast app code."
    )
    parser.add_argument("--model", default="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit")
    parser.add_argument("--ref-audio", required=True, help="Reference audio file path.")
    parser.add_argument("--ref-text", required=True, help="Exact transcript spoken in the reference audio.")
    parser.add_argument("--language", default="chinese")
    parser.add_argument("--output-dir", default=".local-data/debug/qwen3-voice-clone")
    parser.add_argument("--texts-json", default="", help="Optional JSON object of label -> target text.")
    parser.add_argument("--script-json", default="", help="Optional Aodcast script JSON. Runs App parity experiments.")
    parser.add_argument("--skip-default-texts", action="store_true", help="Only run script-json experiments.")
    parser.add_argument("--temperature", type=float, default=0.9)
    parser.add_argument("--top-k", type=int, default=50)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--repeat", type=int, default=1, help="Generate each text N times to expose sampling variance.")
    args = parser.parse_args()

    ref_audio = Path(args.ref_audio).expanduser().resolve()
    if not ref_audio.exists():
        raise FileNotFoundError(f"Reference audio does not exist: {ref_audio}")
    if not ref_audio.is_file():
        raise ValueError(f"Reference audio is not a file: {ref_audio}")
    ref_text = args.ref_text.strip()
    if not ref_text:
        raise ValueError("--ref-text must not be empty.")

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    script_text, script_meta = _load_script_text(args.script_json)
    texts = {} if args.skip_default_texts else _load_texts(args.texts_json)

    started = time.time()
    report: dict[str, object] = {
        "model": args.model,
        "ref_audio": str(ref_audio),
        "ref_text": ref_text,
        "language": args.language,
        "texts": texts,
        "script": script_meta,
        "outputs": [],
    }

    try:
        import mlx.core as mx  # type: ignore
        from mlx_audio.tts.utils import load_model  # type: ignore
        from app.domain.tts_config import TTSProviderConfig
        from app.providers.tts_local_mlx.chunker import split_script_into_chunks
        from app.providers.tts_local_mlx.runner import MLXAudioQwenRunner

        report["mlx_version"] = getattr(mx, "__version__", "")
        report["default_device"] = str(mx.default_device())
        model = load_model(args.model)
        report["sample_rate"] = int(getattr(model, "sample_rate", 24000))
        report["model_type"] = str(getattr(model, "model_type", ""))
        report["supported_speakers"] = (
            model.get_supported_speakers() if hasattr(model, "get_supported_speakers") else []
        )

        for label, text in texts.items():
            for index in range(max(1, args.repeat)):
                item_started = time.time()
                audio = _generate_one(
                    model,
                    text=text,
                    ref_audio=ref_audio,
                    ref_text=ref_text,
                    language=args.language,
                    temperature=args.temperature,
                    top_k=args.top_k,
                    top_p=args.top_p,
                    max_tokens=args.max_tokens,
                )
                out_path = output_dir / f"{label}-{index + 1}.wav"
                _write_audio(out_path, audio, int(report["sample_rate"]))
                report["outputs"].append(
                    {
                        "label": label,
                        "repeat": index + 1,
                        "text_chars": len(text),
                        "path": str(out_path),
                        "elapsed_seconds": round(time.time() - item_started, 3),
                    }
                )
                print(f"[ok] {label} #{index + 1}: {out_path}", flush=True)

        if script_text:
            full_started = time.time()
            full_audio = _generate_one(
                model,
                text=script_text,
                ref_audio=ref_audio,
                ref_text=ref_text,
                language=args.language,
                temperature=args.temperature,
                top_k=args.top_k,
                top_p=args.top_p,
                max_tokens=args.max_tokens,
            )
            full_path = output_dir / "script-full-once.wav"
            _write_audio(full_path, full_audio, int(report["sample_rate"]))
            report["outputs"].append(
                {
                    "label": "script-full-once",
                    "mode": "direct_full",
                    "text_chars": len(script_text),
                    "path": str(full_path),
                    "elapsed_seconds": round(time.time() - full_started, 3),
                }
            )
            print(f"[ok] script full once: {full_path}", flush=True)

            chunk_dir = output_dir / "script-app-chunks"
            chunks = split_script_into_chunks(script_text)
            report["script_chunks"] = [
                {"index": chunk.index, "text_chars": len(chunk.text), "text": chunk.text}
                for chunk in chunks
            ]
            chunk_audios: list[object] = []
            chunks_started = time.time()
            for chunk in chunks:
                chunk_started = time.time()
                chunk_audio = _generate_one(
                    model,
                    text=chunk.text,
                    ref_audio=ref_audio,
                    ref_text=ref_text,
                    language=args.language,
                    temperature=args.temperature,
                    top_k=args.top_k,
                    top_p=args.top_p,
                    max_tokens=args.max_tokens,
                )
                chunk_audios.append(chunk_audio)
                chunk_path = chunk_dir / f"chunk-{chunk.index + 1:02d}.wav"
                _write_audio(chunk_path, chunk_audio, int(report["sample_rate"]))
                report["outputs"].append(
                    {
                        "label": f"script-chunk-{chunk.index + 1:02d}",
                        "mode": "direct_app_chunk",
                        "text_chars": len(chunk.text),
                        "path": str(chunk_path),
                        "elapsed_seconds": round(time.time() - chunk_started, 3),
                    }
                )
                print(f"[ok] script chunk {chunk.index + 1:02d}: {chunk_path}", flush=True)

            if chunk_audios:
                joined = mx.concatenate(chunk_audios, axis=0)
                joined_path = output_dir / "script-app-chunks-joined.wav"
                _write_audio(joined_path, joined, int(report["sample_rate"]))
                report["outputs"].append(
                    {
                        "label": "script-app-chunks-joined",
                        "mode": "direct_app_chunks_joined",
                        "chunks": len(chunks),
                        "path": str(joined_path),
                        "elapsed_seconds": round(time.time() - chunks_started, 3),
                    }
                )
                print(f"[ok] joined app chunks: {joined_path}", flush=True)

            runner_started = time.time()
            runner = MLXAudioQwenRunner(
                TTSProviderConfig(
                    provider="local_mlx",
                    model=args.model,
                    audio_format="wav",
                )
            )
            runner_result = runner.synthesize(
                script_text,
                audio_format="wav",
                language=args.language,
                reference_audio_path=str(ref_audio),
                reference_text=ref_text,
            )
            runner_path = output_dir / "script-app-runner.wav"
            runner_path.write_bytes(runner_result.audio_bytes)
            report["outputs"].append(
                {
                    "label": "script-app-runner",
                    "mode": "app_runner",
                    "chunks": runner_result.chunks_total,
                    "path": str(runner_path),
                    "elapsed_seconds": round(time.time() - runner_started, 3),
                }
            )
            print(f"[ok] app runner: {runner_path}", flush=True)

        report["elapsed_seconds"] = round(time.time() - started, 3)
        report_path = output_dir / "report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[done] report: {report_path}")
        return 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc(limit=12)
        report["elapsed_seconds"] = round(time.time() - started, 3)
        report_path = output_dir / "report.failed.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[failed] {report['error']}", file=sys.stderr)
        print(f"[failed] report: {report_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
