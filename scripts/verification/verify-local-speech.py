#!/usr/bin/env python3
"""Run REAL local TTS/ASR and the podcast pipeline; never substitute audio models."""
from __future__ import annotations

import argparse
import json
import re
import resource
import sys
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
from app.domain.tts_config import TTSProviderConfig
from app.orchestration.audio_rendering import AudioRenderingService
from app.providers.local_speech.client import LocalSpeechClient
from app.providers.local_speech.provider import LocalSpeechTTSProvider
from app.providers.tts_api.base import TTSGenerationRequest
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore

REPO_ROOT = Path(__file__).resolve().parents[2]

SHORT_TEXT = "欢迎收听今天的播客。今天我们讨论人工智能如何帮助普通人提高工作效率。技术的价值在于解决真实的问题。"
LONG_PARTS = [
    "欢迎收听今天的节目。我们想讨论一个贴近每个人生活的话题，那就是如何让技术真正帮助普通人，而不是让普通人为了追赶技术不断焦虑。每天打开手机，我们都能看到新的工具、新的观点和新的成功故事，但真正值得思考的问题是，这些变化究竟解决了什么实际困难。",
    "先从一个普通的早晨说起。你可能需要整理会议记录，回复几封邮件，再为下午的讨论准备材料。这些事情单独看都不复杂，可是一旦堆在一起，就会不断打断注意力。我们需要的帮助，往往不是替我们做出所有决定，而是把重复的工作处理得更清楚，让人能够专心判断真正重要的事情。",
    "比如一段录音，如果能够在本机完成识别，再整理成可以检索的文字，很多信息就不会在会议结束后消失。又比如一篇长文章，如果能够用稳定自然的声音读出来，就能让我们在散步或者通勤的时候继续学习。技术在这里承担的是一种支持性的角色，它扩大了选择，而不是替代人的全部经验。",
    "当然，便利并不意味着可以忽略边界。我们仍然需要知道数据放在哪里，哪些内容适合自动处理，哪些判断必须由人来完成。尤其当信息涉及家庭、工作或者个人经历的时候，清楚的控制权比一个听起来很漂亮的承诺更加重要。一个值得信任的工具，应该让使用者能够理解它正在做什么。",
    "谈到学习新工具，很多人会习惯性地追求一步到位。他们希望第一天就配置所有功能，建立完整流程，然后再开始真正的工作。可是经验告诉我们，最有效的方法常常更加朴素。先选一个每天都会遇到的小问题，尝试解决它，再观察节省了多少时间，以及是否引入了新的麻烦。",
    "如果一个工具只能在演示的时候表现出色，到了真实工作里却需要不断修补，那么它暂时还不能算作可靠的基础设施。我们应该关注错误发生时会怎样，服务暂时不可用时是否能够清楚提示，以及任务很长的时候系统能不能稳定完成。这些看起来不起眼的细节，决定了一个工具是否值得长期依赖。",
    "还有一个容易忽略的方面，那就是人的节奏。效率不只是单位时间完成更多事情，也包括减少没有必要的切换，给思考留出连续的空间。有时候，把一段文字听完，比同时打开许多窗口更能帮助理解。有时候，停下来确认一句话的真实含义，也比立刻生成更多内容更加有价值。",
    "因此，评价技术时，我们可以问几个具体的问题。它有没有让原本困难的事情变得更容易？它有没有保留使用者选择和修改的权利？遇到限制的时候，它是否愿意明确说明，而不是用模糊的说法掩盖问题？这些问题没有那么新鲜，却能够帮助我们避开许多不必要的试错。",
    "把这些原则放回日常工作，我们就会发现，好的系统往往不是功能最多的系统，而是职责清楚、反馈及时、出错以后容易恢复的系统。每个部分做好自己的事情，彼此之间通过明确的接口合作，复杂的任务就能够被拆成可理解的步骤。这样带来的稳定感，通常比短暂的惊艳更有价值。",
    "今天的节目接近尾声。希望你下次遇到一种新工具的时候，不必急着判断自己是否已经落后。可以先想一想，它是否能够帮助你解决眼前一个真实的问题。如果答案是肯定的，就从一个小任务开始，保留观察，逐步调整。感谢你的收听，我们下期再见。我们的测试到这里全部结束。",
]


def wav_info(path: Path) -> dict[str, object]:
    with wave.open(str(path), "rb") as audio:
        assert audio.getnframes() > 0 and audio.getsampwidth() == 2
        return {"path": str(path), "bytes": path.stat().st_size,
                "seconds": round(audio.getnframes() / audio.getframerate(), 3),
                "sample_rate_hz": audio.getframerate(), "channels": audio.getnchannels()}


def characters(text: str) -> str:
    return "".join(re.findall(r"[\u3400-\u9fffA-Za-z0-9]", text)).lower()


def character_error_rate(expected: str, actual: str) -> float:
    a, b = characters(expected), characters(actual)
    row = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        new = [i]
        for j, right in enumerate(b, 1):
            new.append(min(new[-1] + 1, row[j] + 1, row[j - 1] + (left != right)))
        row = new
    return row[-1] / max(1, len(a))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / ".local-data/speech-verification" / datetime.now().strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    client = LocalSpeechClient()
    health = client.health()
    print(json.dumps({"service_before": health}, ensure_ascii=False), flush=True)
    samples = []
    stop = threading.Event()
    phase = {"name": "short_tts"}

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
                    log.flush()
                stop.wait(1)

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    results = {"output": str(output), "service_before": health,
               "planner": "deterministic mock LLM; TTS and ASR are real HTTP model inference"}
    try:
        config = TTSProviderConfig(model=health["models"]["tts"]["id"])
        provider = LocalSpeechTTSProvider(config)
        start = time.monotonic()
        short = provider.synthesize(TTSGenerationRequest("verification-short", SHORT_TEXT, "warm_narrator", "wav"))
        short_path = output / "short.wav"
        short_path.write_bytes(short.audio_bytes)
        results["short_tts"] = {**wav_info(short_path), "elapsed_seconds": round(time.monotonic() - start, 3), "input": SHORT_TEXT}
        print(json.dumps({"short_tts": results["short_tts"]}, ensure_ascii=False), flush=True)

        phase["name"] = "asr_loopback"
        start = time.monotonic()
        recognized = client.transcribe(short_path, "zh")
        cer = character_error_rate(SHORT_TEXT, recognized)
        results["asr_loopback"] = {"text": recognized, "character_error_rate": round(cer, 4),
                                  "elapsed_seconds": round(time.monotonic() - start, 3)}
        print(json.dumps({"asr_loopback": results["asr_loopback"]}, ensure_ascii=False), flush=True)
        assert cer <= 0.15, f"ASR character error rate {cer:.3f} exceeds acceptance threshold"

        phase["name"] = "long_pipeline"
        long_text = "".join(LONG_PARTS)
        assert len(long_text) > 1000
        (output / "long-input.txt").write_text(long_text)
        store = ProjectStore(output / "pipeline-state")
        configs = ConfigStore(output / "pipeline-state/config")
        artifacts = ArtifactStore(output / "pipeline-state")
        for component in (store, configs, artifacts):
            component.bootstrap()
        configs.save_llm_config(LLMProviderConfig(provider="mock"))
        configs.save_tts_config(config)
        session = SessionRecord(topic="本机语音真实联调", creation_intent="验证千字完整播客")
        session.transition(SessionState.SCRIPT_EDITED)
        script = ScriptRecord(session_id=session.session_id, final=long_text)
        store.save_project(SessionProject(session=session, script=script, artifact=ArtifactRecord(session_id=session.session_id)))
        start = time.monotonic()
        rendered = AudioRenderingService(store, configs, artifacts).render_audio(session.session_id, script_id=script.script_id)
        long_audio = Path(rendered.audio_path)
        assert len(rendered.project.speech_plan.segments) == 1, "Aodcast must submit the long natural paragraph intact"
        results["long_pipeline"] = {**wav_info(long_audio), "input_characters": len(long_text),
                                    "business_segments": len(rendered.project.speech_plan.segments),
                                    "elapsed_seconds": round(time.monotonic() - start, 3),
                                    "render_id": rendered.project.render_manifest.render_id}
        assert results["long_pipeline"]["seconds"] > 60
        print(json.dumps({"long_pipeline": results["long_pipeline"]}, ensure_ascii=False), flush=True)

        phase["name"] = "long_tail_asr"
        tail = output / "long-tail.wav"
        with wave.open(str(long_audio), "rb") as source, wave.open(str(tail), "wb") as target:
            target.setparams(source.getparams())
            source.setpos(max(0, source.getnframes() - 30 * source.getframerate()))
            target.writeframes(source.readframes(source.getnframes()))
        text = client.transcribe(tail, "zh")
        results["long_tail_asr"] = {"text": text, "closing_marker_present": "测试到这里全部结束" in characters(text)}
        print(json.dumps({"long_tail_asr": results["long_tail_asr"]}, ensure_ascii=False), flush=True)
        assert results["long_tail_asr"]["closing_marker_present"], "Long audio is missing the spoken closing marker"
        results["passed"] = True
    except Exception as exc:
        results["passed"] = False
        results["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        stop.set()
        monitor_thread.join(timeout=6)
        if samples:
            results["memory"] = {
                "samples": len(samples),
                "rss_peak_bytes": max(item["memory"]["rss_bytes"] for item in samples),
                "metal_peak_bytes": max(item["memory"]["metal_peak_bytes"] for item in samples),
                "system_available_min_bytes": min(item["memory"]["system_available_bytes"] for item in samples),
                "client_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),
                "by_phase": {
                    name: {
                        "rss_peak_bytes": max(item["memory"]["rss_bytes"] for item in samples if item["phase"] == name),
                        "metal_peak_bytes": max(item["memory"]["metal_peak_bytes"] for item in samples if item["phase"] == name),
                    }
                    for name in {item["phase"] for item in samples}
                },
            }
        (output / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps({"report": str(output / "results.json"), "passed": results.get("passed", False)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
