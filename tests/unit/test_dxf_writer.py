"""Tests for dxf_writer — save-as and copy operations."""

from __future__ import annotations

import ezdxf

from cad_dxf_agent.core.dxf_writer import copy_dxf_for_editing, save_as_new_dxf


class TestSaveAsNewDxf:
    def test_save_as_new_dxf_succeeds(self, sample_dxf, tmp_path):
        """Save-as creates a valid new DXF at the output path."""
        output = tmp_path / "output" / "result.dxf"
        result = save_as_new_dxf(sample_dxf, output)

        assert result == output
        assert output.exists()
        # Verify it's a valid DXF
        doc = ezdxf.readfile(str(output))
        assert doc is not None

    def test_save_as_same_path_raises_valueerror(self, sample_dxf):
        """Overwriting the source file is blocked."""
        import pytest

        with pytest.raises(ValueError, match="must differ"):
            save_as_new_dxf(sample_dxf, sample_dxf)

    def test_save_as_creates_parent_dirs(self, sample_dxf, tmp_path):
        """Nested output directories are created automatically."""
        output = tmp_path / "deep" / "nested" / "dir" / "out.dxf"
        assert not output.parent.exists()

        result = save_as_new_dxf(sample_dxf, output)
        assert result.exists()

    def test_save_as_preserves_entities(self, sample_dxf, tmp_path):
        """Round-trip: saved DXF retains the same entities."""
        output = tmp_path / "round_trip.dxf"
        save_as_new_dxf(sample_dxf, output)

        original = ezdxf.readfile(str(sample_dxf))
        saved = ezdxf.readfile(str(output))

        orig_count = len(list(original.modelspace()))
        saved_count = len(list(saved.modelspace()))
        assert saved_count == orig_count

    def test_save_as_does_not_modify_source(self, sample_dxf, tmp_path):
        """Source file bytes are unchanged after save-as."""
        original_bytes = sample_dxf.read_bytes()
        output = tmp_path / "out.dxf"
        save_as_new_dxf(sample_dxf, output)
        assert sample_dxf.read_bytes() == original_bytes


class TestCopyDxfForEditing:
    def test_copy_round_trip(self, sample_dxf, tmp_path):
        """Copy produces a byte-identical working copy."""
        work = tmp_path / "work.dxf"
        result = copy_dxf_for_editing(sample_dxf, work)

        assert result == work
        assert work.exists()
        assert work.read_bytes() == sample_dxf.read_bytes()

    def test_copy_same_path_raises(self, sample_dxf):
        """Copying to the same path is blocked."""
        import pytest

        with pytest.raises(ValueError, match="must differ"):
            copy_dxf_for_editing(sample_dxf, sample_dxf)
