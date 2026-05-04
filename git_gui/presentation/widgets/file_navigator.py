"""FileNavigatorWidget — vertical list / horizontal pill strip for files in a commit.

Wraps a FileListView and (in pill mode, see Task 3) a horizontal strip of pill
buttons. Both share the same selection model so click-to-filter works
identically regardless of which mode is active.

Mode-switch and active-file highlight are driven externally — by
DiffWidget's _StickyPinController in the case of pin/unpin, and by scroll-
based auto-highlight logic.
"""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QItemSelectionModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import QListView, QStackedLayout, QWidget

from git_gui.presentation.models.diff_model import DiffModel
from git_gui.presentation.widgets.file_list_view import FileDeltaDelegate, FileListView


class NavMode(Enum):
    LIST = 0
    PILL = 1


class FileNavigatorWidget(QWidget):
    """Two-shape file navigator backed by a shared QItemSelectionModel."""

    # Re-exposes signals from the shared selection model + list view so callers
    # don't have to know the internal structure.
    currentChanged = Signal(QModelIndex, QModelIndex)
    deselected = Signal()

    def __init__(self, model: DiffModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._model = model

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)

        # ── List mode ────────────────────────────────────────────────────────
        self._list_view = FileListView()
        self._list_view.setEditTriggers(QListView.NoEditTriggers)
        self._list_view.setModel(model)
        self._list_view.setItemDelegate(FileDeltaDelegate(self._list_view))
        self._stack.addWidget(self._list_view)

        # Pill mode placeholder (Task 3 fills this in).
        self._pill_root: QWidget | None = None

        # Wire signal forwarding.
        self._list_view.selectionModel().currentChanged.connect(self.currentChanged.emit)
        self._list_view.deselected.connect(self.deselected.emit)

    # ── Public API ──────────────────────────────────────────────────────────

    @property
    def selection_model(self) -> QItemSelectionModel:
        return self._list_view.selectionModel()

    def mode(self) -> NavMode:
        idx = self._stack.currentIndex()
        return NavMode.LIST if idx == 0 else NavMode.PILL

    def set_mode(self, mode: NavMode) -> None:
        self._stack.setCurrentIndex(mode.value)
