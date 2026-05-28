"""Configuration management — JSON file-based settings."""

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = PROJECT_ROOT / "config" / "config.json"

DEFAULT_CONFIG = {
    "api_key": "",
    "llm_model": "qwen-plus",
    "transcription_mode": "audio",  # audio / subtitle / auto
    "asr_engine": "whisper",
    "whisper_model": "small",
    "aliyun_asr_app_key": "",
    "aliyun_asr_access_key_id": "",
    "aliyun_asr_access_key_secret": "",
    "aliyun_asr_dialect": "",
    "download_mode": "playwright",
    "use_llm": True,
    "keep_audio": False,
    "output_dir": str(PROJECT_ROOT / "output"),
    "cookies_file": "",
    "system_prompt": "",
    "user_template": "",
}


class Config:
    """Application configuration. Persisted as JSON."""

    def __init__(self):
        self.data = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        """Load from config.json, merge with defaults."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # Merge: saved values override defaults
                self.data = {**DEFAULT_CONFIG, **saved}
            except (json.JSONDecodeError, OSError):
                pass  # fall back to defaults

    def save(self):
        """Persist current config to config.json."""
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value):
        self.data[key] = value

    @property
    def output_dir(self) -> Path:
        return Path(self.data.get("output_dir", str(PROJECT_ROOT / "output")))

    @property
    def api_key(self) -> str:
        return self.data.get("api_key", "") or os.environ.get("DASHSCOPE_API_KEY", "")
