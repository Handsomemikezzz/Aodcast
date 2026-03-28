from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    data_dir: Path

    @classmethod
    def from_cwd(cls, cwd: Path | None = None) -> "AppConfig":
        project_root = (cwd or Path.cwd()).resolve()
        data_dir = project_root / ".local-data"
        return cls(project_root=project_root, data_dir=data_dir)
