#!/usr/bin/env python3
"""Run REAL zero-shot voice cloning with both Qwen3 Base models and compare them.

One Speaker Reference is created once and reused by every model. Without --reference the
script records its own reference with the preset model, so the transcript is exact.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

from app.domain.artifact import ArtifactRecord
from app.domain.project import SessionProject
from app.domain.provider_config import LLMProviderConfig
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord, SessionState
from app.domain.tts_config import LOCAL_CLONE_MODELS, TTSProviderConfig
from app.orchestration.audio_rendering import AudioRenderingService, VoiceRenderSettings
from app.providers.local_speech.client import LocalSpeechClient
from app.providers.local_speech.provider import LocalSpeechTTSProvider
from app.providers.tts_api.base import TTSGenerationRequest
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore
from app.storage.speaker_reference_store import SpeakerReferenceStore

REPO_ROOT = Path(__file__).resolve().parents[2]
# Reuse the WAV and CER helpers of the preset-voice verification script.
_spec = importlib.util.spec_from_file_location("verify_local_speech", Path(__file__).with_name("verify-local-speech.py"))
_speech = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_speech)
wav_info, character_error_rate, characters = _speech.wav_info, _speech.character_error_rate, _speech.characters

GENERATED_REFERENCE_TEXT = "大家好，我是今天的主持人。很高兴在这里和你聊一聊最近读到的几本好书，希望你也会喜欢。"
SHORT_TEXT = "欢迎收听今天的节目。今天我们聊一聊，为什么好的播客听起来就像一位老朋友在身边说话。"
EPISODE_PARAGRAPHS = [
    "欢迎收听今天的节目。我们想聊一个很日常的话题，就是怎样把一天里零碎的时间，变成真正属于自己的时间。",
    "很多人以为效率就是做得更多，可是真正让人疲惫的，往往是不停地切换。每一次被打断，注意力都要重新找回来。",
    "所以不妨先选一件小事，比如每天早上留出二十分钟，只做一件最重要的事情，然后观察一周以后会有什么变化。",
    "今天的节目就到这里，感谢你的收听，我们下期再见。克隆测试到这里全部结束。",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, help="Your own reference recording (3-30 s of clean speech).")
    parser.add_argument("--reference-text", default="", help="Exact transcript of --reference.")
    parser.add_argument("--language", default="zh", help="Language of the reference transcript.")
    parser.add_argument("--models", nargs="+", default=list(LOCAL_CLONE_MODELS), choices=LOCAL_CLONE_MODELS)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / ".local-data/speech-verification" / ("clone-" + datetime.now().strftime("%Y%m%d-%H%M%S")))
    args = parser.parse_args()
    if bool(args.reference) != bool(args.reference_text.strip()):
        parser.error("--reference and --reference-text must be given together")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    client = LocalSpeechClient()
    health = client.health()
    served = {item["id"] for item in health["models"].get("clone", [])}
    missing = [model for model in args.models if model not in served]
    if missing:
        raise SystemExit(f"The running speech service does not serve {missing}; run ./speech-service/service.sh restart")
    print(json.dumps({"service_before": health}, ensure_ascii=False), flush=True)

    samples = []
    stop = threading.Event()
    phase = {"name": "reference"}

    def monitor():
        with (output / "memory.jsonl").open("w") as log:
            while not stop.is_set():
                try:
                    sample = {"time": time.time(), "phase": phase["name"], **client.health()}
                    samples.append(sample)
                    log.write(json.dumps(sample) + "\n")
                    log.flush()
                except Exception as exc:
                    log.write(json.dumps({"time": time.time(), "monitor_error": str(exc)}) + "\n")
                stop.wait(1)

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    results: dict[str, object] = {"output": str(output), "service_before": health, "models": {}}
    try:
        state = output / "state"
        store, configs, artifacts = ProjectStore(state), ConfigStore(state / "config"), ArtifactStore(state)
        for component in (store, configs, artifacts):
            component.bootstrap()
        configs.save_llm_config(LLMProviderConfig(provider="mock"))
        configs.save_tts_config(TTSProviderConfig())
        references = SpeakerReferenceStore(state, artifacts)
        references.bootstrap()

        if args.reference:
            source, reference_text = args.reference, args.reference_text.strip()
        else:
            preset = LocalSpeechTTSProvider(TTSProviderConfig(model=health["models"]["tts"]["id"]))
            source = output / "generated-reference.wav"
            source.write_bytes(preset.synthesize(
                TTSGenerationRequest("clone-reference", GENERATED_REFERENCE_TEXT, "news_anchor", "wav")
            ).audio_bytes)
            reference_text = GENERATED_REFERENCE_TEXT
        reference = references.create_user_reference(
            name="Verification voice", source_audio_path=source, reference_text=reference_text, language=args.language,
        )
        results["reference"] = {**wav_info(Path(reference.audio_path)), "text": reference_text,
                                "reference_hash": reference.reference_hash}
        print(json.dumps({"reference": results["reference"]}, ensure_ascii=False), flush=True)

        session = SessionRecord(topic="本机声音克隆真实联调", creation_intent="比较两个 Base 模型")
        session.transition(SessionState.SCRIPT_EDITED)
        script = ScriptRecord(session_id=session.session_id, final="\n\n".join(EPISODE_PARAGRAPHS))
        store.save_project(SessionProject(session=session, script=script, artifact=ArtifactRecord(session_id=session.session_id)))
        service = AudioRenderingService(store, configs, artifacts)
        service.select_speaker_reference(session.session_id, script_id=script.script_id, reference=reference)

        for model in args.models:
            label = model.rsplit("/", 1)[-1]
            row: dict[str, object] = {}
            results["models"][model] = row  # type: ignore[index]

            phase["name"] = f"{label}:short"
            start = time.monotonic()
            short = LocalSpeechTTSProvider(TTSProviderConfig(model=model)).synthesize(TTSGenerationRequest(
                "clone-short", SHORT_TEXT, "", "wav", language="zh",
                reference_audio_path=reference.audio_path, reference_text=reference.reference_text,
            ))
            short_path = output / f"{label}-short.wav"
            short_path.write_bytes(short.audio_bytes)
            row["short"] = {**wav_info(short_path), "elapsed_seconds": round(time.monotonic() - start, 3)}
            recognized = client.transcribe(short_path, "zh")
            row["short"]["asr"] = recognized  # type: ignore[index]
            row["short"]["character_error_rate"] = round(character_error_rate(SHORT_TEXT, recognized), 4)  # type: ignore[index]
            print(json.dumps({model: {"short": row["short"]}}, ensure_ascii=False), flush=True)

            phase["name"] = f"{label}:episode"
            start = time.monotonic()
            rendered = service.render_audio(
                session.session_id, script_id=script.script_id, override_provider="local_http",
                override_model=model, settings=VoiceRenderSettings(), require_speaker_reference=True,
            )
            manifest = rendered.project.render_manifest
            assert manifest and manifest.pipeline[0].model == model
            assert manifest.speaker_reference and manifest.speaker_reference["reference_hash"] == reference.reference_hash
            episode = Path(rendered.audio_path)
            (output / f"{label}-episode.wav").write_bytes(episode.read_bytes())
            row["episode"] = {**wav_info(episode), "elapsed_seconds": round(time.monotonic() - start, 3),
                              "segments": len(manifest.segments), "render_id": manifest.render_id}
            tail = output / f"{label}-episode-tail.wav"
            with wave.open(str(episode), "rb") as source_wav, wave.open(str(tail), "wb") as target:
                target.setparams(source_wav.getparams())
                source_wav.setpos(max(0, source_wav.getnframes() - 12 * source_wav.getframerate()))
                target.writeframes(source_wav.readframes(source_wav.getnframes()))
            tail_text = client.transcribe(tail, "zh")
            row["episode"]["tail_asr"] = tail_text  # type: ignore[index]
            row["episode"]["closing_marker_present"] = "测试到这里全部结束" in characters(tail_text)  # type: ignore[index]
            print(json.dumps({model: {"episode": row["episode"]}}, ensure_ascii=False), flush=True)

            phase["name"] = f"{label}:regenerate"
            plan = rendered.project.speech_plan
            assert plan is not None
            start = time.monotonic()
            regenerated = service.regenerate_audio_window_with_cancellation(
                session.session_id, script_id=script.script_id, target_segment_id=plan.segments[1].segment_id,
                expected_plan_id=plan.plan_id, expected_render_id=manifest.render_id,
            )
            after = regenerated.project.render_manifest
            assert after and after.parent_render_id == manifest.render_id and after.pipeline[0].model == model
            row["regenerate"] = {"elapsed_seconds": round(time.monotonic() - start, 3),
                                 "affected_segments": list(regenerated.affected_segment_ids)}
            print(json.dumps({model: {"regenerate": row["regenerate"]}}, ensure_ascii=False), flush=True)

        failures = [
            f"{model}: {problem}"
            for model, row in results["models"].items()  # type: ignore[union-attr]
            for problem in (
                ["short-clone CER above 0.2"] if row["short"]["character_error_rate"] > 0.2 else []
            ) + ([] if row["episode"]["closing_marker_present"] else ["episode is missing its closing marker"])
        ]
        assert not failures, "; ".join(failures)
        results["passed"] = True
    except BaseException as exc:
        results["passed"] = False
        results["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        stop.set()
        monitor_thread.join(timeout=6)
        if samples:
            results["memory"] = {
                name: {
                    "rss_peak_bytes": max(s["memory"]["rss_bytes"] for s in samples if s["phase"] == name),
                    "metal_peak_bytes": max(s["memory"]["metal_peak_bytes"] for s in samples if s["phase"] == name),
                    "system_available_min_bytes": min(s["memory"]["system_available_bytes"] for s in samples if s["phase"] == name),
                }
                for name in dict.fromkeys(s["phase"] for s in samples)
            }
        (output / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps({"report": str(output / "results.json"), "passed": results.get("passed", False)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
