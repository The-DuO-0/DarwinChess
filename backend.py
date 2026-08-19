from __future__ import annotations

import os
import re
import shutil
import signal
import sys
import uuid
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QProcess, QThread, Signal, Slot


def darwin_executable() -> str:
    """Keep the existing core executable for checkpoint/state compatibility."""
    local = Path(sys.executable).resolve().parent / "darwinchess"
    if local.exists():
        return str(local)
    return shutil.which("darwinchess") or "darwinchess"


def flatten_mapping(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, val in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(val, dict):
                out.update(flatten_mapping(val, path))
            else:
                out[path] = val
    else:
        out[prefix or "value"] = value
    return out


def find_state_value(state: dict[str, Any], *aliases: str, default: Any = "—") -> Any:
    flat = flatten_mapping(state)
    aliases = tuple(a.lower().replace(" ", "_") for a in aliases)
    for key, value in flat.items():
        leaf = key.split(".")[-1].lower().replace(" ", "_")
        if leaf in aliases:
            return value
    for key, value in flat.items():
        norm = key.lower().replace(" ", "_")
        if any(a in norm for a in aliases):
            return value
    return default


def normalize_move(answer: Any) -> str:
    if answer is None:
        raise ValueError("dog_matist returned no move")
    if isinstance(answer, dict):
        for key in ("move", "best_move", "uci", "bestmove"):
            if key in answer:
                return normalize_move(answer[key])
    for attr in ("move", "best_move", "uci"):
        if hasattr(answer, attr):
            obj = getattr(answer, attr)
            obj = obj() if callable(obj) else obj
            return normalize_move(obj)
    text = str(answer).strip()
    match = re.search(r"\b([a-h][1-8][a-h][1-8][qrbn]?)\b", text.lower())
    if match:
        return match.group(1)
    return text


class _AgentWorker(QObject):
    ready = Signal()
    status_ready = Signal(str, object)
    move_ready = Signal(str, str)
    talk_ready = Signal(str, str)
    error = Signal(str, str)
    stopped = Signal()

    def __init__(self, mode: str = "normal") -> None:
        super().__init__()
        self.mode = mode
        self.agent = None
        self._entered = False

    @Slot()
    def initialize(self) -> None:
        try:
            from darwinchess.api import DarwinChessAgent
            obj = DarwinChessAgent(mode=self.mode)
            if hasattr(obj, "__enter__"):
                entered = obj.__enter__()
                self.agent = entered if entered is not None else obj
                self._entered = True
            else:
                self.agent = obj
            self.ready.emit()
        except Exception as exc:
            self.error.emit("startup", f"Could not start chess core: {exc}")

    @Slot(str)
    def get_status(self, request_id: str) -> None:
        try:
            result = self.agent.status()
            if not isinstance(result, dict):
                result = {"status": result}
            self.status_ready.emit(request_id, result)
        except Exception as exc:
            self.error.emit(request_id, str(exc))

    @Slot(str, str)
    def get_best_move(self, request_id: str, fen: str) -> None:
        try:
            result = self.agent.best_move(fen)
            self.move_ready.emit(request_id, normalize_move(result))
        except Exception as exc:
            self.error.emit(request_id, str(exc))

    @Slot(str, str)
    def talk(self, request_id: str, text: str) -> None:
        try:
            self.talk_ready.emit(request_id, str(self.agent.talk(text)))
        except Exception as exc:
            self.error.emit(request_id, str(exc))

    @Slot()
    def shutdown(self) -> None:
        try:
            if self._entered and self.agent is not None and hasattr(self.agent, "__exit__"):
                self.agent.__exit__(None, None, None)
            elif self.agent is not None and hasattr(self.agent, "close"):
                self.agent.close()
        finally:
            self.agent = None
            self.stopped.emit()


class AgentBridge(QObject):
    status_request = Signal(str)
    move_request = Signal(str, str)
    talk_request = Signal(str, str)
    shutdown_request = Signal()

    ready = Signal()
    status_ready = Signal(str, object)
    move_ready = Signal(str, str)
    talk_ready = Signal(str, str)
    error = Signal(str, str)

    def __init__(self, mode: str = "normal", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.thread = QThread(self)
        self.worker = _AgentWorker(mode)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.initialize)
        self.status_request.connect(self.worker.get_status)
        self.move_request.connect(self.worker.get_best_move)
        self.talk_request.connect(self.worker.talk)
        self.shutdown_request.connect(self.worker.shutdown)
        self.worker.ready.connect(self.ready)
        self.worker.status_ready.connect(self.status_ready)
        self.worker.move_ready.connect(self.move_ready)
        self.worker.talk_ready.connect(self.talk_ready)
        self.worker.error.connect(self.error)
        self.worker.stopped.connect(self.thread.quit)
        self.thread.start()

    def request_status(self) -> str:
        rid = uuid.uuid4().hex
        self.status_request.emit(rid)
        return rid

    def request_move(self, fen: str) -> str:
        rid = uuid.uuid4().hex
        self.move_request.emit(rid, fen)
        return rid

    def request_talk(self, text: str) -> str:
        rid = uuid.uuid4().hex
        self.talk_request.emit(rid, text)
        return rid

    def close(self) -> None:
        if not self.thread.isRunning():
            return
        self.shutdown_request.emit()
        self.thread.wait(4000)


class ProcessController(QObject):
    output = Signal(str)
    started = Signal(str)
    finished = Signal(int)
    state_changed = Signal(bool)
    stage_changed = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.started.connect(self._on_started)
        self.process.finished.connect(self._on_finished)
        self.label = ""
        self.stage = "idle"

    @property
    def running(self) -> bool:
        return self.process.state() != QProcess.NotRunning

    def start(self, args: list[str], label: str = "dog_matist") -> bool:
        if self.running:
            return False
        self.label = label
        self.process.setProgram(darwin_executable())
        self.process.setArguments(args)
        self.process.start()
        return True

    def _infer_stage(self, text: str):
        low = text.lower()
        stage = None
        detail = ""
        if any(k in low for k in ("self-play", "selfplay", "self play")):
            stage = "self-play"
        if any(k in low for k in ("training", "train challenger", "gradient", "epoch", "batch")):
            stage = "training"
        if any(k in low for k in ("arena", "candidate vs", "challenger vs")):
            stage = "arena"
        if any(k in low for k in ("promoted", "promote")):
            stage = "promoted"
        elif any(k in low for k in ("rejected", "reject")):
            stage = "rejected"
        if "sigint" in low or "safe boundary" in low or "stopping" in low:
            stage = "stopping safely"

        # Pull useful progress snippets without depending on one exact CLI format.
        m = re.search(r"(?:game|batch|epoch|opening)\s*[#:]?\s*(\d+)\s*/\s*(\d+)", text, re.I)
        if m:
            detail = f"{m.group(1)}/{m.group(2)}"
        if stage and (stage != self.stage or detail):
            self.stage = stage
            self.stage_changed.emit(stage, detail)

    def start_evolution(self, mode: str, cycles: int, hours: float) -> bool:
        args = ["--mode", mode, "evolve"]
        if hours and hours > 0:
            args += ["--hours", str(hours)]
        else:
            args += ["--cycles", str(max(1, cycles))]
        return self.start(args, f"Evolution ({mode})")

    @Slot()
    def _read_output(self) -> None:
        raw = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if raw:
            clean = raw.rstrip()
            self.output.emit(clean)
            for line in clean.splitlines():
                self._infer_stage(line)

    @Slot()
    def _on_started(self) -> None:
        self.state_changed.emit(True)
        self.started.emit(self.label)
        self.stage = "starting"
        self.stage_changed.emit("starting", self.label)

    @Slot(int, QProcess.ExitStatus)
    def _on_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self.state_changed.emit(False)
        self.stage = "idle"
        self.stage_changed.emit("idle", "")
        self.finished.emit(exit_code)

    def stop_safely(self) -> None:
        if not self.running:
            return
        self.stage = "stopping safely"
        self.stage_changed.emit("stopping safely", "waiting for safe boundary")
        pid = int(self.process.processId())
        if pid > 0 and os.name == "posix":
            try:
                os.kill(pid, signal.SIGINT)
                self.output.emit("[Studio] Stop requested. Waiting for the chess core's safe boundary…")
                return
            except OSError:
                pass
        self.process.terminate()
