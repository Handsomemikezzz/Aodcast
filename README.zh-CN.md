# Aodcast

[![CI](https://github.com/Handsomemikezzz/Aodcast/actions/workflows/ci.yml/badge.svg)](https://github.com/Handsomemikezzz/Aodcast/actions/workflows/ci.yml)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Desktop](https://img.shields.io/badge/desktop-Tauri-blue)
![Backend](https://img.shields.io/badge/backend-Python%203.13-blue)
![License](https://img.shields.io/badge/license-MIT-blue)

[English](README.md) | 简体中文

Aodcast 是一个开源、本地优先的 macOS 桌面应用，用于把一个文本想法或现有 Markdown 文章转成单人播客脚本和最终音频。

应用由 Tauri 桌面壳和本地 Python HTTP runtime 组成。它会引导用户完成访谈、生成可编辑的脚本快照、选择可复用的 Speaker Reference 和语音模型，并通过本地或远程语音 provider 渲染最终音频。

> 当前状态：源码级 alpha。Aodcast 可用于本地开发和验证，但还不是经过完整加固的桌面发行版。Provider key 和生成内容存储在本机；目前没有 macOS Keychain 或专用密钥保险库集成。

## 当前可用能力

- 基于文本主题的访谈式播客创作流程。
- 支持导入本地 `.md` 文件或粘贴 Markdown，通过来源预览、播客化改写或忠实朗读、目标时长、可选来源讨论和版本化替换来创建播客。
- 每个 episode 都可以生成多个独立脚本快照，无论它来自访谈还是 Markdown。
- 脚本生成采用 Podcast Editor 行为，生成干净、适合听觉理解的口播稿，通过句子长短、标点和段落节奏安排呼吸，不人为制造 filler 或舞台指令。
- 内部 Speech Director 为精确的脚本 hash 生成版本化、provider-neutral 的 Speech Plan，包含稳定分段、结构化停顿、重音、发音和表达指导，但主 UI 不暴露这些工程概念。
- 以脚本为核心的 Episode Workspace 支持编辑、上下文内 Voice 与 Delivery 选择、短片段试听、完整音频生成、非破坏式更新、播放和导出。
- Voice Studio 支持内置和用户创建的 Speaker Reference、最长 10 分钟的样本上传/录音、资产试听和 reference 管理；已有 Voice 直接在 Episode 内选择。
- 支持本地 MLX TTS 模型 Adapter，也支持 OpenAI-compatible 远程 provider。本地默认 VoxCPM2 4-bit，同时保留 VoxCPM2 8-bit、MOSS-TTS Local v1.5 与 Qwen3-TTS Base 作为对比路径。
- 通过 Render Manifest 装配 WAV，显式处理停顿、格式/响度一致性、渲染血缘和可复用分段音频资产。
- Models 页面支持本地模型存储、下载、迁移、重置和默认本地语音模型选择。
- Mock LLM provider 可用于无付费 API 的访谈与脚本 smoke test；音频渲染仍需本地 MLX 模型或已配置的远程 TTS provider。
- 可通过官方本地 Codex app-server 使用 ChatGPT 订阅额度，支持浏览器登录、账户模型发现和 Codex 使用窗口展示。
- 开发期本地数据默认存储在 `.local-data/`。

## 截图

### Episodes

从首页创建和管理播客 episode。

![Episodes 列表](images/episodes.png)

### Models

下载、迁移并管理本地 MLX TTS 语音模型。

![Models 模型管理](images/models.png)

后续如需更新截图：运行 `./scripts/dev/run-dev-all.sh`，截取当前界面，以稳定文件名保存到 `images/`，并同步更新 `README.md` 与 `README.zh-CN.md`。请勿包含 API key、本地路径、私人 prompt 或用户数据。

## 环境要求

- macOS，用于运行桌面应用
- Python 3.13+
- `uv`
- Node.js
- `pnpm`
- Rust 和 Cargo
- `curl`、`lsof` 和 `pgrep`，用于开发启动脚本

检查本机工具链：

```bash
./scripts/dev/check-toolchain.sh
```

## 快速启动

在仓库根目录执行：

```bash
cd services/python-core
uv venv .venv
uv pip install --python .venv/bin/python -e .

cd ../../apps/desktop
pnpm install

cd ../..
./scripts/dev/run-dev-all.sh
```

`run-dev-all.sh` 会在 `127.0.0.1:8765` 启动 Python runtime，清理过期开发服务状态，并启动 Tauri 桌面应用。Vite Web 服务地址是 `http://localhost:1420`。

## 第一次 Smoke Test

建议先使用 mock LLM provider。这样无需付费 API 就能验证访谈与脚本主流程。音频渲染使用本地 MLX 引擎，因此渲染前需要安装 `local-mlx` 可选依赖组，并在 Models 中下载语音模型：

```bash
cd services/python-core
uv pip install --python .venv/bin/python -e '.[local-mlx]'
cd ../..
./scripts/dev/run-python-core.sh --configure-llm-provider mock
./scripts/dev/run-python-core.sh --configure-tts-provider local_mlx
./scripts/dev/run-python-core.sh --create-demo-session
./scripts/dev/run-dev-all.sh
```

进入应用后，创建或打开一个 Episode，继续对话、获得 Draft，然后在 Episode Workspace 中试听或生成完整音频。

## Provider 配置

Provider 设置保存在本机 `.local-data/` 下，不应纳入版本控制。

### 开发用 Mock LLM

无需付费 API 时，可先用 mock LLM 做访谈与脚本生成的 smoke test：

```bash
./scripts/dev/run-python-core.sh --configure-llm-provider mock
./scripts/dev/run-python-core.sh --configure-tts-provider local_mlx
```

检查当前 LLM 配置是否可用于访谈和脚本生成：

```bash
./scripts/dev/run-python-core.sh --check-llm-config
```

### 通过 Codex 使用 ChatGPT 订阅

安装官方 Codex CLI，然后在设置中选择 **ChatGPT subscription (via Codex)**：

```bash
npm install -g @openai/codex
```

Aodcast 会启动官方本地 `codex app-server`、打开 ChatGPT 浏览器登录，并发现该账户可用的模型。访谈、总结、脚本、Speech Plan 和记忆调用使用临时 Codex thread，消耗当前账户的 Codex 计划额度。Aodcast 不读取或保存 Codex access/refresh token，也不会静默回退到 API Key 计费。登录状态与同一台机器上的官方 Codex CLI 共享。

设置中还提供一个作用于所有 Codex LLM 任务的全局 **Reasoning effort** 选择器。`Auto` 不发送 turn override，使用所选模型实时报告的默认值；显式档位来自该模型的 `supportedReasoningEfforts`。切换模型后，如果原档位不再受支持，会自动回到 `Auto`。更高强度通常会增加等待时间并更快消耗计划额度。

账户已经通过 `codex login` 登录后，也可以只用 CLI 配置 provider：

```bash
./scripts/dev/run-python-core.sh \
  --configure-llm-provider codex_subscription \
  --llm-model "gpt-5.6-sol" \
  --llm-reasoning-effort auto
```

### OpenAI-Compatible Provider

配置 OpenAI-compatible LLM provider：

```bash
./scripts/dev/run-python-core.sh \
  --configure-llm-provider openai_compatible \
  --llm-base-url "https://api.openai.com/v1" \
  --llm-model "gpt-4o-mini" \
  --llm-api-key "<your-key>"
```

配置 OpenAI-compatible TTS provider：

```bash
./scripts/dev/run-python-core.sh \
  --configure-tts-provider openai_compatible \
  --tts-base-url "https://api.openai.com/v1" \
  --tts-model "gpt-4o-mini-tts" \
  --tts-api-key "<your-key>" \
  --tts-voice "alloy" \
  --tts-audio-format "wav"
```

### 环境变量

正常开发不强制要求 `.env`。`.env.example` 记录了 `AODCAST_HF_MODEL_BASE`、`HF_HUB_CACHE`、`HF_TOKEN`，以及用于让并行 worktree 的 Vite shell 指向独立本地 runtime 的 `VITE_AODCAST_RUNTIME_URL` 等可选变量。如果 Codex 不在 `PATH`、`/opt/homebrew/bin` 或 `/usr/local/bin`，请把 `AODCAST_CODEX_BIN` 设置为官方 Codex 可执行文件的绝对路径。

### 导出 MP3

最终成片仍是 WAV。音频生成后，在成片旁点击 **Export**。MP3 转换要求本机安装 FFmpeg。

- Aodcast 会在 WAV 旁边写出一份 192 kbps 的 MP3，例如 `.local-data/exports/<session-id>/renders/<render-id>/podcast.mp3`。
- Finder 会打开该 MP3，随后可手动上传小宇宙或其他平台。
- Aodcast 不保存平台凭据、不直接上传、不生成 RSS，也不维护远端发布状态。

### Local MLX TTS

Local MLX TTS 是首发能力之一，面向支持的 macOS 机器做本地语音生成；更推荐 Apple Silicon，并预留足够磁盘和统一内存。

安装可选依赖：

```bash
cd services/python-core
uv venv .venv
uv pip install --python .venv/bin/python -e '.[local-mlx]'
cd ../..
```

该依赖组将 `mlx-audio[tts]` 固定为 `0.4.6`，保证模型 Adapter 与 worker 使用经过验证的 TTS API。

默认模型目标：

```text
mlx-community/VoxCPM2-4bit
```

下载模型权重到用户自有目录：

```bash
uv run --with huggingface_hub --with tqdm \
  scripts/model-download/download_tts_model.py \
  --base-dir "${HF_HUB_CACHE:-$HOME/.cache/huggingface/hub}"
```

通用下载脚本默认下载 VoxCPM2 4-bit。下载对比模型时显式传入已登记的仓库，例如：

```bash
uv run --with huggingface_hub --with tqdm \
  scripts/model-download/download_tts_model.py \
  --repo-id OpenMOSS-Team/MOSS-TTS-Local-Transformer-v1.5 \
  --base-dir "${HF_HUB_CACHE:-$HOME/.cache/huggingface/hub}"
```

如果仓库需要认证，可传 `--token` 或在本地设置 `HF_TOKEN`。不要提交 token。

Local MLX 路径受 runtime 能力门控。选择它之前务必先检查：

```bash
./scripts/dev/run-python-core.sh --show-local-tts-capability
```

能力报告是 source of truth，会检查平台、Python 环境、MLX import、模型路径和 bootstrap 行为。每个 Adapter 还会把功能标记为 `native`、`approximated` 或 `unsupported`；runtime 会使用这些声明，但主 Episode UI 不暴露 provider capability 术语。

当前对比集合：

| 模型 | 定位 |
| --- | --- |
| `mlx-community/VoxCPM2-4bit` | 推荐默认（包括 16 GB Mac）；同时支持 Speaker Reference 克隆与风格/韵律 instruction。 |
| `mlx-community/VoxCPM2-8bit` | 面向至少 24 GB 统一内存 Mac 的高内存 VoxCPM2 对比版本。 |
| `OpenMOSS-Team/MOSS-TTS-Local-Transformer-v1.5` | 面向高内存 Mac 的长篇与显式停顿对比。 |
| `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit` | 不带 style instruction 的高质量克隆 baseline。 |
| `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit` | 不带 style instruction、速度更快且内存更低的克隆 baseline。 |

配置 repo-id 模式的 Local MLX：

```bash
./scripts/dev/run-python-core.sh \
  --configure-tts-provider local_mlx \
  --clear-tts-local-model-path
```

或显式指定本地模型目录：

```bash
./scripts/dev/run-python-core.sh \
  --configure-tts-provider local_mlx \
  --tts-local-model-path "${HF_HUB_CACHE:-$HOME/.cache/huggingface/hub}/VoxCPM2-4bit"
```

本地模型目录必须包含真实 MLX 导出和 `.safetensors` 权重。占位目录可用于测试，但不能作为可执行模型包。

Aodcast 会为 VoxCPM2 使用低内存 provider 策略：把文本限制为较短的合成分段，采用模型卡推荐的 7 个 CFM steps，限制异常情况下的音频 patch 数，并在每段之间清理 MLX allocator cache。渲染过程中模型权重仍保持热加载；切换模型时仍只保留一个 worker 进程。

#### 在桌面应用中管理模型存储

桌面端 **Models** 页面是管理本地模型文件的首选方式：

- 显示当前模型存储目录
- 可在 Tauri shell 中用 Finder 打开该目录
- 可修改存储目录并迁移已有 Aodcast 模型目录
- 可重置回默认 cache base
- 显示内联下载进度和可恢复的错误信息

为提升本地代理/VPN 环境下的首次下载可靠性，Aodcast 在应用内管理的 Hugging Face 下载中会禁用 Xet 传输路径，改用直接 HTTP 下载器。

应用会把自定义模型 base 写入本地配置。重置存储会清除这项应用设置；`AODCAST_HF_MODEL_BASE` 或 `HF_HUB_CACHE` 等环境变量仍会影响计算出的默认 base。

CLI 等价命令：

```bash
./scripts/dev/run-python-core.sh --show-model-storage
./scripts/dev/run-python-core.sh --migrate-model-storage /path/to/aodcast-models
./scripts/dev/run-python-core.sh --reset-model-storage
```

#### 用渲染验证

如果只想验证音频路径，可配合 mock LLM：

```bash
./scripts/dev/run-python-core.sh --configure-llm-provider mock
./scripts/dev/run-python-core.sh --create-demo-session
./scripts/dev/run-python-core.sh --configure-tts-provider local_mlx --clear-tts-local-model-path
./scripts/dev/run-python-core.sh --render-audio <session-id>
```

#### Local MLX 说明与限制

- 首次渲染可能较慢，因为 worker 需要加载模型。
- 完整渲染会先创建 Speech Plan，为每个分段生成 WAV 资产，再根据 Render Manifest 装配最终 `podcast.wav`。
- Voice Studio 预览渲染是 pollable long task。预览是临时资产；脚本的克隆来源由所选的持久化 Speaker Reference 决定。
- 当所选模型声明原生支持 Speaker Reference 时可进行音色克隆。用户上传或录制的音频最长 10 分钟，并且必须提供匹配的参考文本。
- MOSS 的 pause marker 只由 Adapter 根据 Speech Plan 的结构化 break 临时生成，绝不会写入脚本正文。
- `.mp4` 仅作为 Speaker Reference 音频容器输入，随后会规范化为 WAV；Aodcast 不生成视频 MP4。

## 开发命令

启动桌面应用和本地 runtime：

```bash
./scripts/dev/run-dev-all.sh
```

只启动 Python runtime：

```bash
./scripts/dev/run-python-core.sh --serve-http --host 127.0.0.1 --port 8765
```

前端检查：

```bash
pnpm --dir apps/desktop check
pnpm --dir apps/desktop test
pnpm --dir apps/desktop build:web
```

Tauri Rust 检查：

```bash
cd apps/desktop/src-tauri
cargo check
```

Python 测试：

```bash
cd services/python-core
uv pip install --python .venv/bin/python -e '.[test]'
.venv/bin/python -m unittest discover -s tests -v
```

仓库 hygiene 检查：

```bash
./scripts/maintenance/run-repo-hygiene-check.sh
```

## 仓库结构

- `apps/desktop`：Tauri UI、React 路由、桌面命令和前端 bridge。
- `services/python-core`：访谈编排、脚本生成、provider 分发、本地存储、artifact 和 HTTP runtime。
- `packages/shared-schemas`：前后端共享 contract schema。
- `scripts`：开发、维护和模型下载脚本。
- `docs`：被 Git 忽略的本地草稿目录（例如 `tmp.md`、`plan.md`）；人读安装说明见 README；Agent 约束见 AGENTS.md。

常用文档：

- [Agent collaboration contract](AGENTS.md)
- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## 数据与隐私

Aodcast 是本地优先应用。开发期间，生成的 session、导入来源快照、脚本、Speech Plan、Render Manifest、Speaker Reference、transcript、音频 artifact、provider 配置和 request-state 文件存储在：

```text
.local-data/
```

该目录已被 Git 忽略，不应提交。

API key 作为本地用户配置保存。Aodcast 目前没有 macOS Keychain 或专用密钥保险库。请保护本地配置文件、shell history、日志、截图、备份、同步目录、生成 transcript 和生成音频。

使用 ChatGPT 订阅时，OAuth 存储和 token 刷新由 Codex 自己管理。Aodcast 只接收账户连接状态、计划标签、模型元数据、额度摘要和生成结果；OAuth token 与浏览器 Cookie 不会进入 Aodcast 配置或 bridge payload。

导入的 Markdown 快照保存在 `.local-data/sessions/<session-id>/source.json`。生成脚本时，规范化文章、生成偏好以及后续来源讨论会发送给用户配置的 LLM provider；如果使用远程 provider，这些内容会离开本机并受相应 provider 条款约束。导入来源不会被转换成 transcript turn，也不会写入 Aodcast 长期记忆；只有用户后续主动输入的对话 turn 在启用记忆时可能成为记忆候选。

长期记忆仅保存在本地。启用后，Aodcast 会把少量可复用的用户知识以 Markdown 文件形式保存在 `.local-data/memory/`，以便采访和脚本在不同 Episode 之间保持一致。记忆是可选的（首次使用会提示），可以按 Episode 或全局关闭，并且可以完整查看和删除。高敏感秘密（密码、API key、支付凭据、完整证件号、精确住址）即使用户要求也永不保存。

不要在公开 issue 或 PR 中提交 API key、私人 prompt、导入来源正文、私人生成内容、本地数据路径、transcript 或音频 artifact。

## 当前范围

Aodcast 当前聚焦本地优先的单人播客创作：

- 平台：macOS 桌面（Tauri）+ 本地 Python orchestration core
- 输入：文本主题，或每个 episode 一个本地/粘贴的 Markdown 来源
- 输出：单人播客脚本 + Episode Workspace 渲染的最终音频
- LLM：Mock、OpenAI-compatible，或通过 Codex 使用 ChatGPT 订阅
- 说话者身份：每个脚本选择一个 provider-neutral Speaker Reference
- TTS：本地 MLX 多模型 Adapter 为首发主路径，同时支持远程 API provider
- 记忆：文件原生、仅本地的跨 Episode 长期用户记忆

当前不包含：语音转文本输入、多主持人格式、强制云端后端依赖。

应用可以服务常见音频后缀，并通过本地解码器或 `ffprobe` 校验上传的 Speaker Reference 时长。压缩音频导出依赖本机转换工具。真正的视频 MP4 输出不在当前范围内。

## 架构与行为说明

以下描述面向人和运维的产品行为。Agent 编码约束见 [AGENTS.md](AGENTS.md)。

### 访谈与脚本软提议

提供脚本生成选项需要内容维度就绪，以及最少用户回答轮数（`MIN_USER_TURNS_FOR_SCRIPT_OFFER`，默认 4）。访谈会继续开放式追问，只把生成脚本作为次级可选动作；只有用户明确结束或选择生成时才进入生成。

### 记忆

长期记忆以文件形式保存在 `.local-data/memory/`。`entries/*.md` 是唯一 source of truth；`catalog.json` 与 `MEMORY.md` 可重建。只有用户发言可成为记忆。访谈/脚本主流程只做只读检索，且不得阻塞于后台记忆工作。

### Podcast Editor 与 Speech Director

Podcast Editor 保持脚本为纯口播正文，同时优化听觉结构、句子长度、标点和段落呼吸；不会加入 provider tag、舞台指令或人为 filler。每次完整渲染开始时，Speech Director 都会为精确的脚本 hash 创建版本化 Speech Plan。脚本一旦编辑，旧 plan 与 render 就会过期，必须先重新完整生成，才能再次局部重生成。

### Desktop bridge 与长任务

UI 通过 desktop HTTP bridge 调用本地 Python runtime。长任务（音频渲染、音色预览、模型迁移/下载等）会持久化可轮询的 `request_state`，暴露进度，支持取消，并用 `run_token` 避免重入后的陈旧 UI 状态。完整渲染与上下文窗口重生成共享脚本级 task id `render_audio:<session_id>:<script_id>`；取消请求必须携带本次 run token，因此不同脚本不会互相冲突。有状态的其他长任务应串行执行，除非明确在测并发。

### Episode Workspace 与 Voice Studio

- Episode Workspace 始终以脚本为主画布；Source 与 Conversation 位于上下文抽屉，Voice 与 Delivery 位于轻量 Inspector，Preview 与完整音频控制位于常驻底部 Dock。
- 完整渲染会保存不可变的分段 WAV 与 Render Manifest，再装配 manifest 指向的最终 WAV；MP3 是该最终成片旁的按需导出。
- Preview 优先使用选中文字，其次使用当前段落或稿件开头，生成一次性试听音频，不会替换当前 Episode 成片。
- 修改脚本、Source、Voice 或 Delivery 后，旧音频仍可播放，并显示 `Audio needs update`，直到新成片成功发布。
- Voice Studio 负责可复用 Speaker Reference 资产；Speaker Reference 只定义“谁在说”。Episode 内直接选择已有 reference，创建与克隆仍在 Voice Studio 完成。
- 内置 reference 音频当前位于 `services/python-core/app/assets/speaker-references/`（纳入版本控制）。用户 metadata 位于 `.local-data/speaker-references/`；上传或录制的音频会规范化为不可变的 48 kHz、单声道、16-bit PCM WAV，并保存到 `.local-data/exports/_speaker_references/`。创建时必须提供匹配的参考文本；系统音频捕获尚不可用。
- Episode Workspace 可在 Advanced 中为下一次完整生成选择已下载且可用的本地模型；生成的 manifest 会冻结该模型和 Adapter pipeline。Speech Plan 与上下文窗口重生成合同保留在内部，不进入主 UI。
- Artifact 音频播放在 Web 与 Tauri 中都走 localhost HTTP 路由 `/api/v1/artifacts/audio`。
- Reveal in Finder 等 Tauri-only 助手不在 HTTP `DesktopBridge` 接口中。

### Local MLX runtime

Local MLX TTS 运行在持久 worker 子进程中；模型在 worker 生命周期内只加载一次，不要把一次性 CLI 生成当作生产路径。VoxCPM2、MOSS 与 Qwen 请求分别经过 family-specific Adapter，provider-neutral orchestration 不持久化任何模型标记。装配阶段把所有分段解码为统一 WAV 格式，每段只做一次边缘淡化；插入计划静音之前，仅根据可听样本匹配 RMS 电平，并对 master 施加 sample-peak 上限，最后写出 `podcast.wav`。以 `./scripts/dev/run-python-core.sh` 与 `--show-local-tts-capability` 为能力门控依据（部分环境即使 import 看似正常，原生 MLX bootstrap 仍可能失败）。应用内 Hugging Face 下载禁用 Xet（`HF_HUB_DISABLE_XET=1`）。

选中 Speaker Reference 后，每个语音分段都会持续把这份不可变引用作为音色身份锚点。VoxCPM2 还可以把上一段音频及其准确文本作为独立的连续性上下文；无法同时组合身份与连续性的模型会保留选中的 Speaker Reference，不再递归地把生成分段当成新的音色来源。

### 开发运维

- `./scripts/dev/run-dev-all.sh` 默认重启 `8765` 上的 Python runtime；只有需要进程连续性时才用 `--reuse-runtime`。
- 音频渲染排障：先看 `/healthz` runtime 元数据，再看 `.local-data/runtime/request-state/*`，最后才查前端 `run_token` 过滤。
- CLI 写后读应串行（`start-interview`、`reply-session`、`generate-script`、`render-audio`、configure/show）；并行读写可能读到陈旧状态。
- 桌面打包验证用 `pnpm --dir apps/desktop tauri:build`（不要在 `--` 后追加 cargo 风格参数）。非交互 DMG 依赖 `CI=true` 跳过 Finder AppleScript 样式。
- 新建脚本先 `chmod +x` 再执行，不要让权限与执行竞态。

## 贡献

欢迎贡献。请保持变更小而可审查；当用户流程、存储形状、provider 配置、runtime 行为或开发流程变化时同步更新文档。

不要提交 `.local-data/`、`.env`、模型权重、生成音频、transcript、虚拟环境、`node_modules`、构建产物或私人凭据。

完整贡献说明见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 安全

如果发现漏洞，请不要在公开 issue 中披露利用细节。请发送到 `cxh1210@mail.ustc.edu.cn`，或按照 [SECURITY.md](SECURITY.md) 的私密报告方式处理。

## License

Aodcast 使用 [MIT License](LICENSE)。
