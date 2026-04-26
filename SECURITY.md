# Security Policy

Aodcast is an alpha-stage local-first desktop project. It is not yet a hardened packaged application.

## Supported versions

Security fixes are considered for the current `main` branch and tagged alpha releases.

## Reporting a vulnerability

If you find a vulnerability, please do not open a public issue with exploit details. Report it privately to the maintainers through the repository owner's preferred private contact channel, or open a GitHub security advisory if available.

Please include:

- affected commit or release
- operating system and runtime details
- reproduction steps
- impact assessment
- any known mitigations

## API key and local data notice

Aodcast stores provider configuration locally for a local-first workflow. API keys entered by users are managed on the user's machine, and users are responsible for protecting their local environment, backups, shell history, screenshots, and project data directories.

Do not commit `.local-data/`, `.env`, provider configuration files, generated audio, transcripts, or other user data.
