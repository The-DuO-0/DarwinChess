from __future__ import annotations

from pathlib import Path

from v2.integration.production_overlay.install_on_copy import patch_studio_app


def test_patch_studio_app_adds_scrollable_dynasty_once() -> None:
    original = '''from .pages.dashboard import DashboardPage\nfrom .pages.evolution import EvolutionPage\nfrom .pages.play import PlayPage\n\nclass MainWindow:\n    def setup(self):\n        self.resize(1380, 900)\n        self.setMinimumSize(1080, 720)\n        self.pages = [\n            ("Dashboard", DashboardPage(self.agent, self.process)),\n            ("Evolution", EvolutionPage(self.process)),\n            ("Research", ResearchPage(self.process)),\n        ]\n'''
    patched = patch_studio_app(original)
    assert "from .pages.dynasty import DynastyPage" in patched
    assert "from .scroll_host import scroll_page" in patched
    assert '("Evolution", scroll_page(EvolutionPage(self.process), min_content_height=1220)),' in patched
    assert '("Dynasty Archive", scroll_page(DynastyPage(), min_content_height=1080)),' in patched
    assert "self.resize(1500, 940)" in patched
    assert "self.setMinimumSize(1100, 720)" in patched
    assert patch_studio_app(patched) == patched


def test_dynasty_page_source_compiles() -> None:
    path = Path("v2/integration/production_overlay/studio/pages/dynasty.py")
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    assert "class DynastyPage" in source
    assert "No checkpoint was loaded" in source


def test_scroll_host_source_compiles() -> None:
    path = Path("v2/integration/production_overlay/studio/scroll_host.py")
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    assert "QScrollArea" in source
    assert "scroll_page" in source
