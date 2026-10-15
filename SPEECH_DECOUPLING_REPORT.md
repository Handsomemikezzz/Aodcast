# Aodcast 解耦与清理验收报告

原始解耦验收时间：2026-10-15T15:24:53+08:00。

迁移说明：第 1～5 节保留原始真机测量与清理记录；第 6 节记录迁移到内置服务后的重新实测。服务源码现已随 Aodcast 纳入 `speech-service/`；推理仍在独立 Python 3.12 进程运行，编排核心仍通过 HTTP 调用。桌面/Web 启动器现按“语音健康检查 → runtime → 外壳”顺序启动，权重缓存仍在仓库外。

结论：完成架构解耦、物理清理、真实量化模型 TTS→ASR 闭环及千字播客管线压力验证。所有下面的音频数据来自真实 Apple Silicon 推理；回归测试替身不作为真机验收依据。

## 1. 实测环境与权重

- 设备：Apple M4，16 GiB 统一内存；本机 macOS，无 Docker。
- 服务：`http://127.0.0.1:8090`，launchd 管理，PID `92061`；测试前后 PID 一致，未发生重启。
- TTS：`mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit`；ASR：`mlx-community/Qwen3-ASR-0.6B-8bit`。
- 已发现原有 Qwen3-TTS Base / VoxCPM2 缓存。指定模型的缺失主权重已实际下载，复用现有可用公共组件缓存。
- 常规大文件传输停滞后采用分段下载；以下两个文件均按 Hugging Face LFS 公布的 SHA-256 校验后才用于推理。

| 模型 | 版本 SHA | 主权重字节数 | SHA-256 |
|---|---|---:|---|
| TTS | `049ef77fe8816b536193c0c25f9a214d17921282` | 1,286,743,170 | `3bcb2c4a127e6243e81a30b7126c7865f686d3559de4f938e5d3b150c6a9560d` |
| ASR | `89e96d92ba34aca20b3e29fb10cc284097d1219f` | 1,006,229,426 | `b5bfe4abc1b4c6e58b633096682ec2b6297298add1527119936107d211adf0e8` |

## 2. 真实联调结果

| 验证项 | 实际结果 | 耗时 |
|---|---|---:|
| Aodcast TTS 短文 | 9.04 秒，24kHz / mono / PCM16 WAV，433,964 字节 | 50.999 秒（首次加载） |
| ASR 回环 | 中文正文与原文一致；忽略标点的字符错误率 0.0% | 9.201 秒 |
| Aodcast 长文完整渲染 | 1246 字；业务端 1 个自然段请求；服务端 11 片；输出 266.31 秒 / 48kHz / mono / PCM16 WAV，25,565,804 字节 | 207.940 秒 |
| 长音频完整性 | 最后 30 秒再次送真实 ASR，检出“我们的测试到这里全部结束” | 通过 |

服务端 11 片实际长度：`120, 111, 108, 92, 95, 120, 120, 120, 120, 120, 120`，合计 1246 字，所有切片均在 80～120 字之间。原始长文只在 Aodcast 中形成一个编辑段落，防 OOM 切片与交叉淡化完全由语音服务执行。

实际短文与回环识别文本：

> 欢迎收听今天的播客。今天我们讨论人工智能如何帮助普通人提高工作效率。技术的价值在于解决真实的问题。

压力测试经过 `AudioRenderingService.render_audio()`、Speech Plan、TTS HTTP provider、真实服务推理、音频归一化、Render Manifest 和最终 WAV 落盘。为隔离语音验证，Speech Director 使用确定性的 mock LLM；TTS、ASR、Metal 运算、音频文件及网络请求均为真实执行。

### 内存证据

- 每秒采样，共 263 条；服务 RSS 峰值 **2.066 GiB**。
- MLX/Metal 进程生命周期分配峰值 **6.677 GiB**，低于配置的 8 GiB MLX 限制。
- Aodcast 验证客户端进程 RSS 峰值 **0.576 GiB**。
- 系统可用内存最低 **1.554 GiB**。
- 全部采样中同时驻留模型数不超过 1；TTS 与 ASR 切换时释放另一模型。
- 本次没有 OOM、HTTP 超时或服务重启。RSS 与 Metal 分配是不同统计口径，不应相加；Metal peak 是生命周期峰值，不是每个阶段独立归零后的峰值。
- 单次完整压力测试证明此次输入与负载下可完成，不代表其他任意系统负载下的绝对 OOM 保证。15 分钟闲置卸载另有单元测试，本轮未额外等待完整闲置周期。

### 原始产物

以下为本机 `.local-data/` 下的 ignored 验收产物，已随本地项目迁移保留，不随 Git/GitHub 发布。相对链接仅在保留这些文件的本地 checkout 中可打开；其他机器请运行复跑脚本生成自己的证据。

- [原始 results.json](.local-data/speech-verification/acceptance/results.json)
- [每秒内存 memory.jsonl](.local-data/speech-verification/acceptance/memory.jsonl)
- [实际终端输出 terminal.log](.local-data/speech-verification/acceptance/terminal.log)
- [服务切片与模型加载日志](.local-data/speech-verification/acceptance/service-inference.log)
- [短音频 short.wav](.local-data/speech-verification/acceptance/short.wav)
- [1246 字原始文稿](.local-data/speech-verification/acceptance/long-input.txt)
- [最终完整播客 WAV](.local-data/speech-verification/acceptance/pipeline-state/exports/02e76c5a-bbfc-4266-8156-ce611737b730/renders/85b4efc03c7b48fc99eda50c7c39dc98/podcast.wav)
- [长文末尾 ASR 用音频](.local-data/speech-verification/acceptance/long-tail.wav)
- [TTS 下载与哈希日志](.local-data/speech-verification/acceptance/tts-download.log)
- [ASR 下载与哈希日志](.local-data/speech-verification/acceptance/asr-download.log)

## 3. 物理删除清单

Git 记录中删除 24 个旧路径。其中旧 MLX 推理目录、下载与调试脚本、废弃适配器测试均已物理删除；`app/providers/audio_utils.py` 中仅测试使用的正弦音频生成器迁至 `tests/audio_utils.py`，生产 provider 不再携带测试实现。

```text
scripts/debug/qwen3_voice_clone_probe.py
scripts/model-download/download_tts_model.py
services/python-core/app/providers/audio_utils.py
services/python-core/app/providers/tts_local_mlx/__init__.py
services/python-core/app/providers/tts_local_mlx/adapters/__init__.py
services/python-core/app/providers/tts_local_mlx/adapters/base.py
services/python-core/app/providers/tts_local_mlx/adapters/moss.py
services/python-core/app/providers/tts_local_mlx/adapters/qwen3.py
services/python-core/app/providers/tts_local_mlx/adapters/voxcpm2.py
services/python-core/app/providers/tts_local_mlx/capabilities.py
services/python-core/app/providers/tts_local_mlx/chunker.py
services/python-core/app/providers/tts_local_mlx/mlx_worker.py
services/python-core/app/providers/tts_local_mlx/model_spec.py
services/python-core/app/providers/tts_local_mlx/presets.py
services/python-core/app/providers/tts_local_mlx/provider.py
services/python-core/app/providers/tts_local_mlx/runner.py
services/python-core/app/providers/tts_local_mlx/runtime.py
services/python-core/app/providers/tts_local_mlx/version.py
services/python-core/app/providers/tts_local_mlx/worker_client.py
services/python-core/tests/test_local_mlx_tts.py
services/python-core/tests/test_mlx_worker_client.py
services/python-core/tests/test_runtime_download_shutdown.py
services/python-core/tests/test_tts_mlx_adapters.py
services/python-core/tests/test_tts_model_capabilities.py
```

除整文件删除外，还移除：模型路径/运行时配置字段，模型目录迁移/下载/删除 CLI 参数与 HTTP/desktop bridge，下载子进程管理，旧 worker 进度翻译，递归音频上下文克隆，业务层 `_sentence_spans` / `_merge_short_spans` / `_split_long_spans` 内存切片。没有注释保留旧代码。

保留的 `PodcastAudioAssembler` 是仍被调用的编辑与发布功能：归一化、RMS 匹配、节目段落停顿、片段资产复用及局部重生成。它不再承担模型防 OOM 切片，不是已废弃的 worker 拼接器。

### 移除依赖

- 直接删除 `local-mlx` 可选组及 `mlx`、`mlx-audio[tts]` 声明。
- uv.lock 删除 34 项不再可达的依赖：`annotated-doc`, `charset-normalizer`, `click`, `filelock`, `fsspec`, `hf-xet`, `huggingface-hub`, `jinja2`, `markupsafe`, `mistral-common`, `mlx`, `mlx-audio`, `mlx-lm`, `mlx-metal`, `pillow`, `protobuf`, `pycountry`, `pydantic-extra-types`, `pyyaml`, `regex`, `requests`, `rich`, `safetensors`, `scipy`, `sentencepiece`, `shellingham`, `sounddevice`, `soundfile`, `soxr`, `tiktoken`, `tokenizers`, `transformers`, `typer`, `urllib3`。
- 原始验收时的 Aodcast 编排环境实际检查：`mlx`、`mlx_audio`、`torch`、`transformers`、`funasr` 均未安装。`torch` / `funasr` 原本未声明，不虚报为此次卸载。
- 保留仍用于播客节目音频装配的 NumPy / miniaudio；httpx 为显式轻量依赖，pytest / ruff 为测试可选依赖。

## 4. 改造清单与业务契约

- `app/providers/local_speech/client.py`：统一 TTS / ASR / health HTTP 客户端，读取超时 1800 秒、连接超时 5 秒，服务未启动时提示 `./speech-service/service.sh start`；取消请求会关闭网络连接。
- `provider.py`：保留 `synthesize(TTSGenerationRequest) -> TTSGenerationResponse`；业务音色映射由 adapter 负责，按服务实际模型选择 Qwen / Kokoro 预设。
- `capabilities.py`：声明实际 HTTP 能力及近似停顿，不依赖模型代码。
- Aodcast 原先没有独立 ASR 实现；本次新增 `LocalSpeechClient.transcribe(path, language=None) -> str`，不虚构旧 ASR 函数的迁移。
- `AudioRenderingService` 公开渲染/试听/取消/局部重生成功能签名保留；自然段完整传入服务。明确改选本地预设会解除旧克隆引用，原参考音频资产保留。
- `speech_director.py` 保留编辑段落及源文偏移，删除句长限制；`podcast_rendering.py` 保留不可变资产、哈希、发布与局部重生成。
- 服务实际模型是音色映射与返回元数据的来源；模型切换后 UI 只选择 `ready` 模型，避免保存配置漂移。
- 本地 provider override 不会继承已保存的云端 URL；云端 OpenAI TTS 参数修正为 `response_format` 并采用长读取超时。
- Models / Settings / Workspace / Voice Studio / TypeScript / 共享 schema 同步删除废弃权重管理字段与桥接接口。
- 中英文 README、贡献指南、环境示例、更新日志与 AGENTS 边界同步。

能力限制：当前本机服务仅预设音色、正常语速、WAV。克隆、风格指令、精确毫秒停顿与音频上下文不受支持，UI 明确限制，直接请求不静默丢弃。编辑停顿可用自然标点近似。固定 25 秒 ASR 分块在边界可能拆词，末尾实测原始文本已保留在 results.json 中；短音频闭环为零字符错误。

## 5. 回归与静态检查

- Python：**356 项测试通过、129 个子测试通过**。
- Desktop：**33 项 Vitest 通过**；TypeScript 检查（含 unused locals/parameters）通过；生产构建通过。
- Rust：`cargo check`、`cargo fmt --check` 通过。
- `ruff check`（项目标准 E4/E7/E9/F）及显式 F401/F841 通过，零诊断；清除全库既有未使用 import。
- `git diff --check`、开发/维护 shell 语法通过。
- 原始解耦验收时，编排核心旧推理类、旧模型、失效配置与下载操作检索无残留；该核心中的 `mlx` 仅保留合法服务 HF 模型 ID。现在内置 `speech-service/` 合法持有 MLX 推理实现与依赖，不能将这些必要代码误判为残留。
- 独立语音服务 **32 项单元测试通过**。

复跑：

```bash
# 从 Aodcast 仓库根目录运行
./speech-service/service.sh start
cd services/python-core
uv sync --extra test
uv run --extra test python ../../scripts/verification/verify-local-speech.py
uv run --extra test pytest -q
uv run --extra test ruff check app tests
```

## 6. 内置 speech-service 迁移复验

验证时间：2026-10-15T23:45:20+08:00。

- 最终布局为 `AudioS/Aodcast/speech-service`，旧的两个目录已移除；Git 仓库与远端保留。
- 编排与语音服务分别重建 Python 环境，Rust 的旧绝对路径构建缓存已重新生成；4 份本地路径元数据已重定位并保留原文件备份。
- launchd 标识为 `com.aodcast.speech-service`，工作目录和 Python 路径均指向内置服务；原注册已停用。
- 桌面、Web 和直接 Tauri 开发入口均先启动并确认语音服务健康，再启动外壳。

| 真实验证 | 结果 | 耗时 |
| --- | --- | ---: |
| 短文 TTS | 9.04 秒 WAV / 433,964 字节 | 281.397 秒 |
| ASR 回环 | 正文一致，字符错误率 0.0% | 10.395 秒 |
| 1246 字完整管线 | 1 个业务自然段，11 个推理切片，266.31 秒 WAV / 25,565,804 字节 | 219.827 秒 |
| 结束语识别 | 检出“我们的测试到这里全部结束” | 通过 |

首次 TTS 包含新环境首次导入与冷启动，期间也在重建桌面缓存；该值不能当作稳态合成耗时。此次没有重新下载已缓存权重。服务 RSS 峰值为 2.075 GiB，Metal 生命周期分配峰值为 6.677 GiB，两者不可相加；全程无 OOM 或 HTTP 超时。

迁移后验证：编排核心 357 项测试及 129 个子测试通过；语音服务 32 项测试通过；启动顺序/失败阻断/健康身份 6 项测试通过；前端 33 项测试、类型检查、构建与迁移后 Rust 检查通过。原始日志、WAV 与结果保存在本地 `.local-data/speech-verification/migrated-bundled/`，不随 Git 发布。单元测试中的替身没有用于上述真实语音结果。

## 附录：删除的生产符号

按 AST 比较原版本与当前版本，删除 155 个生产类／函数／方法符号；以下为完整列表（测试文件删除另见上表）。

### `services/python-core/app/api/http_runtime.py`

`RuntimeContext.register_download_process`, `RuntimeContext.shutdown_download_processes`, `RuntimeContext.start_download_model`, `RuntimeContext.start_migrate_model_storage`, `RuntimeContext.unregister_download_process`

### `services/python-core/app/models_catalog.py`

`_base_default_download_base`, `_clear_custom_model_storage_base`, `_copytree_with_progress`, `_default_download_base`, `_directory_size`, `_download_subprocess_env`, `_load_custom_model_storage_base`, `_model_capability`, `_safe_tree_size`, `_storage_config_file`, `_voice_active`, `delete_voice_model`, `download_voice_model`, `expected_voice_model_dir`, `find_external_download_pids`, `migrate_model_storage`, `model_storage_status`, `reset_model_storage`, `save_custom_model_storage_base`, `stop_download_process`, `voice_model_is_downloaded`

### `services/python-core/app/orchestration/audio_rendering.py`

`_local_mlx_voice_for`, `_translate_provider_event`

### `services/python-core/app/orchestration/speech_director.py`

`_merge_short_spans`, `_sentence_spans`, `_split_long_spans`

### `services/python-core/app/providers/audio_utils.py`

`synthesize_sine_wave_bytes`

### `services/python-core/app/providers/tts_local_mlx/adapters/__init__.py`

`adapter_for_model`

### `services/python-core/app/providers/tts_local_mlx/adapters/base.py`

`AdapterRequest`, `AdapterRequest.from_payload`, `AdapterRequest.to_payload`, `MLXTTSAdapter`, `MLXTTSAdapter.__init__`, `MLXTTSAdapter.capabilities`, `MLXTTSAdapter.generate`, `MLXTTSAdapter.generation_kwargs`, `MLXTTSAdapter.prepare_synthesis`, `MLXTTSAdapter.validate_request`, `PreparedSegment`, `PreparedSegment.from_payload`, `PreparedSegment.to_payload`, `PreparedSynthesis`, `canonical_language`, `moss_language`, `normalize_breaks`, `prepare_pcm_pause_synthesis`

### `services/python-core/app/providers/tts_local_mlx/adapters/moss.py`

`MossTTSAdapter`, `MossTTSAdapter.generation_kwargs`, `MossTTSAdapter.prepare_synthesis`, `inject_pause_markers`

### `services/python-core/app/providers/tts_local_mlx/adapters/qwen3.py`

`Qwen3TTSAdapter`, `Qwen3TTSAdapter.generation_kwargs`

### `services/python-core/app/providers/tts_local_mlx/adapters/voxcpm2.py`

`VoxCPM2Adapter`, `VoxCPM2Adapter.generation_kwargs`, `VoxCPM2Adapter.prepare_synthesis`

### `services/python-core/app/providers/tts_local_mlx/capabilities.py`

`CloneMode`, `ModelCapabilities`, `ModelCapabilities.feature_levels`, `SupportLevel`, `TTSModelCapabilityContract`, `TTSModelCapabilityContract.to_dict`, `UnsupportedTTSRequestError`, `capabilities_for_model`, `capability_contract_for_model`, `normalize_clone_mode`, `validate_request_capabilities`

### `services/python-core/app/providers/tts_local_mlx/chunker.py`

`ScriptChunk`, `_enforce_soft_max_length`, `_is_latin`, `_join_with_space`, `_merge_short_sentences`, `_split_on_sentence_boundaries`, `_wrap_long_sentence`, `limit_script_chunks`, `split_script_into_chunks`

### `services/python-core/app/providers/tts_local_mlx/mlx_worker.py`

`MlxTtsWorker`, `MlxTtsWorker.__init__`, `MlxTtsWorker._join_segments`, `MlxTtsWorker._probe_duration_seconds`, `MlxTtsWorker._read_pcm`, `MlxTtsWorker._render_segment_file`, `MlxTtsWorker._should_cancel`, `MlxTtsWorker._silence`, `MlxTtsWorker._synthesize_segment`, `MlxTtsWorker.clear_cancel`, `MlxTtsWorker.load_model`, `MlxTtsWorker.request_cancel`, `MlxTtsWorker.serve`, `MlxTtsWorker.synthesize_job`, `RenderedSegment`, `WorkerJobCancelled`, `_configure_mlx_allocator`, `_emit`, `_main`, `_release_mlx_inference_memory`

### `services/python-core/app/providers/tts_local_mlx/model_spec.py`

`ModelFamily`, `ModelSpec`, `ModelVariant`, `UnsupportedMLXModelError`, `_qwen_spec`, `_remote_model_spec`, `model_spec_from_config`, `model_spec_from_loaded_model`, `read_local_model_config`, `resolve_model_spec`, `validate_loaded_model_spec`

### `services/python-core/app/providers/tts_local_mlx/provider.py`

`LocalMLXTTSProvider`, `LocalMLXTTSProvider.__init__`, `LocalMLXTTSProvider.synthesize`

### `services/python-core/app/providers/tts_local_mlx/runner.py`

`ChunkProgressEvent`, `LocalMLXRunResult`, `MLXAudioRunner`, `MLXAudioRunner.__init__`, `MLXAudioRunner._resolve_output_file`, `MLXAudioRunner.synthesize`, `get_default_worker_client`

### `services/python-core/app/providers/tts_local_mlx/runtime.py`

`LocalMLXCapability`, `LocalMLXCapability.to_dict`, `_compact_process_error`, `_probe_mlx_runtime_bootstrap`, `detect_local_mlx_capability`, `local_model_directory_is_valid`, `resolve_local_model_target`

### `services/python-core/app/providers/tts_local_mlx/worker_client.py`

`MLXWorkerCancelled`, `MLXWorkerError`, `WorkerClient`, `WorkerClient.__init__`, `WorkerClient._close_process_streams`, `WorkerClient._dispatch_event`, `WorkerClient._ensure_worker`, `WorkerClient._finalize_job_on_exit`, `WorkerClient._hard_reset_after_stalled_terminal_event`, `WorkerClient._hard_reset_for_cancellation`, `WorkerClient._hard_reset_worker`, `WorkerClient._reader_loop`, `WorkerClient._restart_worker`, `WorkerClient._send`, `WorkerClient._stop_worker_locked`, `WorkerClient._terminate_process`, `WorkerClient._wait_for_job`, `WorkerClient.is_running`, `WorkerClient.shutdown`, `WorkerClient.synthesize`, `WorkerEvent`, `WorkerEvent.get_int`, `WorkerEvent.get_str`, `_JobContext`, `_build_preexec`, `build_worker_command`, `worker_environment`
