from __future__ import annotations

from pathlib import Path

from v2.integration.production_overlay.install_on_copy import patch_studio_app


def test_patch_studio_app_adds_dynasty_once() -> None:
    original = '''from .pages.dashboard import DashboardPage\nfrom .pages.evolution import EvolutionPage\nfrom .pages.play import PlayPage\n\nself.pages = [\n            ("Dashboard", DashboardPage(self.agent, self.process)),\n            ("Evolution", EvolutionPage(self.process)),\n            ("Research", ResearchPage(self.process)),\n]\n'''
    patched = patch_studio_app(original)
    assert "from .pages.dynasty import DynastyPage" in patched
    assert '("Dynasty Archive", DynastyPage()),' in patched
    assert patch_studio_app(patched) == patched


def test_dynasty_page_source_compiles() -> None:
    path = Path("v2/integration/production_overlay/studio/pages/dynasty.py")
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    assert "class DynastyPage" in source
    assert "No checkpoint was loaded" in source
