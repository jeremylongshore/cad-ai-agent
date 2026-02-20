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

        # OpenTelemetry
        self.otel_enabled: bool = os.getenv("OTEL_ENABLED", "").lower() in ("1", "true", "yes")
        self.otel_exporter: str = os.getenv("OTEL_EXPORTER", "console")
        self.otel_endpoint: str | None = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

        # Logging
        self.log_level: str = os.getenv("CAD_LOG_LEVEL", "INFO")

        # Conversion (V2)
        self.oda_path: str | None = os.getenv("CAD_ODA_PATH")  # auto-detected if None
        self.target_dxf_version: str = os.getenv("CAD_TARGET_DXF_VERSION", "R2010")

        # Rendering (V2)
        self.render_dpi: int = int(os.getenv("CAD_RENDER_DPI", "150"))
        self.render_background: str = os.getenv("CAD_RENDER_BACKGROUND", "white")

        # Gemini / Vertex AI (V2)
        self.gcp_project: str | None = os.getenv("CAD_GCP_PROJECT")
        self.gcp_location: str = os.getenv("CAD_GCP_LOCATION", "us-central1")
        self.gemini_model: str = os.getenv("CAD_GEMINI_MODEL", "gemini-1.5-pro")
        self.gemini_max_retries: int = int(os.getenv("CAD_GEMINI_MAX_RETRIES", "1"))

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
