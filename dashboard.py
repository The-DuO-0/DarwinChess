from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from ..backend import AgentBridge, ProcessController, find_state_value, flatten_mapping
from ..data import ReadOnlyStore, db_path, first_value
from ..widgets.cards import StatCard


class DashboardPage(QWidget):
    def __init__(self, agent: AgentBridge, process: ProcessController, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.process = process
        self.pending = None

        root = QVBoxLayout(self)
        title_row = QHBoxLayout()
        title = QLabel("Dashboard"); title.setObjectName("SectionTitle")
        self.connection = QLabel("Connecting to DarwinChess…"); self.connection.setObjectName("Subtle")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        title_row.addWidget(title); title_row.addStretch(); title_row.addWidget(self.connection); title_row.addWidget(refresh)
        root.addLayout(title_row)

        cards = QGridLayout()
        self.champion = StatCard("Champion generation")
        self.games = StatCard("Lifetime games")
        self.replay = StatCard("Replay positions")
        self.training = StatCard("Evolution process", "Idle")
        cards.addWidget(self.champion, 0, 0); cards.addWidget(self.games, 0, 1)
        cards.addWidget(self.replay, 0, 2); cards.addWidget(self.training, 0, 3)
        self.candidate = StatCard("Latest generation status")
        self.arena = StatCard("Latest Arena score")
        self.loss = StatCard("Latest training loss")
        self.mix = StatCard("Classical mix")
        cards.addWidget(self.candidate, 1, 0); cards.addWidget(self.arena, 1, 1)
        cards.addWidget(self.loss, 1, 2); cards.addWidget(self.mix, 1, 3)
        root.addLayout(cards)

        panel = QFrame(); panel.setObjectName("Panel")
        pl = QVBoxLayout(panel)
        row = QHBoxLayout()
        self.db_label = QLabel(f"State database: {db_path()}"); self.db_label.setObjectName("Subtle")
        row.addWidget(QLabel("Live status")); row.addStretch(); row.addWidget(self.db_label)
        pl.addLayout(row)
        self.raw = QTextEdit(); self.raw.setReadOnly(True)
        pl.addWidget(self.raw)
        root.addWidget(panel, 1)

        self.agent.ready.connect(self.refresh)
        self.agent.status_ready.connect(self._status_ready)
        self.agent.error.connect(self._error)
        self.process.state_changed.connect(self._process_changed)
        timer = QTimer(self); timer.timeout.connect(self.refresh); timer.start(6000)

    def refresh(self):
        if self.pending is None:
            self.pending = self.agent.request_status()
        self.db_label.setText(f"State database: {db_path()}")
        try:
            gens = ReadOnlyStore().generations(limit=5)
            if gens:
                latest = gens[-1]
                gen = first_value(latest, "generation", "generation_id", "id", default="?")
                status = first_value(latest, "status", "state", default="—")
                self.candidate.set_value(status, f"Generation {gen}")
                self.arena.set_value(first_value(latest, "arena_score", "win_rate", "score", default="—"))
                self.loss.set_value(first_value(latest, "training_loss", "loss", default="—"))
                self.mix.set_value(first_value(latest, "classical_mix", "mix", default="—"))
        except Exception:
            pass

    def _status_ready(self, rid, state):
        if rid != self.pending:
            return
        self.pending = None
        self.connection.setText("Champion connected")
        self.champion.set_value(find_state_value(state, "champion_generation", "generation", "champion_id"))
        self.games.set_value(find_state_value(state, "total_games", "game_count", "games"))
        self.replay.set_value(find_state_value(state, "replay_positions", "replay_size", "replay_count", "examples"))
        flat = flatten_mapping(state)
        self.raw.setPlainText("\n".join(f"{k}: {v}" for k, v in sorted(flat.items())))

    def _error(self, rid, message):
        if rid == "startup" or rid == self.pending:
            self.pending = None
            self.connection.setText("DarwinChess API unavailable")
            self.raw.setPlainText(message)

    def _process_changed(self, running):
        self.training.set_value("Running" if running else "Idle", self.process.label if running else "Ready")
