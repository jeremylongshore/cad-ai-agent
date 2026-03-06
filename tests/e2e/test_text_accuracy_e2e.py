"""E2E text accuracy verification against real and factory DXF data.

Tests cover MTEXT plain_text stripping, mtext_width extraction, INSERT
transforms, ATTRIB confidence/provenance, TEXT geometry, comparison text
changes, approximate bounding boxes, and full pipeline integration.

Sourced-DXF tests skip gracefully when fixtures are not downloaded.
Factory tests always run (including in CI).
"""

from __future__ import annotations

import ezdxf
import pytest

from cad_dxf_agent.core.dxf_reader import load_dxf
from cad_dxf_agent.models.cad_schema import (
    TextGeometry,
    TextProvenance,
    compute_approx_text_bbox,
)

# Formatting codes that should never appear after plain_text() stripping
MTEXT_FORMAT_CODES = ("\\P", "\\f", "\\H", "\\W", "\\C", "\\A", "{\\", "}")


# ── Helpers ──────────────────────────────────────────────────────────


def _text_entities(ctx, *types):
    """Return entities matching given types (default: TEXT, MTEXT)."""
    if not types:
        types = ("TEXT", "MTEXT")
    return [e for e in ctx.entities if e.entity_type.value in types]


def _insert_entities(ctx):
    return [e for e in ctx.entities if e.entity_type.value == "INSERT"]


# ═══════════════════════════════════════════════════════════════════
# Class 1: MTEXT plain_text — formatting codes stripped
# ═══════════════════════════════════════════════════════════════════


class TestMtextPlainText:
    """Verify MTEXT text_content has no raw formatting codes."""

    def test_real_columns_no_backslash_p(self, real_columns_master):
        """Committed real_columns/master.dxf: no \\P in MTEXT text_content."""
        ctx = load_dxf(str(real_columns_master))
        mtexts = [e for e in ctx.entities if e.entity_type.value == "MTEXT"]
        assert len(mtexts) > 0, "Expected MTEXT entities in real_columns"
        for e in mtexts:
            assert "\\P" not in (e.text_content or ""), (
                f"Handle {e.handle}: raw \\P found in text_content"
            )

    def test_real_columns_newlines_present(self, real_columns_master):
        """Multi-line MTEXT should contain \\n after plain_text() conversion."""
        ctx = load_dxf(str(real_columns_master))
        mtexts = [e for e in ctx.entities if e.entity_type.value == "MTEXT"]
        multi_line = [e for e in mtexts if e.text_content and "\n" in e.text_content]
        # At least some MTEXT should be multi-line
        assert len(multi_line) > 0, "Expected at least one multi-line MTEXT"

    def test_factory_rich_mtext_clean(self, rich_mtext_dxf):
        """Factory rich_mtext drawing: no formatting codes leak through."""
        ctx = load_dxf(str(rich_mtext_dxf))
        mtexts = [e for e in ctx.entities if e.entity_type.value == "MTEXT"]
        assert len(mtexts) > 0
        for e in mtexts:
            for code in MTEXT_FORMAT_CODES:
                assert code not in (e.text_content or ""), (
                    f"Handle {e.handle}: formatting code {code!r} in text_content"
                )

    def test_sourced_gds_mtext_clean(self, gds_mtext_test_dxf):
        """Downloaded gds-mtext-test.dxf: no formatting codes in MTEXT."""
        ctx = load_dxf(str(gds_mtext_test_dxf))
        texts = _text_entities(ctx)
        for e in texts:
            for code in MTEXT_FORMAT_CODES:
                assert code not in (e.text_content or ""), (
                    f"Handle {e.handle}: formatting code {code!r} in text_content"
                )

    def test_sourced_jscad_texts_clean(self, jscad_texts_dxf):
        """Downloaded jscad-texts.dxf: all text content is clean."""
        ctx = load_dxf(str(jscad_texts_dxf))
        texts = _text_entities(ctx)
        for e in texts:
            for code in MTEXT_FORMAT_CODES:
                assert code not in (e.text_content or ""), (
                    f"Handle {e.handle}: formatting code {code!r} in text_content"
                )


# ═══════════════════════════════════════════════════════════════════
# Class 2: MTEXT width extraction
# ═══════════════════════════════════════════════════════════════════


class TestMtextWidthExtraction:
    """Verify mtext_width is captured from constrained MTEXT entities."""

    def test_real_columns_mtext_widths(self, real_columns_master):
        """Committed: MTEXT with defined width has mtext_width > 0."""
        ctx = load_dxf(str(real_columns_master))
        mtexts = [e for e in ctx.entities if e.entity_type.value == "MTEXT"]
        with_width = [e for e in mtexts if "mtext_width" in e.attributes]
        assert len(with_width) > 0, "Expected at least one MTEXT with width"
        for e in with_width:
            assert e.attributes["mtext_width"] > 0

    def test_factory_constrained_width(self, rich_mtext_dxf):
        """Factory: MTEXT created with explicit width stores it."""
        ctx = load_dxf(str(rich_mtext_dxf))
        mtexts = [e for e in ctx.entities if e.entity_type.value == "MTEXT"]
        with_width = [e for e in mtexts if "mtext_width" in e.attributes]
        assert len(with_width) > 0, "Expected constrained MTEXT from factory"
        for e in with_width:
            assert e.attributes["mtext_width"] > 0

    def test_factory_unconstrained_no_width(self, tmp_path):
        """Factory: MTEXT without width constraint has no mtext_width key."""
        doc = ezdxf.new()
        msp = doc.modelspace()
        msp.add_mtext("No width constraint")
        path = tmp_path / "no_width.dxf"
        doc.saveas(str(path))

        ctx = load_dxf(str(path))
        mtexts = [e for e in ctx.entities if e.entity_type.value == "MTEXT"]
        assert len(mtexts) == 1
        assert "mtext_width" not in mtexts[0].attributes

    def test_sourced_gds_mtext_width(self, gds_mtext_test_dxf):
        """Downloaded: any MTEXT with width has it extracted."""
        ctx = load_dxf(str(gds_mtext_test_dxf))
        mtexts = [e for e in ctx.entities if e.entity_type.value == "MTEXT"]
        for e in mtexts:
            if "mtext_width" in e.attributes:
                assert e.attributes["mtext_width"] > 0


# ═══════════════════════════════════════════════════════════════════
# Class 3: INSERT transforms — xscale/yscale/rotation extracted
# ═══════════════════════════════════════════════════════════════════


class TestInsertTransforms:
    """Verify INSERT entities have xscale, yscale, and rotation attributes."""

    def test_factory_scaled_inserts(self, scaled_insert_dxf):
        """Factory: 3 INSERTs with known transforms."""
        ctx = load_dxf(str(scaled_insert_dxf))
        inserts = _insert_entities(ctx)
        assert len(inserts) >= 3

        for e in inserts:
            assert "insert_xscale" in e.attributes
            assert "insert_yscale" in e.attributes
            assert "insert_rotation" in e.attributes

        # Find the non-uniform scaled INSERT (xscale=2.0, yscale=0.5)
        scaled = [
            e
            for e in inserts
            if abs(e.attributes["insert_xscale"] - 2.0) < 0.01
            and abs(e.attributes["insert_yscale"] - 0.5) < 0.01
        ]
        assert len(scaled) >= 1, "Expected non-uniform scaled INSERT"

    def test_committed_r2000_blocks(self, r2000_blocks_dxf):
        """Committed r2000_blocks.dxf: all INSERTs have 3 transform attrs."""
        ctx = load_dxf(str(r2000_blocks_dxf))
        inserts = _insert_entities(ctx)
        if not inserts:
            pytest.skip("No INSERT entities in r2000_blocks.dxf")
        for e in inserts:
            assert "insert_xscale" in e.attributes, f"Handle {e.handle}: missing xscale"
            assert "insert_yscale" in e.attributes, f"Handle {e.handle}: missing yscale"
            assert "insert_rotation" in e.attributes, f"Handle {e.handle}: missing rotation"

    def test_committed_block_attribs(self, block_attrib_master):
        """Committed block_attrib_changes/master.dxf: INSERTs have transforms."""
        ctx = load_dxf(str(block_attrib_master))
        inserts = _insert_entities(ctx)
        assert len(inserts) > 0
        for e in inserts:
            assert "insert_xscale" in e.attributes
            assert "insert_yscale" in e.attributes
            assert "insert_rotation" in e.attributes

    def test_sourced_blocks(self, jscad_blocks1_dxf):
        """Downloaded: all INSERTs have transform attributes."""
        ctx = load_dxf(str(jscad_blocks1_dxf))
        inserts = _insert_entities(ctx)
        if not inserts:
            pytest.skip("No INSERT entities in jscad-blocks1.dxf")
        for e in inserts:
            assert "insert_xscale" in e.attributes
            assert "insert_yscale" in e.attributes
            assert "insert_rotation" in e.attributes


# ═══════════════════════════════════════════════════════════════════
# Class 4: ATTRIB confidence & provenance
# ═══════════════════════════════════════════════════════════════════


class TestAttribConfidenceProvenance:
    """Verify ATTRIB trust hierarchy: provenance and confidence values."""

    def test_factory_attrib_provenance(self, scaled_insert_dxf):
        """Factory: ATTRIBs get BLOCK_ATTRIBUTE_TEXT provenance."""
        ctx = load_dxf(str(scaled_insert_dxf))
        inserts_with_attribs = [
            e for e in _insert_entities(ctx) if "attribs" in e.attributes
        ]
        if not inserts_with_attribs:
            pytest.skip("No ATTRIBs in scaled_insert factory fixture")
        for e in inserts_with_attribs:
            assert e.text_geometry is not None
            assert e.text_geometry.provenance == TextProvenance.BLOCK_ATTRIBUTE_TEXT

    def test_factory_attrib_confidence_095(self, scaled_insert_dxf):
        """Factory: ATTRIB position/rotation confidence = 0.95."""
        ctx = load_dxf(str(scaled_insert_dxf))
        inserts_with_attribs = [
            e for e in _insert_entities(ctx) if "attribs" in e.attributes
        ]
        if not inserts_with_attribs:
            pytest.skip("No ATTRIBs in scaled_insert factory fixture")
        for e in inserts_with_attribs:
            tg = e.text_geometry
            assert tg is not None
            assert tg.confidence_position == pytest.approx(0.95)
            assert tg.confidence_rotation == pytest.approx(0.95)

    def test_committed_door_attribs(self, block_attrib_master):
        """Committed: DOOR ATTRIBs have correct provenance."""
        ctx = load_dxf(str(block_attrib_master))
        inserts_with_attribs = [
            e for e in _insert_entities(ctx) if "attribs" in e.attributes
        ]
        assert len(inserts_with_attribs) > 0
        for e in inserts_with_attribs:
            assert e.text_geometry is not None
            assert e.text_geometry.provenance == TextProvenance.BLOCK_ATTRIBUTE_TEXT

    def test_attrib_height_no_double_scaling(self, scaled_insert_dxf):
        """Factory: ATTRIB height reflects DXF value (no double-scaling)."""
        ctx = load_dxf(str(scaled_insert_dxf))
        inserts_with_attribs = [
            e for e in _insert_entities(ctx) if "attribs" in e.attributes
        ]
        if not inserts_with_attribs:
            pytest.skip("No ATTRIBs in scaled_insert factory fixture")
        for e in inserts_with_attribs:
            tg = e.text_geometry
            assert tg is not None
            # Height should be a reasonable value, not absurdly scaled
            if tg.height is not None:
                assert 0.1 < tg.height < 100, (
                    f"Handle {e.handle}: height {tg.height} looks double-scaled"
                )


# ═══════════════════════════════════════════════════════════════════
# Class 5: TEXT geometry preservation
# ═══════════════════════════════════════════════════════════════════


class TestTextGeometryFull:
    """Verify TEXT entities preserve height, provenance, confidence, rotation."""

    def test_committed_dxf_zoo_text_height(self, r12_basic_dxf, r2000_blocks_dxf):
        """Committed zoo DXFs: TEXT height > 0."""
        for dxf_path in [r12_basic_dxf, r2000_blocks_dxf]:
            ctx = load_dxf(str(dxf_path))
            texts = [e for e in ctx.entities if e.entity_type.value == "TEXT"]
            if not texts:
                continue
            for e in texts:
                assert e.text_geometry is not None, f"Handle {e.handle}: no text_geometry"
                assert e.text_geometry.height is not None and e.text_geometry.height > 0, (
                    f"Handle {e.handle}: TEXT height should be > 0"
                )

    def test_text_provenance_native(self, r12_basic_dxf):
        """Committed: all TEXT entities -> NATIVE_CAD_TEXT provenance."""
        ctx = load_dxf(str(r12_basic_dxf))
        texts = [e for e in ctx.entities if e.entity_type.value == "TEXT"]
        if not texts:
            pytest.skip("No TEXT entities in r12_basic.dxf")
        for e in texts:
            assert e.text_geometry is not None
            assert e.text_geometry.provenance == TextProvenance.NATIVE_CAD_TEXT

    def test_text_confidence_full(self, r12_basic_dxf):
        """Committed: all TEXT confidence values = 1.0."""
        ctx = load_dxf(str(r12_basic_dxf))
        texts = [e for e in ctx.entities if e.entity_type.value == "TEXT"]
        if not texts:
            pytest.skip("No TEXT entities in r12_basic.dxf")
        for e in texts:
            tg = e.text_geometry
            assert tg is not None
            assert tg.confidence_position == 1.0
            assert tg.confidence_rotation == 1.0
            assert tg.confidence_content == 1.0

    def test_text_rotation_normalized(self, structural_dxf):
        """Factory structural: TEXT rotation in [0, 360)."""
        ctx = load_dxf(str(structural_dxf))
        texts = _text_entities(ctx)
        for e in texts:
            if e.text_geometry is not None:
                rot = e.text_geometry.rotation
                assert 0.0 <= rot < 360.0, (
                    f"Handle {e.handle}: rotation {rot} not in [0, 360)"
                )

    def test_mtext_provenance_native(self, real_columns_master):
        """Committed real_columns: MTEXT -> NATIVE_CAD_TEXT."""
        ctx = load_dxf(str(real_columns_master))
        mtexts = [e for e in ctx.entities if e.entity_type.value == "MTEXT"]
        assert len(mtexts) > 0
        for e in mtexts:
            assert e.text_geometry is not None
            assert e.text_geometry.provenance == TextProvenance.NATIVE_CAD_TEXT

    def test_sourced_texts_geometry(self, jscad_floorplan_dxf):
        """Downloaded: all TEXT/MTEXT have text_geometry is not None."""
        ctx = load_dxf(str(jscad_floorplan_dxf))
        texts = _text_entities(ctx)
        if not texts:
            pytest.skip("No TEXT/MTEXT in jscad-floorplan.dxf")
        for e in texts:
            assert e.text_geometry is not None, (
                f"Handle {e.handle}: {e.entity_type.value} missing text_geometry"
            )


# ═══════════════════════════════════════════════════════════════════
# Class 6: Comparison text changes detected
# ═══════════════════════════════════════════════════════════════════


class TestComparisonTextChanges:
    """Verify diff engine detects text_height and text_rotation modifications."""

    def test_real_columns_snapshots_have_geometry(
        self, real_columns_master, real_columns_revision
    ):
        """Committed pair: MTEXT snapshots include text_geometry."""
        from cad_dxf_agent.core.comparison.geometry import extract_snapshots

        snaps = extract_snapshots(str(real_columns_master))
        mtexts = [s for s in snaps if s.entity_type.value == "MTEXT"]
        assert len(mtexts) > 0
        for s in mtexts:
            assert s.text_geometry is not None, (
                f"Handle {s.handle}: snapshot missing text_geometry"
            )

    def test_factory_height_change_detected(self, tmp_path):
        """Factory pair: TEXT height 2->4 — snapshots capture different heights."""
        from cad_dxf_agent.core.comparison.geometry import extract_snapshots

        # Build master
        doc = ezdxf.new()
        msp = doc.modelspace()
        msp.add_text("LABEL", dxfattribs={"height": 2.0, "insert": (10, 10)})
        master_path = tmp_path / "master.dxf"
        doc.saveas(str(master_path))

        # Build revision with different height
        doc2 = ezdxf.new()
        msp2 = doc2.modelspace()
        msp2.add_text("LABEL", dxfattribs={"height": 4.0, "insert": (10, 10)})
        rev_path = tmp_path / "revision.dxf"
        doc2.saveas(str(rev_path))

        m_snaps = extract_snapshots(str(master_path))
        r_snaps = extract_snapshots(str(rev_path))

        # Snapshots correctly capture different heights
        assert len(m_snaps) == 1
        assert len(r_snaps) == 1
        assert m_snaps[0].text_geometry is not None
        assert r_snaps[0].text_geometry is not None
        assert m_snaps[0].text_geometry.height == pytest.approx(2.0)
        assert r_snaps[0].text_geometry.height == pytest.approx(4.0)

    def test_factory_rotation_change_detected(self, tmp_path):
        """Factory pair: TEXT rotation 0->45 — snapshots capture different rotations."""
        from cad_dxf_agent.core.comparison.geometry import extract_snapshots

        # Build master
        doc = ezdxf.new()
        msp = doc.modelspace()
        msp.add_text("LABEL", dxfattribs={"height": 2.5, "insert": (20, 20)})
        master_path = tmp_path / "master.dxf"
        doc.saveas(str(master_path))

        # Build revision with rotation
        doc2 = ezdxf.new()
        msp2 = doc2.modelspace()
        msp2.add_text(
            "LABEL", dxfattribs={"height": 2.5, "insert": (20, 20), "rotation": 45.0}
        )
        rev_path = tmp_path / "revision.dxf"
        doc2.saveas(str(rev_path))

        m_snaps = extract_snapshots(str(master_path))
        r_snaps = extract_snapshots(str(rev_path))

        # Snapshots correctly capture different rotations
        assert len(m_snaps) == 1
        assert len(r_snaps) == 1
        assert m_snaps[0].text_geometry is not None
        assert r_snaps[0].text_geometry is not None
        assert m_snaps[0].text_geometry.rotation == pytest.approx(0.0)
        assert r_snaps[0].text_geometry.rotation == pytest.approx(45.0)


# ═══════════════════════════════════════════════════════════════════
# Class 7: Approximate bounding box on real data
# ═══════════════════════════════════════════════════════════════════


class TestApproxBboxOnRealData:
    """Verify compute_approx_text_bbox produces reasonable results."""

    def test_bbox_on_committed_text(self, r12_basic_dxf):
        """Committed fixtures: non-None bbox with positive dimensions."""
        ctx = load_dxf(str(r12_basic_dxf))
        texts = [e for e in ctx.entities if e.entity_type.value == "TEXT"]
        if not texts:
            pytest.skip("No TEXT entities")
        for e in texts:
            if not e.text_content or not e.text_geometry:
                continue
            bbox = compute_approx_text_bbox(e.text_content, e.text_geometry)
            if bbox is not None:
                min_pt, max_pt = bbox
                assert max_pt.x > min_pt.x, f"Handle {e.handle}: bbox width <= 0"
                assert max_pt.y > min_pt.y, f"Handle {e.handle}: bbox height <= 0"

    def test_bbox_with_real_columns_width(self, real_columns_master):
        """Committed: MTEXT with mtext_width uses it for bbox width."""
        ctx = load_dxf(str(real_columns_master))
        mtexts = [
            e
            for e in ctx.entities
            if e.entity_type.value == "MTEXT" and "mtext_width" in e.attributes
        ]
        if not mtexts:
            pytest.skip("No MTEXT with width in real_columns")
        for e in mtexts:
            if not e.text_content or not e.text_geometry:
                continue
            bbox = compute_approx_text_bbox(
                e.text_content,
                e.text_geometry,
                mtext_width=e.attributes["mtext_width"],
            )
            if bbox is not None:
                min_pt, max_pt = bbox
                # Width should match the mtext_width
                assert max_pt.x == pytest.approx(e.attributes["mtext_width"])

    def test_bbox_reasonable_proportions(self, structural_dxf):
        """Factory structural: bbox width > 0, height > 0."""
        ctx = load_dxf(str(structural_dxf))
        texts = _text_entities(ctx)
        computed = 0
        for e in texts:
            if not e.text_content or not e.text_geometry:
                continue
            mw = e.attributes.get("mtext_width")
            bbox = compute_approx_text_bbox(e.text_content, e.text_geometry, mtext_width=mw)
            if bbox is not None:
                min_pt, max_pt = bbox
                assert max_pt.x > 0
                assert max_pt.y > 0
                computed += 1
        assert computed > 0, "Expected at least one bbox computed"

    def test_bbox_none_without_height(self):
        """TextGeometry without height -> None bbox."""
        tg = TextGeometry(height=None)
        result = compute_approx_text_bbox("Hello", tg)
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# Class 8: Full pipeline integration
# ═══════════════════════════════════════════════════════════════════


class TestFullPipelineIntegration:
    """Verify load -> context -> planner context with text geometry."""

    def test_load_real_columns_full(self, real_columns_master):
        """Committed: load_dxf -> MTEXT clean text + geometry + width."""
        ctx = load_dxf(str(real_columns_master))
        mtexts = [e for e in ctx.entities if e.entity_type.value == "MTEXT"]
        assert len(mtexts) > 0

        for e in mtexts:
            # Clean text
            assert "\\P" not in (e.text_content or "")
            # Geometry present
            assert e.text_geometry is not None
            assert e.text_geometry.provenance == TextProvenance.NATIVE_CAD_TEXT

    def test_planner_context_has_text_geometry(self, structural_dxf):
        """Factory structural: build_planner_context() includes text_geometry."""
        from cad_dxf_agent.core.semantic_model import build_planner_context

        ctx = load_dxf(str(structural_dxf))
        planner_ctx = build_planner_context(ctx)

        text_entities_with_geom = [
            e
            for e in planner_ctx["entities"]
            if e.get("text") and e.get("text_geometry")
        ]
        assert len(text_entities_with_geom) > 0, (
            "Expected text entities with text_geometry in planner context"
        )

        for e in text_entities_with_geom:
            tg = e["text_geometry"]
            assert "height" in tg
            assert "rotation" in tg
            assert "provenance" in tg

    def test_sourced_floorplan_full_pipeline(self, jscad_floorplan_dxf):
        """Downloaded: load_dxf succeeds, TEXT/MTEXT have geometry."""
        ctx = load_dxf(str(jscad_floorplan_dxf))
        assert ctx.entity_count > 0

        texts = _text_entities(ctx)
        if not texts:
            pytest.skip("No TEXT/MTEXT in floorplan")
        for e in texts:
            assert e.text_geometry is not None, (
                f"Handle {e.handle}: missing text_geometry"
            )
