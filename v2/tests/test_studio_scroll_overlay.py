from __future__ import annotations

from pathlib import Path

from integration.production_overlay.install_on_copy import patch_studio_app


SAMPLE_APP = '''from .pages.evolution import EvolutionPage\n\n\nclass MainWindow:\n    def __init__(self):\n        self.resize(1380, 900)\n        self.setMinimumSize(1080, 720)\n        self.pages = [\n            ("Dashboard", object()),\n            ("Evolution", EvolutionPage(self.process)),\n            ("Research", object()),\n        ]\n'''


def test_studio_patch_wraps_dense_pages_and_enlarges_window() -> None:
    patched = patch_studio_app(SAMPLE_APP)

    assert "from .pages.dynasty import DynastyPage" in patched
    assert "from .scroll_host import scroll_page" in patched
    assert 'scroll_page(EvolutionPage(self.process), min_content_height=1220)' in patched
    assert 'scroll_page(DynastyPage(), min_content_height=1080)' in patched
    assert "self.resize(1500, 940)" in patched
    assert "self.setMinimumSize(1100, 720)" in patched


def test_studio_patch_is_idempotent() -> None:
    once = patch_studio_app(SAMPLE_APP)
    twice = patch_studio_app(once)
    assert twice == once


def test_scroll_host_uses_outer_vertical_scroll_area() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / "integration" / "production_overlay" / "studio" / "scroll_host.py"
    text = source.read_text(encoding="utf-8")

    assert "QScrollArea" in text
    assert "setWidgetResizable(True)" in text
    assert "ScrollBarAlwaysOff" in text
    assert "ScrollBarAsNeeded" in text
    assert "setMinimumHeight" in text
