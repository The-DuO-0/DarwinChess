from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget)

from ..backend import ProcessController


class EvolutionPage(QWidget):
    def __init__(self, process: ProcessController, parent=None):
        super().__init__(parent)
        self.process = process
        root = QVBoxLayout(self)
        head = QHBoxLayout(); title = QLabel("Evolution"); title.setObjectName("SectionTitle")
        self.phase = QLabel("Idle"); self.phase.setObjectName("Subtle")
        head.addWidget(title); head.addStretch(); head.addWidget(self.phase); root.addLayout(head)

        controls = QFrame(); controls.setObjectName("Panel")
        grid = QGridLayout(controls)
        grid.addWidget(QLabel("Resource mode"), 0, 0)
        self.mode = QComboBox(); self.mode.addItems(["eco", "normal", "night"]); self.mode.setCurrentText("normal")
        grid.addWidget(self.mode, 1, 0)
        grid.addWidget(QLabel("Cycles"), 0, 1)
        self.cycles = QSpinBox(); self.cycles.setRange(1, 999); self.cycles.setValue(1); grid.addWidget(self.cycles, 1, 1)
        grid.addWidget(QLabel("Hours (0 = cycles mode)"), 0, 2)
        self.hours = QSpinBox(); self.hours.setRange(0, 168); self.hours.setValue(0); grid.addWidget(self.hours, 1, 2)

        self.start_btn = QPushButton("Start evolution"); self.start_btn.setObjectName("Primary"); self.start_btn.clicked.connect(self.start_evolution)
        self.stop_btn = QPushButton("Stop safely"); self.stop_btn.setObjectName("Danger"); self.stop_btn.clicked.connect(self.process.stop_safely)
        grid.addWidget(self.start_btn, 1, 3); grid.addWidget(self.stop_btn, 1, 4)
        root.addWidget(controls)

        actions = QHBoxLayout()
        self.challenge = QPushButton("Train + Arena challenge"); self.challenge.clicked.connect(lambda: self._run(["--mode", self.mode.currentText(), "challenge"], "Challenge"))
        self.selfplay = QPushButton("Generate 10 self-play games"); self.selfplay.clicked.connect(lambda: self._run(["--mode", self.mode.currentText(), "selfplay", "--games", "10"], "Self-play"))
        self.export = QPushButton("Export research data"); self.export.clicked.connect(lambda: self._run(["export"], "Export"))
        actions.addWidget(self.challenge); actions.addWidget(self.selfplay); actions.addWidget(self.export); actions.addStretch(); root.addLayout(actions)

        pipeline = QFrame(); pipeline.setObjectName("Panel"); pl = QHBoxLayout(pipeline)
        self.steps = []
        for name in ["SELF-PLAY", "TRAIN", "ARENA", "PROMOTE / REJECT"]:
            label = QLabel(name)
            label.setStyleSheet("padding:10px;border:1px solid #303643;border-radius:8px;color:#9ba5b6")
            self.steps.append(label); pl.addWidget(label)
            if name != "PROMOTE / REJECT": pl.addWidget(QLabel("→"))
        root.addWidget(pipeline)

        root.addWidget(QLabel("Live process log"))
        self.log = QTextEdit(); self.log.setReadOnly(True); root.addWidget(self.log, 1)

        self.process.output.connect(self._log)
        self.process.started.connect(lambda label: self.phase.setText(f"Running: {label}"))
        self.process.finished.connect(self._finished)
        self.process.state_changed.connect(self._state_changed)
        self._state_changed(False)

    def start_evolution(self):
        args = ["--mode", self.mode.currentText(), "evolve"]
        if self.hours.value() > 0:
            args += ["--hours", str(self.hours.value())]
        else:
            args += ["--cycles", str(self.cycles.value())]
        self._run(args, f"Evolution ({self.mode.currentText()})")

    def _run(self, args, label):
        if not self.process.start(args, label):
            QMessageBox.information(self, "DarwinChess busy", "An evolution process is already running.")

    def _log(self, text):
        self.log.append(text)
        low = text.lower()
        active = None
        if "self-play" in low or "selfplay" in low: active = 0
        if "train" in low or "challenger" in low: active = 1
        if "arena" in low: active = 2
        if "promot" in low or "reject" in low: active = 3
        if active is not None:
            for i, label in enumerate(self.steps):
                label.setStyleSheet("padding:10px;border:1px solid #4169e1;border-radius:8px;color:#ffffff;background:#1c2744" if i == active else "padding:10px;border:1px solid #303643;border-radius:8px;color:#9ba5b6")

    def _finished(self, code):
        self.phase.setText(f"Finished (exit {code})")

    def _state_changed(self, running):
        self.start_btn.setEnabled(not running); self.challenge.setEnabled(not running); self.selfplay.setEnabled(not running); self.export.setEnabled(not running); self.stop_btn.setEnabled(running)
