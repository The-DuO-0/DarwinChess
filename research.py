from __future__ import annotations

import math
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from ..backend import ProcessController
from ..data import ReadOnlyStore, db_path, first_value, numeric_series, named_metric_series


class PlotCanvas(FigureCanvas):
    def __init__(self, title=""):
        self.figure = Figure(figsize=(5, 3), tight_layout=True)
        super().__init__(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.title = title
        self._decorate()

    def _decorate(self):
        self.figure.patch.set_facecolor("#15181f")
        self.ax.set_facecolor("#15181f")
        self.ax.tick_params(colors="#aeb6c6")
        for s in self.ax.spines.values(): s.set_color("#353b47")
        self.ax.title.set_color("#edf0f6"); self.ax.xaxis.label.set_color("#aeb6c6"); self.ax.yaxis.label.set_color("#aeb6c6")

    def set_series(self, xs, ys, title, xlabel="Generation", ylabel=""):
        self.ax.clear(); self._decorate(); self.ax.set_title(title); self.ax.set_xlabel(xlabel); self.ax.set_ylabel(ylabel)
        # Defensive alignment: malformed or sparse DB rows must never crash the whole Studio.
        pairs = list(zip(xs or [], ys or []))
        if pairs:
            px, py = zip(*pairs)
            self.ax.plot(px, py, marker="o", linewidth=1.5, markersize=3)
        else:
            self.ax.text(0.5, 0.5, "No compatible data yet", ha="center", va="center", transform=self.ax.transAxes, color="#8d96a8")
        self.draw_idle()


class ResearchPage(QWidget):
    def __init__(self, process: ProcessController, parent=None):
        super().__init__(parent)
        self.process = process
        self.store = ReadOnlyStore()
        root = QVBoxLayout(self)
        head = QHBoxLayout(); title = QLabel("Research & lineage"); title.setObjectName("SectionTitle")
        self.path = QLabel(str(db_path())); self.path.setObjectName("Subtle")
        refresh = QPushButton("Refresh from DB"); refresh.clicked.connect(self.refresh)
        export = QPushButton("Export CSV / PGN"); export.clicked.connect(lambda: self.process.start(["export"], "Export"))
        head.addWidget(title); head.addStretch(); head.addWidget(self.path); head.addWidget(refresh); head.addWidget(export); root.addLayout(head)

        charts = QHBoxLayout(); self.loss_chart = PlotCanvas(); self.arena_chart = PlotCanvas(); charts.addWidget(self.loss_chart); charts.addWidget(self.arena_chart); root.addLayout(charts, 1)

        self.tabs = QTabWidget();
        self.generations_table = QTableWidget(); self.metrics_table = QTableWidget(); self.db_table = QTableWidget()
        self.tabs.addTab(self.generations_table, "Generations")
        self.tabs.addTab(self.metrics_table, "Metrics")
        self.tabs.addTab(self.db_table, "Database overview")
        root.addWidget(self.tabs, 1)
        self.process.finished.connect(lambda _c: self.refresh())
        self.refresh()

    def refresh(self):
        self.store = ReadOnlyStore(); self.path.setText(str(self.store.path))
        try:
            gens = self.store.generations(); metrics = self.store.metrics(); counts = self.store.overview_counts()
        except Exception as exc:
            gens, metrics, counts = [], [], {"error": str(exc)}
        self._fill(self.generations_table, gens[-100:])
        self._fill(self.metrics_table, metrics[-200:])
        self._fill(self.db_table, [{"table": k, "rows": v} for k, v in counts.items()])
        gx, loss = numeric_series(gens, ("generation", "id", "generation_id"), ("training_loss", "loss"))
        ax, arena = numeric_series(gens, ("generation", "id", "generation_id"), ("arena_score", "score", "win_rate"))
        if not loss:
            gx, loss = numeric_series(metrics, ("generation", "step", "id"), ("training_loss", "loss"))
        if not loss:
            gx, loss = named_metric_series(metrics, ("loss", "training_loss"))
        if not arena:
            ax, arena = numeric_series(metrics, ("generation", "step", "id"), ("arena_score", "win_rate", "score"))
        if not arena:
            ax, arena = named_metric_series(metrics, ("arena", "win_rate", "wilson"))
        self.loss_chart.set_series(gx, loss, "Training loss", ylabel="Loss")
        self.arena_chart.set_series(ax, arena, "Arena score", ylabel="Score")

    @staticmethod
    def _fill(table, rows):
        if not rows:
            table.setRowCount(0); table.setColumnCount(0); return
        cols = list(rows[0].keys())
        # Include late-appearing columns too.
        for row in rows[1:]:
            for k in row:
                if k not in cols: cols.append(k)
        table.setColumnCount(len(cols)); table.setHorizontalHeaderLabels(cols); table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, key in enumerate(cols): table.setItem(r, c, QTableWidgetItem(str(row.get(key, ""))))
        table.resizeColumnsToContents()
