from __future__ import annotations

import ast
from pathlib import Path


def _overlay_search_source() -> str:
    root = Path(__file__).resolve().parents[1]
    path = root / "integration" / "production_overlay" / "darwinchess" / "search.py"
    return path.read_text(encoding="utf-8")


def test_search_r2_overlay_is_valid_python_and_preserves_production_api():
    source = _overlay_search_source()
    tree = ast.parse(source)
    classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    assert "AlphaBetaSearcher" in classes
    assert "SearchResult" in classes
    assert "Candidate" in classes
    assert "opening_stabilization" in source
    assert "OpeningSearchR2Session" in source


def test_search_r2_overlay_is_search_only_not_an_opening_book():
    source = _overlay_search_source().lower()
    assert "opening_plies" in source
    assert "extra_depth" in source
    # The production overlay may talk about an opening window, but it must not
    # embed known opening move sequences or polyglot book probing.
    assert "book_moves" not in source
    assert "push_san" not in source
    assert "find_book" not in source


def test_search_r2_result_exposes_compute_attribution_fields():
    source = _overlay_search_source()
    assert "engine_revision" in source
    assert "opening_stabilized" in source
    assert "opening_extra_nodes" in source
