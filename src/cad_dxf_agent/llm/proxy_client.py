"""Proxy client — routes Gemini requests through a Cloud Run proxy.

Desktop users send requests with a license key instead of GCP credentials.
The proxy (proxy/main.py) handles Vertex AI auth and rate limiting.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from ..models.ops_schema import ChangeSet
from ..models.trace_schema import AgentTurn, PlannerTrace, ToolCall
from ..otel import get_tracer
from ..settings import settings
from .agent_provider import AgentProvider
from .prompt_templates import AGENT_SYSTEM_PROMPT
from .providers import PlannerProvider
from .tool_definitions import ALL_TOOLS
from .tool_executor import ToolExecutor
from .vision_describer import describe_drawing_mock

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

MAX_AGENT_TURNS = 10


class ProxyAgentProvider(PlannerProvider):
    """Agent provider that routes through the Cloud Run proxy.

    Mirrors AgentProvider's tool-use loop but sends requests to the proxy
    endpoint instead of calling Vertex AI directly.
    """

    def __init__(
        self,
        proxy_url: str | None = None,
        license_key: str | None = None,
        model_name: str | None = None,
        image_path: str | Path | None = None,
    ) -> None:
        self._proxy_url = (proxy_url or settings.proxy_url or "").rstrip("/")
        self._license_key = license_key or settings.license_key or ""
        self._model_name = model_name or settings.gemini_model
        self._image_path = image_path

        if not self._proxy_url:
            raise ValueError("CAD_PROXY_URL is required for proxy provider")

    @property
    def name(self) -> str:
        return f"proxy-agent ({self._model_name})"

    @property
    def requires_api_key(self) -> bool:
        return False  # Uses license key, not API key

    def plan(
        self,
        prompt: str,
        drawing_context: dict,
        conversation_history: list[dict] | None = None,
    ) -> ChangeSet:
        """Run tool-use agent loop through the Cloud Run proxy."""
        with tracer.start_as_current_span("cad.proxy_agent_plan") as span:
            span.set_attribute("cad.agent.model", self._model_name)

            context = self._reconstruct_context(drawing_context)
            executor = ToolExecutor(context, settings.protected_layers)

            # Build initial prompt
            initial_prompt = self._build_initial_prompt(prompt, drawing_context)

            # Conversation history for the proxy
            contents: list[dict[str, Any]] = [{"role": "user", "parts": [{"text": initial_prompt}]}]

            # Build tool declarations for the proxy
            tool_declarations = [
                {
                    "function_declarations": [
                        {
                            "name": t["name"],
                            "description": t["description"],
                            "parameters": t["parameters"],
                        }
                        for t in ALL_TOOLS
                    ]
                }
            ]

            turns = 0
            trace_turns: list[AgentTurn] = []
            loop_t0 = time.monotonic()

            while turns < MAX_AGENT_TURNS:
                # Send request to proxy
                response = self._proxy_generate(contents, tool_declarations)
                function_calls = self._extract_function_calls(response)

                if not function_calls:
                    break

                turns += 1
                turn_t0 = time.monotonic()
                span.add_event(f"agent_turn_{turns}", {"tool_count": len(function_calls)})

                # Execute tools locally
                tool_results = []
                traced_calls: list[ToolCall] = []
                for fc in function_calls:
                    tool_name = fc["name"]
                    tool_args = fc["args"]
                    logger.info("Proxy agent tool call [%d]: %s(%s)", turns, tool_name, tool_args)

                    tc_t0 = time.monotonic()
                    try:
                        result = executor.execute(tool_name, tool_args)
                    except KeyError:
                        result = {"error": f"Unknown tool: {tool_name}"}
                    except Exception as e:
                        result = {"error": f"Tool execution failed: {e}"}
                    tc_ms = (time.monotonic() - tc_t0) * 1000

                    traced_calls.append(
                        ToolCall(
                            name=tool_name,
                            args=tool_args,
                            result=result if isinstance(result, dict) else {"value": result},
                            duration_ms=tc_ms,
                        )
                    )
                    tool_results.append({"name": tool_name, "response": result})

                # Add model's function calls to conversation
                model_parts = []
                for fc in function_calls:
                    model_parts.append({"function_call": fc})
                contents.append({"role": "model", "parts": model_parts})

                # Add function responses
                fn_parts = []
                for tr in tool_results:
                    fn_parts.append(
                        {
                            "function_response": {
                                "name": tr["name"],
                                "response": tr["response"],
                            }
                        }
                    )
                contents.append({"role": "function", "parts": fn_parts})

                turn_ms = (time.monotonic() - turn_t0) * 1000
                trace_turns.append(
                    AgentTurn(
                        turn_number=turns,
                        tool_calls=traced_calls,
                        duration_ms=turn_ms,
                    )
                )

            total_ms = (time.monotonic() - loop_t0) * 1000
            span.set_attribute("cad.agent.turns", turns)
            span.set_attribute("cad.agent.ops_count", len(executor.operations))

            trace = PlannerTrace(
                provider_name=self.name,
                total_turns=turns,
                total_duration_ms=total_ms,
                turns=trace_turns,
            )

            changeset = ChangeSet(
                prompt=prompt,
                operations=executor.operations,
                revision_label=f"Proxy agent edit ({turns} turns): {prompt[:50]}",
            )
            changeset.planner_trace = trace
            return changeset

    def _proxy_generate(
        self,
        contents: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Send a generate request to the Cloud Run proxy."""
        import urllib.request

        url = f"{self._proxy_url}/v1/generate"
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"Proxy URL must use http(s): {url}")

        payload = json.dumps(
            {
                "model": self._model_name,
                "contents": contents,
                "system_instruction": AGENT_SYSTEM_PROMPT,
                "tools": tools,
            }
        ).encode()

        req = urllib.request.Request(  # noqa: S310  # nosec B310
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._license_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310  # nosec B310
                result: dict[str, Any] = json.loads(resp.read().decode())
                return result
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            logger.error("Proxy error %d: %s", e.code, body)
            raise RuntimeError(f"Proxy returned {e.code}: {body}") from e

    def _extract_function_calls(self, response: dict) -> list[dict[str, Any]]:
        """Extract function calls from the proxy response."""
        calls = []
        for candidate in response.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "function_call" in part:
                    fc = part["function_call"]
                    calls.append(
                        {
                            "name": fc.get("name", ""),
                            "args": fc.get("args", {}),
                        }
                    )
        return calls

    def _build_initial_prompt(self, prompt: str, drawing_context: dict) -> str:
        """Build the initial message with compact context summary."""
        parts = []

        if self._image_path:
            try:
                description = describe_drawing_mock()
                parts.append(f"DRAWING VISUAL DESCRIPTION:\n{description}\n")
            except Exception as e:
                logger.warning("Vision description failed: %s", e)

        # Compact summary instead of full entity JSON
        compact = AgentProvider._build_compact_summary(drawing_context)
        parts.append(compact)
        parts.append(f"USER REQUEST:\n{prompt}")

        return "\n".join(parts)

    def _reconstruct_context(self, drawing_context: dict) -> Any:
        """Reconstruct DrawingContext from the planner dict."""
        from ..models.cad_schema import (
            DrawingContext,
            EntityRef,
            EntityType,
            LayerRule,
            Point2D,
        )

        entities = []
        for e in drawing_context.get("entities", []):
            try:
                point = None
                if e.get("insert_point"):
                    point = Point2D(x=e["insert_point"]["x"], y=e["insert_point"]["y"])
                entities.append(
                    EntityRef(
                        handle=e["handle"],
                        entity_type=EntityType(e["type"]),
                        layer=e["layer"],
                        insert_point=point,
                        text_content=e.get("text"),
                        block_name=e.get("block_name"),
                    )
                )
            except (KeyError, ValueError):
                continue

        layers = [
            LayerRule(name=lyr["name"], protected=lyr.get("protected", False))
            for lyr in drawing_context.get("layers", [])
        ]

        return DrawingContext(
            file_path=drawing_context.get("file_path", ""),
            entities=entities,
            layers=layers,
            blocks=drawing_context.get("blocks", []),
        )
