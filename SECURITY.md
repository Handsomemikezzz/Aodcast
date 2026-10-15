# Security Policy

Aodcast is an alpha-stage local-first desktop project. It is not yet a hardened packaged application.

## Supported versions

Security fixes are considered for the current `main` branch and tagged alpha releases.

## Reporting a vulnerability

If you find a vulnerability, please do not open a public issue with exploit details. Report it privately to `cxh1210@mail.ustc.edu.cn`, or open a GitHub security advisory if available.

Please include:

- affected commit or release
- operating system and runtime details
- reproduction steps
- impact assessment
- any known mitigations

## API key and local data notice

Aodcast stores provider configuration locally for a local-first workflow. API keys entered by users are managed on the user's machine, and users are responsible for protecting their local environment, backups, shell history, screenshots, and project data directories.

Do not commit `.local-data/`, `.env`, provider configuration files, generated audio, transcripts, or other user data.

## ChatGPT subscription authentication

The ChatGPT subscription provider communicates with the official local Codex app-server. Codex owns browser authentication, credential persistence, and token refresh. Aodcast must not read, copy, log, or return Codex access tokens, refresh tokens, `auth.json`, or browser cookies. Provider status and bridge payloads may contain only non-secret account labels, available model metadata, rate-limit summaries, login URLs, and generated content.

## Bundled speech service

`speech-service/` runs local TTS/ASR in a separate Python 3.12 process, listening on `127.0.0.1:8090` by default. Keep it on loopback; its audio endpoints have no user authentication. Desktop/web launchers start it before the runtime and UI. Closing the UI leaves this shared service running; stop it explicitly with `./speech-service/service.sh stop`.

The current-user LaunchAgent is `com.aodcast.speech-service`, and logs live under `~/Library/Logs/Aodcast/speech-service/`. Protect `speech-service/.env`, Hugging Face tokens/caches, generated audio, transcription results, and local logs. Model weights stay outside the repository in the Hugging Face cache; neither credentials nor weights belong in Git. Model downloads contact the configured Hugging Face endpoint; inference runs locally.
