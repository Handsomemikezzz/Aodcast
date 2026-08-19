from __future__ import annotations

from dataclasses import dataclass

from app.domain.artifact import ArtifactRecord
from app.domain.episode_source import EpisodeSource
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord
from app.domain.transcript import TranscriptRecord


@dataclass(slots=True)
class SessionProject:
    session: SessionRecord
    source: EpisodeSource | None = None
    transcript: TranscriptRecord | None = None
    script: ScriptRecord | None = None
    artifact: ArtifactRecord | None = None
