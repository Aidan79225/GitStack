# git_gui/presentation/widgets/file_list_view.py
"""Shared QListView subclass with click-to-deselect and checkbox-without-select."""
from __future__ import annotations
from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtWidgets import QListView, QStyle, QStyleOptionViewItem


class FileListView(QListView):
    """QListView with two custom click behaviors:

    1. Clicking the checkbox indicator toggles the check state WITHOUT changing
       the row selection (so the blue highlight on another row is preserved).
    2. Clicking an already-selected row deselects it and emits ``deselected``,
       without delegating to ``super()`` so Qt cannot re-select.
    """

    deselected = Signal()

    def _checkbox_rect(self, index):
        """Return the QRect of the check indicator for *index*, or None."""
        if not index.isValid():
            return None
        opt = QStyleOptionViewItem()
        self.initViewItemOption(opt)
        opt.rect = self.visualRect(index)
        opt.features |= QStyleOptionViewItem.HasCheckIndicator
        return self.style().subElementRect(
            QStyle.SE_ItemViewItemCheckIndicator, opt, self
        )

    def mousePressEvent(self, event) -> None:
        clicked = self.indexAt(event.pos())

        # Case 1: click on the checkbox indicator → toggle without selection change
        if clicked.isValid() and (self.model().flags(clicked) & Qt.ItemIsUserCheckable):
            check_rect = self._checkbox_rect(clicked)
            if check_rect is not None and check_rect.contains(event.pos()):
                current = clicked.data(Qt.CheckStateRole)
                is_checked = current == Qt.CheckState.Checked or current == Qt.Checked
                new_state = Qt.CheckState.Unchecked if is_checked else Qt.CheckState.Checked
                self.model().setData(clicked, new_state, Qt.CheckStateRole)
                return  # do NOT call super → selection unchanged

        # Case 2: click on the already-selected row → deselect
        current = self.currentIndex()
        if (clicked.isValid() and clicked == current
                and self.selectionModel().isSelected(current)):
            self.selectionModel().clear()
            self.setCurrentIndex(QModelIndex())
            self.viewport().update()
            self.deselected.emit()
            return

        super().mousePressEvent(event)


# ── Delegate for FileListView's default look ─────────────────────────────
# Moved here from diff.py so FileListView and FileNavigatorWidget can both
# use it without circular imports.

from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QBrush, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from git_gui.presentation.theme import get_theme_manager


DELTA_LABEL = {
    "modified": "M",
    "added":    "A",
    "deleted":  "D",
    "renamed":  "R",
    "unknown":  "?",
}

BADGE_SIZE = 20
BADGE_GAP = 6


class FileDeltaDelegate(QStyledItemDelegate):
    """Paints a colored delta badge plus the file path for a FileListView row."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        rect = option.rect

        if option.state & QStyle.State_Selected:
            painter.fillRect(rect, get_theme_manager().current.colors.as_qcolor("primary"))

        fs = index.data(Qt.UserRole)
        delta = fs.delta if fs else "unknown"
        label = DELTA_LABEL.get(delta, "?")

        badge_x = rect.left() + 4
        badge_y = rect.top() + (rect.height() - BADGE_SIZE) // 2
        badge_rect = QRect(badge_x, badge_y, BADGE_SIZE, BADGE_SIZE)
        painter.setBrush(QBrush(get_theme_manager().current.colors.status_color(delta)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(badge_rect, 3, 3)

        painter.setPen(get_theme_manager().current.colors.as_qcolor("on_badge"))
        painter.drawText(badge_rect, Qt.AlignCenter, label)

        text_x = badge_x + BADGE_SIZE + BADGE_GAP
        text_rect = QRect(text_x, rect.top(), rect.right() - text_x, rect.height())
        painter.setPen(option.palette.text().color())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, index.data(Qt.DisplayRole) or "")

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(option.rect.width(), max(BADGE_SIZE + 8, option.fontMetrics.height() + 8))
