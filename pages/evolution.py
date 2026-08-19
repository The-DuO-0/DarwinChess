from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)


class EvolutionPage(QWidget):
    STAGES = ["self-play", "training", "arena", "promoted"]

    def __init__(self, process, parent=None):
        super().__init__(parent)
        self.process = process
        self.elapsed = QElapsedTimer()
        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self._tick)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 24)
        root.setSpacing(14)

        title_row = QHBoxLayout()
        title = QLabel("Evolution")
        title.setObjectName("SectionTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        self.status = QLabel("● IDLE")
        self.status.setObjectName("RunBadge")
        title_row.addWidget(self.status)
        root.addLayout(title_row)

        controls = QFrame()
        controls.setObjectName("Panel")
        grid = QGridLayout(controls)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(12)
        grid.addWidget(QLabel("Resource mode"), 0, 0)
        grid.addWidget(QLabel("Cycles"), 0, 1)
        grid.addWidget(QLabel("Hours (0 = cycles mode)"), 0, 2)
        self.mode = QComboBox()
        self.mode.addItems(["eco", "normal", "night"])
        self.mode.setCurrentText("night")
        self.cycles = QSpinBox()
        self.cycles.setRange(1, 999)
        self.cycles.setValue(1)
        self.hours = QDoubleSpinBox()
        self.hours.setRange(0, 72)
        self.hours.setDecimals(1)
        self.hours.setValue(2.0)
        self.start_btn = QPushButton("Start evolution")
        self.start_btn.setObjectName("Primary")
        self.stop_btn = QPushButton("Stop safely")
        self.stop_btn.setObjectName("Danger")
        for button in (self.start_btn, self.stop_btn):
            button.setCursor(Qt.PointingHandCursor)
        grid.addWidget(self.mode, 1, 0)
        grid.addWidget(self.cycles, 1, 1)
        grid.addWidget(self.hours, 1, 2)
        grid.addWidget(self.start_btn, 1, 3)
        grid.addWidget(self.stop_btn, 1, 4)
        root.addWidget(controls)

        run_card = QFrame()
        run_card.setObjectName("Card")
        rl = QVBoxLayout(run_card)
        rl.setContentsMargins(18, 16, 18, 16)
        run_head = QHBoxLayout()
        run_head.addWidget(QLabel("CURRENT RUN"))
        run_head.addStretch()
        self.elapsed_label = QLabel("elapsed 00:00:00")
        self.elapsed_label.setObjectName("Subtle")
        run_head.addWidget(self.elapsed_label)
        rl.addLayout(run_head)

        self.stage_title = QLabel("Waiting")
        self.stage_title.setObjectName("CardValue")
        rl.addWidget(self.stage_title)
        self.detail = QLabel("The current stage will appear here as soon as the process starts.")
        self.detail.setObjectName("Subtle")
        rl.addWidget(self.detail)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        rl.addWidget(self.progress)
        root.addWidget(run_card)

        flow = QFrame()
        flow.setObjectName("Panel")
        fl = QHBoxLayout(flow)
        fl.setContentsMargins(14, 14, 14, 14)
        self.stage_boxes = {}
        for i, stage in enumerate(["SELF-PLAY", "TRAINING", "ARENA", "PROMOTE / REJECT"]):
            label = QLabel(stage)
            label.setObjectName("StageBox")
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumHeight(54)
            fl.addWidget(label, 1)
            self.stage_boxes[stage.lower()] = label
            if i < 3:
                arrow = QLabel("→")
                arrow.setObjectName("Subtle")
                fl.addWidget(arrow)
        root.addWidget(flow)

        note = QLabel("Opening-diversity gate: this Studio build is prepared for paired-opening Arena and curriculum self-play. Core integration is kept separate from UI so existing checkpoints stay untouched during migration.")
        note.setObjectName("InfoNote")
        note.setWordWrap(True)
        root.addWidget(note)

        root.addWidget(QLabel("Live process log"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        root.addWidget(self.log, 1)

        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self.process.stop_safely)
        self.process.output.connect(self._append)
        self.process.started.connect(self._started)
        self.process.finished.connect(self._finished)
        self.process.state_changed.connect(self._running_changed)
        self.process.stage_changed.connect(self._stage_changed)
        self._running_changed(self.process.running)

    def _start(self):
        ok = self.process.start_evolution(self.mode.currentText(), self.cycles.value(), self.hours.value())
        if not ok:
            self._append("[Studio] A process is already running; Start was ignored.")

    def _running_changed(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.mode.setEnabled(not running)
        self.cycles.setEnabled(not running)
        self.hours.setEnabled(not running)

    def _started(self, label: str):
        self.elapsed.start()
        self.clock.start()
        self.status.setText(f"● RUNNING · {label}")
        self.status.setProperty("active", True)
        self._restyle(self.status)
        self._tick()

    def _finished(self, code: int):
        self.clock.stop()
        self.status.setText("● IDLE" if code == 0 else f"● EXITED · code {code}")
        self.status.setProperty("active", False)
        self._restyle(self.status)
        self.stage_title.setText("Finished" if code == 0 else "Process stopped")
        self.detail.setText("Safe boundary reached." if code == 0 else "Check the final log lines for details.")
        self.progress.setVisible(False)
        self._highlight(None)

    def _tick(self):
        if not self.elapsed.isValid():
            return
        total = self.elapsed.elapsed() // 1000
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        self.elapsed_label.setText(f"elapsed {h:02d}:{m:02d}:{s:02d}")

    def _stage_changed(self, stage: str, detail: str):
        label = stage.upper().replace("_", " ")
        self.status.setText(f"● {label}" + (f" · {detail}" if detail else ""))
        self.stage_title.setText(label)
        self.detail.setText(detail or self._stage_explanation(stage))
        self._highlight(stage)
        if detail and "/" in detail:
            try:
                cur, total = [int(x) for x in detail.split("/", 1)]
                self.progress.setRange(0, total)
                self.progress.setValue(cur)
                self.progress.setVisible(True)
            except ValueError:
                self.progress.setVisible(False)
        else:
            self.progress.setVisible(stage not in ("idle", "promoted", "rejected"))
            if self.progress.isVisible():
                self.progress.setRange(0, 0)

    def _stage_explanation(self, stage: str) -> str:
        return {
            "starting": "Launching the existing chess core without touching the active champion.",
            "self-play": "Generating durable experience games.",
            "training": "Updating a challenger from the current champion checkpoint.",
            "arena": "Held-out challenger vs champion evaluation.",
            "promoted": "The challenger passed the gate and became champion.",
            "rejected": "The challenger failed the gate; the old champion remains active.",
            "stopping safely": "Stop requested; waiting for the chess core's safe boundary.",
        }.get(stage, "")

    def _highlight(self, stage: str | None):
        mapping = {
            "self-play": "self-play",
            "training": "training",
            "arena": "arena",
            "promoted": "promote / reject",
            "rejected": "promote / reject",
        }
        active = mapping.get(stage or "")
        for key, label in self.stage_boxes.items():
            label.setProperty("active", key == active)
            self._restyle(label)

    @staticmethod
    def _restyle(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _append(self, text: str):
        self.log.appendPlainText(text)
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())
