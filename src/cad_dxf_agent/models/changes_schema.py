"""Validation result and change tracking schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Severity(StrEnum):
    """Validation issue severity."""

    WARNING = "warning"
    BLOCKER = "blocker"


class ValidationIssue(BaseModel):
    """A single validation issue found during operation validation."""

    severity: Severity
    message: str
    operation_index: int | None = None
    field: str | None = None


class ValidationResult(BaseModel):
    """Result of validating a set of operations."""

    valid: bool = True
    issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def blockers(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.BLOCKER]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    def add_blocker(self, message: str, operation_index: int | None = None) -> None:
        self.valid = False
        self.issues.append(
            ValidationIssue(
                severity=Severity.BLOCKER,
                message=message,
                operation_index=operation_index,
            )
        )

    def add_warning(self, message: str, operation_index: int | None = None) -> None:
        self.issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                message=message,
                operation_index=operation_index,
            )
        )
