# Aodcast speech-service

Aodcast 内置的 Apple Silicon 原生 TTS/ASR 服务，面向 16GB 统一内存设备。源码随 Aodcast 发布，模型推理以独立 FastAPI 进程运行，与 Python 编排核心通过 HTTP 解耦，不使用 Docker。

```text
Aodcast/
├── speech-service/
│   ├── pyproject.toml / uv.lock         # 独立依赖，Python 3.12
│   ├── .env.example                    # 模型、镜像与内存配置
│   ├── speech_server/
│   │   ├── config.py                   # 在导入模型库前读取 .env
│   │   ├── text.py                     # 两级中文切片
│   │   ├── audio.py                    # 静音裁剪、交叉淡化、增量 WAV
│   │   ├── engine.py                   # 串行 GPU 推理、ASR 与卸载
│   │   └── app.py                      # HTTP API 与请求保护
│   ├── launchd/com.aodcast.speech-service.plist.template
│   ├── service.sh                     # start / stop / restart / status / logs
│   └── tests/
├── services/python-core/               # Python 3.13+，仅 HTTP 语音客户端
└── scripts/dev/run-dev-all.sh           # 先启动语音，再 runtime 和桌面壳
```

## 安装与配置

安装 `uv` 与 FFmpeg（例如 `brew install uv ffmpeg`）。从 Aodcast 仓库根目录执行：

```bash
cd speech-service
uv sync --frozen
cp .env.example .env
```

`uv` 根据 `.python-version` 管理原生 arm64 Python 3.12。此目录的 `.venv` 与 `services/python-core/.venv` 相互隔离；不要合并依赖。MLX、mlx-audio、FastAPI、SoundFile 等版本由 `uv.lock` 固定。

默认模型与音色：

```dotenv
TTS_MODEL=mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit
ASR_MODEL=mlx-community/Qwen3-ASR-0.6B-8bit
TTS_VOICE=Vivian
TTS_LANGUAGE=Chinese
```

声音克隆固定提供两个 Qwen3 TTS Base 模型，按请求选择，无需改 `.env`：`mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit`（默认）与 `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit`。首次使用前需在 Hugging Face 缓存中存在对应权重（默认 `HF_HUB_OFFLINE=1`，可临时关闭离线模式或用镜像下载）。

国内镜像可在 `speech-service/.env` 启用 `HF_ENDPOINT=https://hf-mirror.com`。服务先读环境再导入 Hugging Face 库；修改后需重启。权重按需下载到仓库外的 Hugging Face 缓存，已有匹配缓存会复用；空闲卸载不删除缓存。不要提交 `.env`、token、权重、虚拟环境、音频或日志。

可选 Kokoro 为较小的 bf16 模型。先在此目录执行 `uv sync --frozen --extra kokoro`，然后在 `.env` 同时设置：

```dotenv
TTS_MODEL=mlx-community/Kokoro-82M-bf16
TTS_VOICE=zf_xiaobei
TTS_LANGUAGE=z
```

## 启动与关闭

安装全部项目依赖后，在 Aodcast 仓库根目录执行：

```bash
./scripts/dev/run-dev-all.sh
```

启动器按顺序启动语音服务、等待 `GET http://127.0.0.1:8090/health` 就绪、启动 `8765` 上的编排 runtime，最后启动 Tauri/Vite `1420`。`run-web-with-runtime.sh` 使用相同顺序。健康检查不加载模型，首次 TTS/ASR 才懒加载。

只管理语音服务时，从仓库根目录执行：

```bash
./speech-service/service.sh start
./speech-service/service.sh status
./speech-service/service.sh logs
./speech-service/service.sh restart
./speech-service/service.sh stop
```

`start` 安装并启用当前用户的 `~/Library/LaunchAgents/com.aodcast.speech-service.plist`，包括后续登录启动和异常退出重启。`stop` 注销并禁用它，再次 `start` 可恢复。脚本根据当前仓库位置生成路径，不依赖固定的个人目录。无需管理员权限。

关闭桌面壳或在开发启动器按 `Ctrl+C` 不会停止共享语音进程；需要时显式 `stop`。日志目录为 `~/Library/Logs/Aodcast/speech-service/`。这是登录用户的 LaunchAgent，Mac 休眠期间不推理。

前台排查时，先停止后台服务以释放端口，再从 `speech-service/` 执行 `uv run --frozen python -m speech_server`。必须保持一个进程、一个 Uvicorn worker，不能用多 worker 绕过单进程 GPU 锁。

## HTTP 契约

默认 `127.0.0.1:8090`，可由服务 `.env` 的 `HOST` / `PORT` 调整。以下示例在仓库根目录运行，测试音频写入已忽略的本地数据目录。

```bash
mkdir -p .local-data/speech-smoke
curl --fail-with-body --max-time 1800 \
  http://127.0.0.1:8090/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"input":"你好，欢迎收听今天的播客。","voice":"默认中文音色","response_format":"wav"}' \
  --output .local-data/speech-smoke/speech.wav

curl --fail-with-body --max-time 1800 \
  http://127.0.0.1:8090/v1/audio/transcriptions \
  -F 'file=@.local-data/speech-smoke/speech.wav' \
  -F 'model=whisper-1' -F 'language=zh' -F 'response_format=json'

curl --fail-with-body http://127.0.0.1:8090/health
```

- `POST /v1/audio/speech`：JSON `input`、`voice`、`response_format=wav`，返回 PCM16 单声道 WAV。`默认中文音色` / `default` 映射到配置音色，Qwen 也支持 `Vivian`、`Serena` 等实际内置 speaker。`seed` 默认 42。`model` 可省略或使用配置 ID、`tts-1`、`tts-1-hd`。`X-TTS-Chunks` 表示推理切片数。
- `POST /v1/audio/speech/clone`：零样本声音克隆。multipart 字段 `reference`（wav/mp3/m4a 参考录音）、`reference_text`（参考录音的准确逐字稿）、`input`、可选 `model`（两个 Base 模型之一，默认 0.6B）、`language`（`zh` 等代码或 Qwen 语言名，默认自动）、`seed`。服务把参考音频解码为 24 kHz 单声道并裁剪首尾静音，有效语音须在 `CLONE_MIN_REFERENCE_SECONDS`～`CLONE_MAX_REFERENCE_SECONDS`（默认 3～30 秒）之间，否则返回 422。每个推理切片都以同一份参考音频与逐字稿做 ICL 条件，参考越长，每片预填充与解码越慢；返回格式与 `/v1/audio/speech` 相同。
- `POST /v1/audio/transcriptions`：multipart `file` 支持 WAV/MP3/M4A，经 FFmpeg 转为 16kHz mono PCM；JSON 返回 `{"text":"识别结果"}`，`response_format=text` 可返回纯文本。`model=whisper-1` 是路由别名，实际使用配置的 Qwen3-ASR。`language=zh` 等常用语言代码会映射成模型语言名；省略时自动检测。
- `GET /health`：返回模型 ID 和 `loaded` 状态（`models.clone` 列出克隆模型，`clone_reference` 给出参考语音时长窗口）、`busy` / `waiting`、实时进程 RSS、系统可用内存，以及工作线程最近边界采样的 Metal active/cache/peak。`status=ok` 仅表示 HTTP 可用，首次请求前 `loaded=false` 正常。

当前支持预设音色、Qwen3 Base 参考录音零样本克隆、WAV、正常语速 `1.0` 和转写；不支持微调、声音转换、风格、精确停顿或前文音频条件，不支持的请求明确报错。ASR 默认按 25 秒块串行识别，不提供字级时间戳或说话人分离，边界可能拆词。客户端读取超时应至少 180 秒，Aodcast 使用 1800 秒。

## 长文本与内存保护

Aodcast 将完整自然段交给服务，服务独占防 OOM 切片职责；业务侧保留 Speech Plan 和 Render Manifest 作为编辑与发布资产。

- 按换行与 `。！？；` 切分，短于 20 字向后合并，超过 120 字优先在 `，、` 二次切分，无合适标点时按长度切分。目标 80～120 字，硬上限 120；原文总长度或段落边界无法满足下限时允许短片，不补字、不重复正文。
- 所有 TTS/ASR 请求共享 `Semaphore(1)` 与 GPU `Lock`，整个请求在同一个专用工作线程中串行推理。每片使用固定音色/Seed，裁剪边缘静音、保留 20ms 保护区，片间做 10ms 交叉淡化，段落间插入 300ms 停顿。
- 音频逐段增量写临时 WAV，只保留当前切片及短尾缓冲；响应结束删除临时文件。取消在安全片段边界停止，底层任务结束前不释放 GPU 锁。
- 默认只驻留一个模型；切换预设 TTS、克隆模型或 ASR 时卸载其他模型（比较 0.6B 与 1.7B 时会重新加载）。MLX 分配器默认限 8GiB，缓存 256MiB，系统可用内存低于 2GiB 拒绝新推理；切片与请求边界清理缓存和垃圾回收。这些上限不是整个进程 RSS 上限，也不保证其他高内存进程并发时绝无 OOM。
- 无请求且无排队任务连续 900 秒后卸载模型，检测周期不超过 30 秒，下次请求懒加载。轮询 `/health` 也会重置空闲计时。卸载后 Python/HTTP 进程仍占用内存，RSS 不会归零。
- 默认文字上限 20,000 字、上传 100MiB、音频 3600 秒；最多 4 个进行中/排队请求，超出返回 429，GPU 排队超过 300 秒返回 503。原始请求体在解析前限长，FFmpeg 转码有 120 秒超时。达到单片解码 token 上限会返回错误，避免发布截断音频。

完整可调参数见 [.env.example](.env.example)。音色和 Seed 不保证跨片韵律完全一致；静音裁剪与交叉淡化不能修复模型自身发音错误。

## 验证

从本目录执行：

```bash
uv sync --frozen
uv run --frozen pytest -q
uv run --frozen ruff check speech_server tests
bash -n service.sh
```

上述模型替身测试验证切片、并发、取消与空闲卸载，不代表真实推理或音质验证；格式解码测试会使用真实 FFmpeg。

服务运行后，从 Aodcast 的 `services/python-core/` 执行真实 TTS→ASR 与 1246 字节目管线复跑：

```bash
uv run --extra test python ../../scripts/verification/verify-local-speech.py
uv run --extra test python ../../scripts/verification/verify-local-clone.py
```

克隆验证默认先用预设模型生成一段逐字稿已知的参考音频，再分别用两个 Base 模型做短句克隆（ASR 回环计算字错率）、多段完整节目渲染和上下文窗口重渲染。使用朋友的真实录音时追加 `--reference /path/to/friend.wav --reference-text "准确逐字稿"`。

输出写入本机 `.local-data/speech-verification/<timestamp>/`，不随 Git 发布。此前 2026-10-15 的量化模型真机实测摘要见根目录 [README](../README.zh-CN.md)。

上游：[MLX Audio](https://github.com/Blaizzy/mlx-audio)。
