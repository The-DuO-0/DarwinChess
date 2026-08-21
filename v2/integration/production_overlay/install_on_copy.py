from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import shutil


CLI_IMPORT = "from dogmatist_v2.live_entrypoint import LiveEvolutionOptions, run_live_evolution\n"
OLD_EVOLVE = '''def cmd_evolve(args) -> int:\n    with _runtime(args) as rt:\n        try:\n            rt.evolve(hours=args.hours, cycles=args.cycles)\n        except KeyboardInterrupt:\n            print("\\nInterrupted safely. Completed games and accepted checkpoints were already committed.")\n        print(json.dumps(rt.status(), ensure_ascii=False, indent=2))\n    return 0\n'''
NEW_EVOLVE = '''def cmd_evolve(args) -> int:\n    with _runtime(args) as rt:\n        v2cfg = rt.config.get("v2_live", {})\n        options = LiveEvolutionOptions(\n            targeted_examples=int(v2cfg.get("targeted_examples", 64)),\n            teacher_request_cap=int(v2cfg.get("teacher_request_cap", 8)),\n            persist_teacher=bool(v2cfg.get("persist_teacher", False)),\n            enable_parallel_league=bool(v2cfg.get("parallel_league", True)),\n            strength_fail_open=bool(v2cfg.get("strength_fail_open", True)),\n            parallel_league_fail_open=bool(v2cfg.get("parallel_league_fail_open", True)),\n            handle_sigint=True,\n        )\n        try:\n            run_live_evolution(\n                rt,\n                hours=args.hours,\n                cycles=args.cycles,\n                options=options,\n            )\n        except KeyboardInterrupt:\n            print("\\nEmergency stop after a second interrupt. Durable completed games/checkpoints remain committed.")\n        print(json.dumps(rt.status(), ensure_ascii=False, indent=2))\n    return 0\n'''


@dataclass(frozen=True)
class OverlayPlan:
    target_root: Path
    source_package: Path
    target_package: Path
    pyproject: Path
    cli: Path
    source_studio_backend: Path
    source_evolution_page: Path
    target_studio_backend: Path
    target_evolution_page: Path


def repo_v2_root() -> Path:
    return Path(__file__).resolve().parents[2]


def make_plan(target_root: str | Path) -> OverlayPlan:
    target = Path(target_root).expanduser().resolve()
    v2_root = repo_v2_root()
    overlay_root = v2_root / "integration" / "production_overlay"
    source = v2_root / "dogmatist_v2"
    pyproject = target / "pyproject.toml"
    cli = target / "darwinchess" / "cli.py"
    target_backend = target / "studio" / "backend.py"
    target_evolution = target / "studio" / "pages" / "evolution.py"
    source_backend = overlay_root / "studio" / "backend.py"
    source_evolution = overlay_root / "studio" / "pages" / "evolution.py"

    required = [source, pyproject, cli, target_backend, target_evolution, source_backend, source_evolution]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("overlay/target files missing: " + ", ".join(missing))
    project_text = pyproject.read_text(encoding="utf-8")
    if 'name = "dog-matist"' not in project_text:
        raise RuntimeError("refusing to patch an unrelated pyproject")
    return OverlayPlan(
        target,
        source,
        target / "dogmatist_v2",
        pyproject,
        cli,
        source_backend,
        source_evolution,
        target_backend,
        target_evolution,
    )


def patch_pyproject(text: str) -> str:
    old = 'include = ["darwinchess*", "studio*"]'
    new = 'include = ["darwinchess*", "studio*", "dogmatist_v2*"]'
    if new in text:
        return text
    if old not in text:
        raise RuntimeError("could not find the expected setuptools package include line")
    return text.replace(old, new, 1)


def patch_cli(text: str) -> str:
    if "run_live_evolution(" in text and "LiveEvolutionOptions" in text:
        return text
    import_anchor = "from .selfplay import build_pgn\n"
    if CLI_IMPORT not in text:
        if import_anchor not in text:
            raise RuntimeError("could not find CLI import anchor")
        text = text.replace(import_anchor, import_anchor + CLI_IMPORT, 1)
    if OLD_EVOLVE not in text:
        raise RuntimeError("could not find the expected production cmd_evolve block")
    return text.replace(OLD_EVOLVE, NEW_EVOLVE, 1)


def _backup(path: Path) -> Path:
    backup = path.with_suffix(path.suffix + ".pre_v2")
    if not backup.exists():
        shutil.copy2(path, backup)
    return backup


def apply_overlay(plan: OverlayPlan) -> None:
    pyproject_text = patch_pyproject(plan.pyproject.read_text(encoding="utf-8"))
    cli_text = patch_cli(plan.cli.read_text(encoding="utf-8"))

    for path in (
        plan.pyproject,
        plan.cli,
        plan.target_studio_backend,
        plan.target_evolution_page,
    ):
        _backup(path)

    if plan.target_package.exists():
        backup_package = plan.target_root / "dogmatist_v2.pre_v2"
        if backup_package.exists():
            shutil.rmtree(backup_package)
        shutil.move(str(plan.target_package), str(backup_package))
    shutil.copytree(
        plan.source_package,
        plan.target_package,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )
    plan.pyproject.write_text(pyproject_text, encoding="utf-8")
    plan.cli.write_text(cli_text, encoding="utf-8")
    shutil.copy2(plan.source_studio_backend, plan.target_studio_backend)
    shutil.copy2(plan.source_evolution_page, plan.target_evolution_page)


def describe(plan: OverlayPlan) -> str:
    return "\n".join([
        "DogMatist V2 copied-source overlay plan",
        f"  target:       {plan.target_root}",
        f"  copy package: {plan.source_package} -> {plan.target_package}",
        f"  patch:        {plan.pyproject}",
        f"  patch:        {plan.cli}",
        f"  replace UI:   {plan.target_studio_backend}",
        f"  replace UI:   {plan.target_evolution_page}",
        "  state data:   NOT touched by this installer",
        "  teacher:      defaults OFF until copied-state validation passes",
        "  backups:      *.pre_v2 are created before source replacement",
    ])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Overlay V2 onto a COPY of the uploaded dog_matist-2.0 source."
    )
    parser.add_argument("target", help="path to copied dog_matist-2.0 source")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the source overlay; without this flag only print the plan",
    )
    args = parser.parse_args(argv)
    plan = make_plan(args.target)
    print(describe(plan))
    if not args.apply:
        print("\nDRY RUN ONLY. Re-run with --apply only on a disposable/copy source tree.")
        return 0
    apply_overlay(plan)
    print("\nOverlay applied to the SOURCE COPY. Reinstall that copy in its venv before testing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
