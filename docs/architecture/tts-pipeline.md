# TTS Pipeline

## Purpose

This document describes the end-to-end audio rendering pipeline, from the
desktop "Generate" page down to the MLX worker subprocess that produces the
final audio artifact. It complements [local-mlx-tts.md](local-mlx-tts.md), which documents the
MLX capability report and runtime requirements in isolation.

## Components

- `apps/desktop/src/pages/GeneratePage.tsx` - UI that starts renders,
  polls progress, and displays artifacts
- `apps/desktop/src/lib/httpBridge.ts` - HTTP bridge that talks to the
  Python runtime over `localhost`
- `apps/desktop/src/lib/shellOps.ts` - Tauri-only helpers such as
  Reveal in Finder; kept outside the HTTP bridge contract
- `services/python-core/app/api/http_runtime.py` - HTTP endpoints,
  task lifecycle, `run_token` issuance
- `services/python-core/app/orchestration/audio_rendering.py` -
  session state transitions + `on_progress` translation
- `services/python-core/app/providers/tts_local_mlx/runner.py` -
  submits chunked jobs to the worker client and assembles the final
  audio from the worker output
- `services/python-core/app/providers/tts_local_mlx/worker_client.py` -
  owns the persistent worker subprocess, event queue, cancellation
- `services/python-core/app/providers/tts_local_mlx/mlx_worker.py` -
  long-lived MLX subprocess; loads the model once and streams per-chunk
  events on stdout
- `services/python-core/app/providers/tts_local_mlx/chunker.py` -
  sentence-level script splitter (CJK + ASCII aware)

## Flow

```mermaid
graph TD
    subgraph desktopUI[Desktop UI]
        generate[GeneratePage]
        bridge[httpBridge]
        shell[shellOps]
    end

    subgraph pythonCore[python-core HTTP runtime]
        taskApi[/api/v1/tasks/*]
        startRender[start_render_audio worker thread]
        orchestration[AudioRenderingService]
        progressMgr[LongTaskStateManager.set_progress]
    end

    subgraph localWorker[Persistent MLX worker]
        workerClient[WorkerClient singleton]
        workerProcess[mlx_worker subprocess]
        chunker[chunker.py]
    end

    generate -->|renderAudio| bridge
    bridge -->|POST audio:render| startRender
    startRender --> orchestration
    orchestration --> chunker
    orchestration --> workerClient
    workerClient -->|stdin JSON| workerProcess
    workerProcess -->|stdout chunk events| workerClient
    workerClient -->|ChunkProgressEvent| orchestration
    orchestration -->|AudioRenderProgress| progressMgr
    progressMgr --> taskApi
    bridge -->|showTaskState 1s poll| taskApi
    generate -->|revealInFinder| shell
```

## Chunked Synthesis

The input script is split by `split_script_into_chunks` into sentence-level
chunks using CJK and ASCII punctuation. Short fragments are merged into
their neighbour and runs beyond a soft character cap are wrapped at
comma/whitespace boundaries. The resulting chunks are fed one-by-one to
the MLX worker, which emits `chunk_started` and `chunk_done` events for
each sentence. The orchestration layer translates those events into the
0-100 progress percentage shown in the UI.

The worker joins the per-chunk WAV segments into the final container
format before emitting the `done` event, so downstream consumers see
exactly one audio file per render.

## Persistent Worker Lifecycle

- The worker process is launched lazily on the first render and kept
  alive for subsequent renders, amortising model load cost.
- `WorkerClient._restart_worker` is triggered when the model target
  changes, the process has exited, or a cancellation has been escalated
  to a hard kill.
- Environment defaults: `PYTHONUNBUFFERED=1`, `OMP_NUM_THREADS=2`,
  `MKL_NUM_THREADS=2`, `VECLIB_MAXIMUM_THREADS=2`,
  `NUMEXPR_NUM_THREADS=2`. On POSIX the worker also calls
  `os.nice(10)` to reduce scheduling priority.
- Cancellation sends a `{"type":"cancel"}` message over stdin; if the
  worker does not respond within 3 seconds the client terminates and
  replaces it so future renders are not blocked.

## Task State and `run_token`

Every new render generates a UUID stored as `run_token` inside the
request state envelope. The frontend captures the expected token and
ignores polling updates whose `run_token` does not match, eliminating
the "multiple clicks only take effect once" race where a stale
`succeeded` state would otherwise short-circuit a fresh run.

## Progress Reporting

`LongTaskStateManager.set_progress(percent, message)` is the primary
path for chunk-driven updates. Unlike `update_running`, it does not
require monotonic increments because the orchestration layer provides
its own monotonic policy. The previous time-based heartbeat has been
removed for audio rendering.

## Known Constraints

- The worker assumes MLX and `mlx_audio` are available in the same
  Python runtime as the HTTP service. The capability probe in
  `runtime.py` must continue to gate local rendering.
- Reveal in Finder is implemented as a Tauri command; it lives outside
  the HTTP bridge contract because it has no remote counterpart.
