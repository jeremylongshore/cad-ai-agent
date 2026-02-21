"""Cloud Run Gemini proxy — shields desktop users from GCP credentials.

Desktop app sends requests with a license key. Proxy validates the key,
forwards the request to Vertex AI, and streams the response back. Users
never need GCP credentials or a billing account.

Routes:
    POST /v1/generate   — Forward a generate request to Gemini
    GET  /health        — Health check
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

ALLOWED_LICENSE_KEYS: set[str] = set()
_raw = os.getenv("CAD_ALLOWED_LICENSE_KEYS", "")
if _raw:
    ALLOWED_LICENSE_KEYS = {k.strip() for k in _raw.split(",") if k.strip()}

GCP_PROJECT = os.getenv("CAD_GCP_PROJECT", "")
GCP_LOCATION = os.getenv("CAD_GCP_LOCATION", "us-central1")
DEFAULT_MODEL = os.getenv("CAD_GEMINI_MODEL", "gemini-2.5-flash")

# Rate limiting (per-key, in-memory — good enough for MVP)
MAX_REQUESTS_PER_MINUTE = int(os.getenv("CAD_RATE_LIMIT_RPM", "30"))

app = FastAPI(title="CAD DXF Agent Proxy", version="1.0.0")


# ------------------------------------------------------------------
# Request / response models
# ------------------------------------------------------------------


class GenerateRequest(BaseModel):
    """Proxied Gemini generate request."""

    model: str = Field(default="", description="Model name override")
    contents: list[dict[str, Any]] = Field(description="Gemini contents array")
    system_instruction: str | None = None
    tools: list[dict[str, Any]] | None = None
    generation_config: dict[str, Any] | None = None


# ------------------------------------------------------------------
# In-memory rate limiter
# ------------------------------------------------------------------

_rate_buckets: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(key: str) -> bool:
    """Return True if the key is within the rate limit."""
    now = time.time()
    window = 60.0
    _rate_buckets[key] = [t for t in _rate_buckets[key] if now - t < window]
    if len(_rate_buckets[key]) >= MAX_REQUESTS_PER_MINUTE:
        return False
    _rate_buckets[key].append(now)
    return True


# ------------------------------------------------------------------
# Auth middleware
# ------------------------------------------------------------------


def _validate_license(request: Request) -> str:
    """Extract and validate the license key from the request."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    key = auth[7:].strip()

    if ALLOWED_LICENSE_KEYS and key not in ALLOWED_LICENSE_KEYS:
        raise HTTPException(status_code=403, detail="Invalid license key")

    if not _check_rate_limit(key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return key


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok", "project": GCP_PROJECT}


@app.post("/v1/generate")
async def generate(body: GenerateRequest, request: Request):
    """Forward generate request to Vertex AI Gemini."""
    _validate_license(request)

    try:
        import vertexai
        from vertexai.generative_models import (
            Content,
            FunctionDeclaration,
            GenerativeModel,
            Part,
            Tool,
        )

        vertexai.init(project=GCP_PROJECT, location=GCP_LOCATION)

        model_name = body.model or DEFAULT_MODEL

        # Rebuild tools if provided
        gemini_tools = None
        if body.tools:
            declarations = []
            for tool_group in body.tools:
                for fd in tool_group.get("function_declarations", []):
                    declarations.append(
                        FunctionDeclaration(
                            name=fd["name"],
                            description=fd.get("description", ""),
                            parameters=fd.get("parameters", {}),
                        )
                    )
            if declarations:
                gemini_tools = [Tool(function_declarations=declarations)]

        model = GenerativeModel(
            model_name,
            system_instruction=body.system_instruction,
            tools=gemini_tools,
        )

        # Convert contents to Gemini format
        gemini_contents = []
        for msg in body.contents:
            role = msg.get("role", "user")
            parts_raw = msg.get("parts", [])
            parts = []
            for p in parts_raw:
                if isinstance(p, str):
                    parts.append(Part.from_text(p))
                elif isinstance(p, dict) and "text" in p:
                    parts.append(Part.from_text(p["text"]))
                elif isinstance(p, dict) and "function_call" in p:
                    fc = p["function_call"]
                    parts.append(Part.from_dict({"function_call": fc}))
                elif isinstance(p, dict) and "function_response" in p:
                    fr = p["function_response"]
                    parts.append(
                        Part.from_function_response(
                            name=fr["name"],
                            response=fr["response"],
                        )
                    )
            gemini_contents.append(Content(role=role, parts=parts))

        response = model.generate_content(
            gemini_contents,
            generation_config=body.generation_config,
        )

        # Serialize response
        result = _serialize_response(response)
        return JSONResponse(content=result)

    except ImportError as err:
        raise HTTPException(
            status_code=500,
            detail="google-cloud-aiplatform not installed on proxy",
        ) from err
    except Exception as e:
        logger.error("Gemini proxy error: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}") from e


def _serialize_response(response) -> dict[str, Any]:
    """Convert Gemini response to JSON-serializable dict."""
    candidates = []
    for candidate in response.candidates:
        parts = []
        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                parts.append(
                    {
                        "function_call": {
                            "name": fc.name,
                            "args": dict(fc.args) if fc.args else {},
                        }
                    }
                )
            elif hasattr(part, "text") and part.text:
                parts.append({"text": part.text})
        candidates.append(
            {
                "content": {
                    "role": candidate.content.role,
                    "parts": parts,
                }
            }
        )
    return {"candidates": candidates}
