"""Application settings loaded from environment variables."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Settings:
    """Application configuration from environment variables."""

    def __init__(self) -> None:
        self.llm_provider: str = os.getenv("CAD_LLM_PROVIDER", "mock")
        self.llm_model: str | None = os.getenv("CAD_LLM_MODEL")

        # Protected layers (never editable)
        raw_layers = os.getenv("CAD_PROTECTED_LAYERS", "TITLE,TITLEBLOCK,SEAL,REVISION")
        self.protected_layers: list[str] = [
            layer.strip().upper() for layer in raw_layers.split(",") if layer.strip()
        ]

        # AI revision notes
        self.revision_notes_enabled: bool = (
            os.getenv("CAD_REVISION_NOTES_ENABLED", "true").lower() == "true"
        )
        self.revision_notes_layer: str = os.getenv("CAD_REVISION_NOTES_LAYER", "AI_REV_NOTES")

        # Logging
        self.log_level: str = os.getenv("CAD_LOG_LEVEL", "INFO")

        # Local API
        self.api_host: str = os.getenv("CAD_API_HOST", "127.0.0.1")
        self.api_port: int = int(os.getenv("CAD_API_PORT", "8321"))

    def get_api_key(self, provider: str) -> str | None:
        """Retrieve API key for a provider. Never logs the key."""
        key_map = {
            "openai": "CAD_OPENAI_API_KEY",
            "anthropic": "CAD_ANTHROPIC_API_KEY",
            "google": "CAD_GOOGLE_API_KEY",
        }
        env_var = key_map.get(provider)
        if env_var is None:
            return None
        value = os.getenv(env_var)
        if value:
            logger.debug("API key loaded for provider: %s", provider)
        return value

    @property
    def data_dir(self) -> Path:
        return Path.home() / ".cad-dxf-agent"


settings = Settings()
