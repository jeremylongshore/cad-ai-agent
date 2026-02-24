"""Planner error types for timeout and retry exhaustion."""

from __future__ import annotations


class PlannerTimeoutError(Exception):
    """Raised when the planner exceeds its wall-clock timeout."""

    def __init__(self, timeout_seconds: int, message: str | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(message or f"Planner timed out after {timeout_seconds}s")


class PlannerRetryExhaustedError(Exception):
    """Raised when all planner retry attempts have failed."""

    def __init__(self, attempts: int, last_error: Exception | None = None) -> None:
        self.attempts = attempts
        self.last_error = last_error
        msg = f"Planner failed after {attempts} attempt(s)"
        if last_error:
            msg += f": {last_error}"
        super().__init__(msg)
