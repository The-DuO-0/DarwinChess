import importlib.util
from pathlib import Path
import sys


V2_ROOT = Path(__file__).resolve().parents[1]
OVERLAY = V2_ROOT / "integration" / "production_overlay"


def _load(name, filename):
    path = OVERLAY / filename
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


def test_prepare_script_builds_dot_darwinchess_under_empty_validation_home(tmp_path):
    prepare = _load("dogmatist_prepare_validation", "prepare_mac_validation.py")
    live = tmp_path / "live" / ".darwinchess"
    home = tmp_path / "validation-home"
    source, destination = prepare.resolve_validation_paths(live, home)
    assert source == live.resolve()
    assert destination == (home / ".darwinchess").resolve()


def test_prepare_script_rejects_nonempty_validation_home(tmp_path):
    prepare = _load("dogmatist_prepare_validation_nonempty", "prepare_mac_validation.py")
    live = tmp_path / "live" / ".darwinchess"
    home = tmp_path / "validation-home"
    home.mkdir()
    (home / "unexpected.txt").write_text("x", encoding="utf-8")
    try:
        prepare.resolve_validation_paths(live, home)
    except FileExistsError:
        pass
    else:
        raise AssertionError("non-empty validation home should be rejected")
