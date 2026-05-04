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

from PySide6.QtCore import QItemSelectionModel, QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListView,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QWidget,
)

from git_gui.presentation.models.diff_model import DiffModel
from git_gui.presentation.theme import connect_widget, get_theme_manager
from git_gui.presentation.widgets.file_list_view import FileDeltaDelegate, FileListView


class NavMode(Enum):
    LIST = 0
    PILL = 1


def _delta_dot_icon(delta: str, diameter: int = 8) -> QIcon:
    """Generate a circle-icon pixmap colored by the file's delta status."""
    pix = QPixmap(diameter, diameter)
    pix.fill(QColor(0, 0, 0, 0))  # transparent
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    color = get_theme_manager().current.colors.status_color(delta)
    painter.setBrush(color)
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, diameter, diameter)
    painter.end()
    return QIcon(pix)


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

        # ── Pill mode ────────────────────────────────────────────────────────
        self._pill_root = QScrollArea()
        self._pill_root.setWidgetResizable(True)
        self._pill_root.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._pill_root.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._pill_root.setFrameShape(QScrollArea.NoFrame)

        self._pill_container = QWidget()
        self._pill_layout = QHBoxLayout(self._pill_container)
        self._pill_layout.setContentsMargins(4, 4, 4, 4)
        self._pill_layout.setSpacing(4)
        self._pill_layout.addStretch(1)  # right-side filler
        self._pill_root.setWidget(self._pill_container)
        self._stack.addWidget(self._pill_root)

        # "All" synthetic pill (always present, at index 0).
        self._all_pill = QPushButton("All")
        self._all_pill.setCheckable(True)
        self._all_pill.setChecked(True)
        self._all_pill.clicked.connect(self._on_all_pill_clicked)
        self._pill_layout.insertWidget(0, self._all_pill)

        self._pill_buttons: dict[str, QPushButton] = {}
        self._build_pills()
        model.modelReset.connect(self._build_pills)

        # Sync pill check state from selection model changes (so list-view
        # clicks update pill highlight too).
        self._list_view.selectionModel().currentChanged.connect(self._sync_pills_to_selection)
        self._list_view.deselected.connect(self._sync_pills_to_selection_cleared)

        connect_widget(self, rebuild=self._restyle_pills)
        self._restyle_pills()

        # Wire signal forwarding.
        self._list_view.selectionModel().currentChanged.connect(self.currentChanged.emit)
        self._list_view.deselected.connect(self.deselected.emit)

    # ── Public API ──────────────────────────────────────────────────────────

    @property
    def selection_model(self) -> QItemSelectionModel:
        return self._list_view.selectionModel()

    def mode(self) -> NavMode:
        return NavMode(self._stack.currentIndex())

    def set_mode(self, mode: NavMode) -> None:
        self._stack.setCurrentIndex(mode.value)

    # ── Pill management ─────────────────────────────────────────────────────

    def _build_pills(self) -> None:
        """Tear down current per-file pills and rebuild from the model."""
        # Remove existing per-file pills (skip the "All" pill at index 0 and
        # the trailing stretch).
        for btn in list(self._pill_buttons.values()):
            self._pill_layout.removeWidget(btn)
            btn.deleteLater()
        self._pill_buttons.clear()

        for row in range(self._model.rowCount()):
            idx = self._model.index(row)
            fs = self._model.data(idx, Qt.UserRole)
            if fs is None:
                continue
            btn = QPushButton(fs.path)
            btn.setIcon(_delta_dot_icon(fs.delta))
            btn.setIconSize(QSize(10, 10))
            btn.setCheckable(True)
            btn.setChecked(False)
            btn.clicked.connect(lambda _checked=False, r=row: self._on_pill_clicked(r))
            # Insert before the stretch (which is at the end).
            insert_at = self._pill_layout.count() - 1
            self._pill_layout.insertWidget(insert_at, btn)
            self._pill_buttons[fs.path] = btn

        # Reset highlight to "All".
        self._all_pill.setChecked(not self.selection_model.hasSelection())

        # New pill widgets need their QSS applied; the construction-time
        # _restyle_pills call only saw _all_pill.
        self._restyle_pills()

    def _on_pill_clicked(self, row: int) -> None:
        """Drive the shared selection model. Visual pill state will follow via
        _sync_pills_to_selection. The explicit resync at the end handles the case
        where the user re-clicks the already-active pill: setCurrentIndex is a
        no-op (no currentChanged signal), but click() already toggled the pill's
        visual checked state to False — we reset it from the selection model.
        """
        idx = self._model.index(row)
        self.selection_model.setCurrentIndex(
            idx, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )
        self._sync_pills_to_selection(self.selection_model.currentIndex(), QModelIndex())

    def _on_all_pill_clicked(self) -> None:
        self.selection_model.clearSelection()
        self._list_view.setCurrentIndex(QModelIndex())
        self._sync_pills_to_selection_cleared()
        self.deselected.emit()

    def _sync_pills_to_selection(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            self._sync_pills_to_selection_cleared()
            return
        fs = self._model.data(current, Qt.UserRole)
        active_path = fs.path if fs else None
        for path, btn in self._pill_buttons.items():
            btn.setChecked(path == active_path)
        self._all_pill.setChecked(active_path is None)

    def _sync_pills_to_selection_cleared(self) -> None:
        for btn in self._pill_buttons.values():
            btn.setChecked(False)
        self._all_pill.setChecked(True)

    # ── set_active_file (visual-only highlight; does not change selection) ──

    def set_active_file(self, path: str | None) -> None:
        """Visually highlight a pill (and ensure it is on screen) without
        changing the selection model. Used by auto-highlight on scroll.

        DO NOT call this in response to a pill click; pill clicks must go
        through `_on_pill_clicked` so the selection model becomes the source
        of truth. This method is for read-only visual sync from external
        state (e.g., the diff scroll position).
        """
        # Unknown / stale path or explicit None → highlight "All".
        if path is None or path not in self._pill_buttons:
            self._all_pill.setChecked(True)
            for btn in self._pill_buttons.values():
                btn.setChecked(False)
            return

        self._all_pill.setChecked(False)
        active_btn = self._pill_buttons[path]
        for p, btn in self._pill_buttons.items():
            btn.setChecked(p == path)
        self._pill_root.ensureWidgetVisible(active_btn)

    # ── Theming ─────────────────────────────────────────────────────────────

    def _restyle_pills(self) -> None:
        c = get_theme_manager().current.colors
        bg = c.surface_container_high
        outline = c.outline
        on_surface = c.on_surface
        primary = c.primary
        on_primary = c.on_primary

        # Full state coverage so Qt's native Windows style fully yields to
        # our QSS. Without :hover, :pressed, :focus, and outline:none the
        # native style bleeds through and produces sharp-cornered gray
        # rectangles instead of rounded MD3 pills.
        pill_qss = (
            f"QPushButton {{"
            f"  background: {bg};"
            f"  color: {on_surface};"
            f"  border: 1px solid {outline};"
            f"  border-radius: 12px;"
            f"  padding: 4px 12px;"
            f"  min-height: 16px;"
            f"  outline: none;"
            f"}}"
            f"QPushButton:hover {{"
            f"  border-color: {primary};"
            f"}}"
            f"QPushButton:pressed {{"
            f"  background: {primary};"
            f"  color: {on_primary};"
            f"  border-color: {primary};"
            f"}}"
            f"QPushButton:checked {{"
            f"  background: {primary};"
            f"  color: {on_primary};"
            f"  border-color: {primary};"
            f"}}"
            f"QPushButton:checked:hover {{"
            f"  background: {primary};"
            f"  border-color: {primary};"
            f"}}"
            f"QPushButton:focus {{"
            f"  outline: none;"
            f"}}"
        )
        self._all_pill.setStyleSheet(pill_qss)
        for btn in self._pill_buttons.values():
            btn.setStyleSheet(pill_qss)
