"""Comparison schemas: geometry snapshots, matching, and diff classification."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, computed_field

from .cad_schema import EntityType, Point2D

# --- Alignment schemas ---


class AlignmentMethod(StrEnum):
    """How two drawings were aligned."""

    identity = "identity"
    translation = "translation"
    rigid = "rigid"
    anchor = "anchor"
    feature = "feature"
    manual = "manual"


class AlignmentConfig(BaseModel):
    """Configuration for the alignment step."""

    enabled: bool = Field(default=False, description="Enable automatic alignment before matching")
    confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence to accept an alignment (0-1)",
    )
    max_residual: float = Field(
        default=1.0,
        gt=0.0,
        description="Maximum RMS residual to accept alignment (drawing units)",
    )
    anchor_layer_patterns: list[str] = Field(
        default_factory=lambda: ["GRID*", "COLUMN*", "AXIS*"],
        description="Layer name glob patterns to search for anchor blocks",
    )
    control_points: list[tuple[tuple[float, float], tuple[float, float]]] | None = Field(
        default=None,
        description=(
            "User-supplied control point pairs for manual alignment. "
            "Each entry is (master_xy, revision_xy). "
            "1 point = translation only, 2+ = rigid via Kabsch."
        ),
    )


class AlignmentAttempt(BaseModel):
    """Record of a single alignment ladder step."""

    method: str = Field(description="Alignment method tried")
    success: bool = Field(description="Whether the method met confidence threshold")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence achieved")


class AlignmentDiagnostics(BaseModel):
    """Detailed diagnostics from an alignment attempt."""

    rms_residual: float = Field(default=0.0, description="RMS residual after alignment")
    overlap_ratio: float = Field(
        default=0.0,
        description="Fraction of master entities with nearby revision (0-1)",
    )
    match_count: int = Field(default=0, description="Point pairs used to compute transform")
    inlier_count: int = Field(default=0, description="Number of inlier pairs (within tolerance)")
    attempts: list[AlignmentAttempt] = Field(
        default_factory=list,
        description="Log of each ladder step: method, success, confidence",
    )


class AlignmentResult(BaseModel):
    """Output of the alignment step."""

    method: AlignmentMethod = Field(description="Method that produced this alignment")
    confidence: float = Field(ge=0.0, le=1.0, description="Overall alignment confidence (0-1)")
    translation: tuple[float, float] = Field(
        default=(0.0, 0.0), description="Translation (tx, ty) applied to revision"
    )
    rotation_deg: float = Field(
        default=0.0, description="Rotation in degrees applied to revision (CCW positive)"
    )
    rotation_center: tuple[float, float] = Field(
        default=(0.0, 0.0), description="Center of rotation"
    )
    diagnostics: AlignmentDiagnostics = Field(default_factory=AlignmentDiagnostics)
    guidance: str | None = Field(
        default=None,
        description="Human-readable guidance when alignment fails or has low confidence",
    )


class GeometrySnapshot(BaseModel):
    """Full geometry capture of one entity from a DXF file."""

    handle: str = Field(description="DXF entity handle (unique within its file)")
    entity_type: EntityType
    layer: str
    points: list[Point2D] = Field(description="All defining points (ordered)")
    text_content: str | None = None
    block_name: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    stable_id: str | None = Field(
        default=None,
        description="Geometry-based stable ID (assigned by assign_stable_ids)",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def centroid(self) -> Point2D:
        """Mean of all defining points."""
        if not self.points:
            return Point2D(x=0.0, y=0.0)
        cx = sum(p.x for p in self.points) / len(self.points)
        cy = sum(p.y for p in self.points) / len(self.points)
        return Point2D(x=cx, y=cy)


class ComparisonConfig(BaseModel):
    """Configuration for a DXF comparison run."""

    tolerance: float = Field(
        default=0.25,
        description="Match threshold in drawing units (1/4 inch default)",
    )
    move_threshold: float = Field(
        default=0.25,
        description="Min displacement to classify as moved vs unchanged",
    )
    ignored_layers: list[str] = Field(default_factory=list)
    focus_entity_types: list[EntityType] | None = Field(
        default=None,
        description="Restrict comparison to these types; None = all",
    )
    use_canonical: bool = Field(
        default=False,
        description="Enable canonical model: stable IDs, deterministic ordering, quantized points",
    )
    alignment: AlignmentConfig = Field(
        default_factory=AlignmentConfig,
        description="Alignment configuration (disabled by default)",
    )


class MatchMethod(StrEnum):
    """How a master-revision pair was matched."""

    fingerprint = "fingerprint"
    signature = "signature"
    spatial = "spatial"


class ChangeCategory(StrEnum):
    """Classification of a single entity change."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    MOVED = "moved"
    UNCHANGED = "unchanged"


class EntityChange(BaseModel):
    """One classified change between master and revision."""

    category: ChangeCategory
    master_snapshot: GeometrySnapshot | None = Field(
        default=None, description="None for ADDED entities"
    )
    revision_snapshot: GeometrySnapshot | None = Field(
        default=None, description="None for REMOVED entities"
    )
    displacement: Point2D | None = Field(default=None, description="dx, dy for MOVED entities")
    modifications: dict[str, Any] | None = Field(
        default=None, description="What changed for MODIFIED entities"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Match confidence (0-1)")
    match_method: MatchMethod | None = Field(
        default=None, description="How master/revision were matched (None for ADDED/REMOVED)"
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """Bounding box (min_x, min_y, max_x, max_y) covering both snapshots."""
        all_pts: list[Point2D] = []
        if self.master_snapshot:
            all_pts.extend(self.master_snapshot.points)
        if self.revision_snapshot:
            all_pts.extend(self.revision_snapshot.points)
        if not all_pts:
            return (0.0, 0.0, 0.0, 0.0)
        min_x, max_x = all_pts[0].x, all_pts[0].x
        min_y, max_y = all_pts[0].y, all_pts[0].y
        for p in all_pts[1:]:
            min_x = min(min_x, p.x)
            max_x = max(max_x, p.x)
            min_y = min(min_y, p.y)
            max_y = max(max_y, p.y)
        return (min_x, min_y, max_x, max_y)


class ScoredMatch(BaseModel):
    """A matched pair with confidence scoring metadata."""

    master: GeometrySnapshot
    revision: GeometrySnapshot
    confidence: float = Field(ge=0.0, le=1.0, description="Match confidence (0-1)")
    method: MatchMethod
    runner_up_score: float | None = Field(
        default=None, description="Score of the next-best candidate (None if no runner-up)"
    )
    ambiguous: bool = Field(
        default=False, description="True when confidence - runner_up_score < 0.1"
    )


class MatchResult(BaseModel):
    """Output of the entity matching step."""

    pairs: list[ScoredMatch] = Field(
        default_factory=list,
        description="Matched (master, revision) pairs with confidence scores",
    )
    master_only: list[GeometrySnapshot] = Field(
        default_factory=list,
        description="Unmatched master entities (candidates for REMOVED)",
    )
    revision_only: list[GeometrySnapshot] = Field(
        default_factory=list,
        description="Unmatched revision entities (candidates for ADDED)",
    )


class ComparisonResult(BaseModel):
    """Full result of comparing two DXF files."""

    changes: list[EntityChange] = Field(default_factory=list)
    summary: dict[str, int] = Field(
        default_factory=lambda: {
            "added": 0,
            "removed": 0,
            "modified": 0,
            "moved": 0,
            "unchanged": 0,
        }
    )
    config: ComparisonConfig = Field(default_factory=ComparisonConfig)
    alignment_result: AlignmentResult | None = Field(
        default=None, description="Alignment result, if alignment was enabled"
    )

    @property
    def total_changes(self) -> int:
        """Count of non-unchanged changes."""
        return (
            self.summary.get("added", 0)
            + self.summary.get("removed", 0)
            + self.summary.get("modified", 0)
            + self.summary.get("moved", 0)
        )


class DiffOverlayLayers:
    """Layer name constants and DXF color codes for diff overlays."""

    ADDED = ("AI_ADDED", 3)  # green
    REMOVED = ("AI_REMOVED", 1)  # red
    MODIFIED = ("AI_MODIFIED", 2)  # yellow
    MOVED = ("AI_MOVED", 4)  # cyan

    ALL = [ADDED, REMOVED, MODIFIED, MOVED]


# --- Revision-apply schemas (E4) ---


class RevisionOpType(StrEnum):
    """Type of operation to apply from a comparison change."""

    MOVE = "move"
    DELETE = "delete"
    ADD = "add"
    MODIFY_GEOMETRY = "modify_geometry"
    MODIFY_TEXT = "modify_text"
    MODIFY_ATTRIBUTES = "modify_attributes"


class RevisionOp(BaseModel):
    """A single reversible operation derived from an EntityChange."""

    op_id: str = Field(description="Unique identifier for this operation")
    op_type: RevisionOpType
    change_index: int = Field(description="Index into ComparisonResult.changes")
    target_handle: str = Field(description="DXF entity handle in the master file")
    target_layer: str = Field(description="Layer of the target entity")
    forward: dict[str, Any] = Field(
        default_factory=dict, description="Parameters for forward (apply) direction"
    )
    reverse: dict[str, Any] = Field(
        default_factory=dict, description="Parameters for reverse (undo) direction"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    match_method: MatchMethod | None = None
    description: str = Field(default="")


class ApprovalStatus(StrEnum):
    """Status of an approval decision for a revision op."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    AUTO_APPROVED = "auto_approved"
    FORCE_APPROVED = "force_approved"


class ApprovalDecision(BaseModel):
    """A user or system decision on a single RevisionOp."""

    op_id: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    reason: str = ""
    decided_at: str | None = Field(default=None, description="ISO-8601 timestamp")


class ApprovalConfig(BaseModel):
    """Thresholds for automatic approval gating."""

    auto_approve_threshold: float = Field(
        default=0.85, ge=0.0, le=1.0, description="Confidence >= this → auto-approved"
    )
    force_required_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Confidence < this → requires force_approve",
    )
    allow_force: bool = Field(
        default=False, description="Whether force_approve is permitted for low-confidence ops"
    )


class ApprovalSet(BaseModel):
    """Collection of approval decisions for a set of RevisionOps."""

    decisions: list[ApprovalDecision] = Field(default_factory=list)
    config: ApprovalConfig = Field(default_factory=ApprovalConfig)

    @property
    def approved_op_ids(self) -> set[str]:
        return {
            d.op_id
            for d in self.decisions
            if d.status
            in (
                ApprovalStatus.APPROVED,
                ApprovalStatus.AUTO_APPROVED,
                ApprovalStatus.FORCE_APPROVED,
            )
        }

    @property
    def rejected_op_ids(self) -> set[str]:
        return {d.op_id for d in self.decisions if d.status == ApprovalStatus.REJECTED}

    @property
    def pending_op_ids(self) -> set[str]:
        return {d.op_id for d in self.decisions if d.status == ApprovalStatus.PENDING}

    def get_decision(self, op_id: str) -> ApprovalDecision | None:
        for d in self.decisions:
            if d.op_id == op_id:
                return d
        return None


class AppliedRevisionOp(BaseModel):
    """Record of a single revision op application attempt."""

    op_id: str
    op_type: RevisionOpType
    success: bool
    description: str = ""
    entity_handle: str | None = None
    error: str | None = None


class ApplyResult(BaseModel):
    """Result of applying a batch of revision ops to a master DXF."""

    run_id: str = Field(description="Unique run identifier")
    applied: list[AppliedRevisionOp] = Field(default_factory=list)
    skipped_count: int = 0
    rejected_count: int = 0
    output_path: str | None = None

    @property
    def success_count(self) -> int:
        return sum(1 for a in self.applied if a.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for a in self.applied if not a.success)

    @property
    def all_succeeded(self) -> bool:
        return len(self.applied) > 0 and all(a.success for a in self.applied)


class RunBundle(BaseModel):
    """Manifest of all artifacts from a revision-apply run."""

    run_id: str
    created_at: str = Field(description="ISO-8601 timestamp")
    master_path: str
    revision_path: str
    updated_master_path: str | None = None
    overlay_path: str | None = None
    changelog_json_path: str | None = None
    changelog_text_path: str | None = None
    apply_result_path: str | None = None
    bundle_dir: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
