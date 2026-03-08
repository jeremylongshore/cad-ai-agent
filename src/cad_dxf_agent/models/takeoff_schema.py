"""Takeoff report schemas — structured quantity takeoff outputs.

Extends the design_ops TakeoffItem pattern with categorized items,
zone-based area measurements, and linear measurements. Designed for
export to CSV/spreadsheet formats.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class TakeoffCategory(StrEnum):
    """Category of a takeoff item."""

    SYMBOL = "symbol"
    LINEAR = "linear"
    AREA = "area"
    COUNT = "count"
    TEXT_DERIVED = "text_derived"


class TakeoffReportItem(BaseModel):
    """A single takeoff line item with category and evidence."""

    name: str
    category: TakeoffCategory
    quantity: float
    unit: str
    source_layer: str | None = None
    zone_id: str | None = None
    entity_handles: list[str] = Field(default_factory=list)
    notes: str = ""


class TakeoffReport(BaseModel):
    """Aggregate takeoff report with categorized items."""

    items: list[TakeoffReportItem] = Field(default_factory=list)
    total_items: int = 0
    zone_count: int = 0
    entity_count: int = 0

    @property
    def by_category(self) -> dict[str, list[TakeoffReportItem]]:
        """Group items by category."""
        result: dict[str, list[TakeoffReportItem]] = {}
        for item in self.items:
            result.setdefault(item.category.value, []).append(item)
        return result

    def to_csv_rows(self) -> list[list[str]]:
        """Export items as CSV rows (header + data)."""
        rows: list[list[str]] = [
            ["Category", "Name", "Quantity", "Unit", "Layer", "Zone", "Notes"],
        ]
        for item in self.items:
            rows.append(
                [
                    item.category.value,
                    item.name,
                    f"{item.quantity:.2f}"
                    if isinstance(item.quantity, float)
                    else str(item.quantity),
                    item.unit,
                    item.source_layer or "",
                    item.zone_id or "",
                    item.notes,
                ]
            )
        return rows
