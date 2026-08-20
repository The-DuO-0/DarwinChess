from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


_FLOW_ORDER = (
    ("self_play", "Self-play"),
    ("population_train", "Population train"),
    ("league", "League · 2–3"),
    ("arena", "Arena"),
    ("strength_guard", "Strength guard"),
    ("promotion", "Promote / Reject"),
    ("archive", "Archive + Chronicle"),
    ("next_round", "Next round"),
)


def _duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "—"
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class EvolutionFlowPanel(QFrame):
    """V2.2 Evolution monitor driven by structured `DOGMATIST_UI` events.

    This panel is deliberately command-agnostic: it can be embedded into the
    existing Evolution page without changing the buttons that launch training.
    It consumes ``ProcessController.ui_event`` added by the V2.2 backend.
    """

    def __init__(self, process, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EvolutionFlowPanel")
        self.process = process

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("DogMatist evolution flow")
        title.setObjectName("SectionTitle")
        top.addWidget(title)
        top.addStretch()
        self.round_label = QLabel("Round —")
        self.round_label.setObjectName("Subtle")
        top.addWidget(self.round_label)
        root.addLayout(top)

        clock_box = QFrame()
        clock_layout = QGridLayout(clock_box)
        clock_layout.setContentsMargins(0, 0, 0, 0)
        clock_layout.addWidget(QLabel("Compute time used"), 0, 0)
        self.used_label = QLabel("—")
        clock_layout.addWidget(self.used_label, 0, 1)
        clock_layout.addWidget(QLabel("Compute time remaining"), 0, 2)
        self.remaining_label = QLabel("—")
        clock_layout.addWidget(self.remaining_label, 0, 3)
        self.compute_bar = QProgressBar()
        self.compute_bar.setRange(0, 1000)
        self.compute_bar.setValue(0)
        self.compute_bar.setTextVisible(False)
        clock_layout.addWidget(self.compute_bar, 1, 0, 1, 4)
        sleep_note = QLabel("Sleep / paused time is not charged to the compute budget.")
        sleep_note.setObjectName("Subtle")
        clock_layout.addWidget(sleep_note, 2, 0, 1, 4)
        root.addWidget(clock_box)

        flow_box = QFrame()
        flow_layout = QHBoxLayout(flow_box)
        flow_layout.setContentsMargins(0, 0, 0, 0)
        flow_layout.setSpacing(6)
        self.flow_labels: dict[str, QLabel] = {}
        for index, (key, label) in enumerate(_FLOW_ORDER):
            widget = QLabel(label)
            widget.setAlignment(Qt.AlignCenter)
            widget.setObjectName("FlowPending")
            widget.setProperty("flowState", "pending")
            flow_layout.addWidget(widget, 1)
            self.flow_labels[key] = widget
            if index < len(_FLOW_ORDER) - 1:
                arrow = QLabel("→")
                arrow.setObjectName("Subtle")
                flow_layout.addWidget(arrow)
        root.addWidget(flow_box)

        self.banner = QLabel("Waiting for evolution status…")
        self.banner.setWordWrap(True)
        self.banner.setObjectName("StatusBanner")
        root.addWidget(self.banner)

        league_header = QHBoxLayout()
        league_title = QLabel("Live League games")
        league_title.setObjectName("SectionTitle")
        league_header.addWidget(league_title)
        league_header.addStretch()
        self.league_capacity = QLabel("0/2 active")
        self.league_capacity.setObjectName("Subtle")
        league_header.addWidget(self.league_capacity)
        root.addLayout(league_header)

        self.games = QTableWidget(0, 8)
        self.games.setHorizontalHeaderLabels(
            ["Game", "Pair", "White", "Black", "Leg", "Move / ply", "Runtime", "State"]
        )
        self.games.verticalHeader().setVisible(False)
        self.games.setEditTriggers(QTableWidget.NoEditTriggers)
        self.games.setSelectionBehavior(QTableWidget.SelectRows)
        self.games.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.games)

        if hasattr(process, "ui_event"):
            process.ui_event.connect(self.apply_payload)

    def _set_flow_state(self, key: str, state: str) -> None:
        label = self.flow_labels.get(key)
        if label is None:
            return
        label.setProperty("flowState", state)
        if state == "current":
            label.setText("● " + dict(_FLOW_ORDER)[key])
        elif state == "done":
            label.setText("✓ " + dict(_FLOW_ORDER)[key])
        else:
            label.setText(dict(_FLOW_ORDER)[key])
        label.style().unpolish(label)
        label.style().polish(label)

    def apply_payload(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        self.round_label.setText(f"Round {payload.get('round_index', '—')}")
        self.banner.setText(str(payload.get("status_text", "")))

        compute = payload.get("compute") or {}
        if isinstance(compute, dict):
            used = float(compute.get("elapsed_compute_seconds", 0.0) or 0.0)
            remaining = float(compute.get("remaining_compute_seconds", 0.0) or 0.0)
            budget = float(compute.get("budget_seconds", 0.0) or 0.0)
            self.used_label.setText(_duration(used))
            self.remaining_label.setText(_duration(remaining))
            fraction = 0.0 if budget <= 0 else min(1.0, used / budget)
            self.compute_bar.setValue(int(fraction * 1000))

        flow = payload.get("flow") or []
        if isinstance(flow, list):
            for row in flow:
                if isinstance(row, dict):
                    self._set_flow_state(str(row.get("key", "")), str(row.get("state", "pending")))

        league = payload.get("league") or {}
        if not isinstance(league, dict):
            league = {}
        active = league.get("active_games") or []
        if not isinstance(active, list):
            active = []
        capacity = int(league.get("parallel_games", 2) or 2)
        suffix = " · draining" if league.get("draining") else ""
        self.league_capacity.setText(f"{len(active)}/{capacity} active{suffix}")

        self.games.setRowCount(len(active))
        for row_index, game in enumerate(active):
            if not isinstance(game, dict):
                continue
            plies = int(game.get("plies", 0) or 0)
            full_moves = int(game.get("completed_full_moves", plies // 2) or 0)
            values = (
                game.get("game_id", "—"),
                game.get("pairing_id", "—"),
                game.get("white_id", "—"),
                game.get("black_id", "—"),
                game.get("leg", "—"),
                f"{full_moves} / {plies}",
                _duration(game.get("runtime_seconds")),
                game.get("state", "—"),
            )
            for column, value in enumerate(values):
                self.games.setItem(row_index, column, QTableWidgetItem(str(value)))
