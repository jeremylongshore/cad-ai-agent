"""Tests for the distribution manifest guard."""

from scripts.verify_dist import find_forbidden_members


def test_generated_frontend_members_are_rejected() -> None:
    names = [
        "cad_dxf_agent-0.13.0/src/cad_dxf_agent/__init__.py",
        "cad_dxf_agent-0.13.0/web/frontend/node_modules/react/index.js",
        "cad_dxf_agent-0.13.0/web/frontend/dist/index.html",
    ]

    assert find_forbidden_members(names) == names[1:]


def test_frontend_source_is_allowed() -> None:
    names = ["cad_dxf_agent-0.13.0/web/frontend/src/App.jsx"]

    assert find_forbidden_members(names) == []
