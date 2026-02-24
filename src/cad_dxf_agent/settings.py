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

        # Vision pipeline (render DXF → PNG → Gemini vision → text description)
        self.vision_enabled: bool = os.getenv("CAD_VISION_ENABLED", "true").lower() == "true"

        # Rendering (V2)
        self.render_dpi: int = int(os.getenv("CAD_RENDER_DPI", "150"))
        self.render_background: str = os.getenv("CAD_RENDER_BACKGROUND", "white")

        # Planner timeout / retry
        self.planner_timeout: int = int(os.getenv("CAD_PLANNER_TIMEOUT", "60"))
        self.planner_max_retries: int = int(os.getenv("CAD_PLANNER_MAX_RETRIES", "2"))
        self.planner_retry_delay: float = float(os.getenv("CAD_PLANNER_RETRY_DELAY", "1.0"))
        self.planner_max_validation_retries: int = int(
            os.getenv("CAD_PLANNER_MAX_VALIDATION_RETRIES", "2")
        )

        # LLM generation parameters
        self.llm_temperature: float = float(os.getenv("CAD_LLM_TEMPERATURE", "0.0"))
        self.llm_top_p: float | None = float(v) if (v := os.getenv("CAD_LLM_TOP_P")) else None
        self.llm_top_k: int | None = int(v) if (v := os.getenv("CAD_LLM_TOP_K")) else None
        self.llm_max_output_tokens: int = int(os.getenv("CAD_LLM_MAX_OUTPUT_TOKENS", "4096"))

        # Gemini / Vertex AI (V2)
        self.gcp_project: str | None = os.getenv("CAD_GCP_PROJECT")
        self.gcp_location: str = os.getenv("CAD_GCP_LOCATION", "us-central1")
        self.gemini_model: str = os.getenv("CAD_GEMINI_MODEL", "gemini-2.5-flash")
        self.vision_model: str = os.getenv("CAD_VISION_MODEL", "gemini-2.5-flash")
        self.gemini_max_retries: int = int(os.getenv("CAD_GEMINI_MAX_RETRIES", "1"))

        # Cloud Run proxy (optional — lets users skip GCP credentials)
        self.proxy_url: str | None = os.getenv("CAD_PROXY_URL")
        self.license_key: str | None = os.getenv("CAD_LICENSE_KEY")

        # Edit history
        self.max_undo_snapshots: int = int(os.getenv("CAD_MAX_UNDO_SNAPSHOTS", "50"))

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
