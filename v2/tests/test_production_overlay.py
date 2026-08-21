import importlib.util
from pathlib import Path
import sys


V2_ROOT = Path(__file__).resolve().parents[1]
OVERLAY = V2_ROOT / "integration" / "production_overlay"


def _load_installer():
    path = OVERLAY / "install_on_copy.py"
    name = "dogmatist_overlay_installer"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def test_studio_drop_in_sources_are_syntax_valid_without_importing_qt():
    for path in (
        OVERLAY / "studio" / "backend.py",
        OVERLAY / "studio" / "pages" / "evolution.py",
    ):
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")


def test_installer_patches_exact_uploaded_pyproject_and_cli_shape():
    installer = _load_installer()
    pyproject = '[tool.setuptools.packages.find]\nwhere = ["."]\ninclude = ["darwinchess*", "studio*"]\n'
    patched_project = installer.patch_pyproject(pyproject)
    assert '"dogmatist_v2*"' in patched_project

    cli = (
        "from .selfplay import build_pgn\n\n\n"
        "def cmd_evolve(args) -> int:\n"
        "    with _runtime(args) as rt:\n"
        "        try:\n"
        "            rt.evolve(hours=args.hours, cycles=args.cycles)\n"
        "        except KeyboardInterrupt:\n"
        "            print(\"\\nInterrupted safely. Completed games and accepted checkpoints were already committed.\")\n"
        "        print(json.dumps(rt.status(), ensure_ascii=False, indent=2))\n"
        "    return 0\n"
    )
    patched_cli = installer.patch_cli(cli)
    assert "run_live_evolution" in patched_cli
    assert "LiveEvolutionOptions" in patched_cli
    assert "persist_teacher" in patched_cli
    assert "parallel_league" in patched_cli
