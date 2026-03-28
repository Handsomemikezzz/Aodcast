from __future__ import annotations

import json
from pathlib import Path

from app.domain.provider_config import LLMProviderConfig
from app.domain.tts_config import TTSProviderConfig


class ConfigStore:
    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir

    def bootstrap(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def llm_config_file(self) -> Path:
        return self.config_dir / "llm.json"

    def load_llm_config(self) -> LLMProviderConfig:
        path = self.llm_config_file()
        if not path.exists():
            return LLMProviderConfig()
        payload = json.loads(path.read_text(encoding="utf-8"))
        return LLMProviderConfig.from_dict(payload)

    def save_llm_config(self, config: LLMProviderConfig) -> Path:
        path = self.llm_config_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(config.to_dict(), indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return path

    def tts_config_file(self) -> Path:
        return self.config_dir / "tts.json"

    def load_tts_config(self) -> TTSProviderConfig:
        path = self.tts_config_file()
        if not path.exists():
            return TTSProviderConfig()
        payload = json.loads(path.read_text(encoding="utf-8"))
        return TTSProviderConfig.from_dict(payload)

    def save_tts_config(self, config: TTSProviderConfig) -> Path:
        path = self.tts_config_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(config.to_dict(), indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        return path
