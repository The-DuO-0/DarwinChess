from __future__ import annotations

from pathlib import Path
from typing import Any
import copy
import os
import random

import numpy as np
import torch
import yaml


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PACKAGE_ROOT / "configs" / "default.yaml"


def _expand(obj: Any) -> Any:
    if isinstance(obj, str) and obj.startswith("~"):
        return str(Path(obj).expanduser())
    if isinstance(obj, dict):
        return {k: _expand(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand(v) for v in obj]
    return obj


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    with DEFAULT_CONFIG.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if path:
        with Path(path).expanduser().open("r", encoding="utf-8") as f:
            override = yaml.safe_load(f) or {}
        config = deep_merge(config, override)
    return _expand(config)


def apply_mode(config: dict[str, Any], mode: str) -> dict[str, Any]:
    cfg = copy.deepcopy(config)
    modes = cfg["resources"]
    if mode not in modes or not isinstance(modes[mode], dict):
        raise ValueError(f"Unknown resource mode: {mode}")
    m = modes[mode]
    cfg["search"]["depth"] = int(m["search_depth"])
    cfg["selfplay"]["games_per_cycle"] = int(m["selfplay_games_per_cycle"])
    cfg["training"]["steps_per_cycle"] = int(m["training_steps_per_cycle"])
    cfg["arena"]["games"] = int(m["arena_games"])
    cfg["runtime"] = {"mode": mode, **m}
    return cfg


def state_root(config: dict[str, Any]) -> Path:
    override = os.environ.get("DARWINCHESS_HOME") or os.environ.get("DARWINCHESS_STATE_DIR")
    if override:
        return Path(override).expanduser()
    return Path(config["project"]["state_dir"]).expanduser()


def state_paths(config: dict[str, Any]) -> dict[str, Path]:
    root = state_root(config)
    return {
        "root": root,
        "db": root / "darwinchess.sqlite3",
        "checkpoints": root / "checkpoints",
        "logs": root / "logs",
        "exports": root / "exports",
    }


def ensure_state_dirs(config: dict[str, Any]) -> dict[str, Path]:
    paths = state_paths(config)
    for key, path in paths.items():
        if key != "db":
            path.mkdir(parents=True, exist_ok=True)
    return paths


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.backends.mps.is_available():
        pass


def choose_device(prefer_accelerator: bool = True) -> torch.device:
    if prefer_accelerator and torch.backends.mps.is_available():
        return torch.device("mps")
    if prefer_accelerator and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def configure_runtime(config: dict[str, Any]) -> None:
    runtime = config.get("runtime", {})
    threads = int(runtime.get("torch_threads", 0) or 0)
    if threads > 0:
        torch.set_num_threads(threads)
    nice = int(runtime.get("nice", 0) or 0)
    if nice > 0 and hasattr(os, "nice"):
        try:
            os.nice(nice)
        except OSError:
            pass
