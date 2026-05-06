# git_gui/presentation/widgets/commit_detail.py
from __future__ import annotations
from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget
from git_gui.domain.entities import Commit
from git_gui.presentation.theme import get_theme_manager, connect_widget
from git_gui.presentation.widgets.author_avatar import paint_avatar
from git_gui.presentation.widgets.avatar_loader import get_avatar_loader
from git_gui.presentation.widgets.ref_badge_delegate import (
    _badge_color, _badge_display_name, BADGE_RADIUS, BADGE_H_PAD, BADGE_V_PAD, BADGE_GAP,
)


def _muted() -> QColor:
    return get_theme_manager().current.colors.as_qcolor("on_surface_variant")


PAD = 12
AVATAR_SIZE = 36
AVATAR_GAP = 10


class CommitDetailWidget(QWidget):
    commit_oid_copy_requested = Signal(str)  # full 40-char OID

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._commit: Commit | None = None
        self._refs: list[str] = []
        self._avatar_hash: str | None = None
        self._oid_rect: QRect | None = None
        self.setMouseTracking(True)
        connect_widget(self)
        self._avatar_loader = get_avatar_loader()
        self._avatar_loader.avatar_ready.connect(self._on_avatar_ready)
        self._avatar_loader.enabled_changed.connect(lambda _v: self.update())

    def set_commit(self, commit: Commit, refs: list[str]) -> None:
        self._commit = commit
        self._refs = refs
        self._avatar_hash = self._avatar_loader.hash_for_author(commit.author)
        # Prime the cache; first call may kick off async fetch.
        self._avatar_loader.get_pixmap(commit.author)
        fm = self.fontMetrics()
        self.setFixedHeight(fm.height() * 3 + PAD * 4)
        self.update()

    def clear(self) -> None:
        self._commit = None
        self._refs = []
        self._avatar_hash = None
        self._oid_rect = None
        self.update()

    def _on_avatar_ready(self, email_hash: str) -> None:
        if email_hash == self._avatar_hash:
            self.update()

    def paintEvent(self, event) -> None:
        if self._commit is None:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        fm = painter.fontMetrics()
        line_h = fm.height()
        w = self.width()
        c = self._commit
        on_surface = get_theme_manager().current.colors.as_qcolor("on_surface")
        on_badge = get_theme_manager().current.colors.as_qcolor("on_badge")

        # ── Avatar (left, vertically centered) ───────────────────────────────
        avatar_y = (self.height() - AVATAR_SIZE) // 2
        avatar_rect = QRect(PAD, avatar_y, AVATAR_SIZE, AVATAR_SIZE)
        pixmap = self._avatar_loader.get_pixmap(c.author)
        paint_avatar(painter, avatar_rect, c.author, pixmap)
        text_left = PAD + AVATAR_SIZE + AVATAR_GAP

        # ── Line 1: Author + datetime ────────────────────────────────────────
        y = PAD
        painter.setPen(_muted())
        painter.drawText(text_left, y + fm.ascent(), "Author: ")
        label_w = fm.horizontalAdvance("Author: ")
        painter.setPen(on_surface)
        painter.drawText(text_left + label_w, y + fm.ascent(), c.author)
        ts = c.timestamp.strftime("%Y-%m-%d %H:%M")
        ts_w = fm.horizontalAdvance(ts)
        painter.setPen(_muted())
        painter.drawText(w - PAD - ts_w, y + fm.ascent(), ts)

        # ── Line 2: Hash + ref badges ────────────────────────────────────────
        y += line_h + PAD
        painter.setPen(_muted())
        painter.drawText(text_left, y + fm.ascent(), "Commit: ")
        x = text_left + fm.horizontalAdvance("Commit: ")
        oid_font = QFont(painter.font())
        oid_font.setUnderline(True)
        painter.setFont(oid_font)
        painter.setPen(on_surface)
        painter.drawText(x, y + fm.ascent(), c.oid)
        oid_w = fm.horizontalAdvance(c.oid)
        self._oid_rect = QRect(x, y, oid_w, line_h)
        # Restore the default font for whatever follows on this line.
        oid_font.setUnderline(False)
        painter.setFont(oid_font)
        x += oid_w + BADGE_GAP * 2

        badge_h = line_h + BADGE_V_PAD * 2
        cy = y + line_h // 2
        for name in self._refs:
            display = _badge_display_name(name)
            badge_w = fm.horizontalAdvance(display) + BADGE_H_PAD * 2
            badge_rect = QRect(x, cy - badge_h // 2, badge_w, badge_h)
            painter.setBrush(QBrush(_badge_color(name)))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(badge_rect, BADGE_RADIUS, BADGE_RADIUS)
            painter.setPen(on_badge)
            painter.drawText(badge_rect, Qt.AlignCenter, display)
            x += badge_w + BADGE_GAP

        # ── Line 3: Parent(s) ────────────────────────────────────────────────
        y += line_h + PAD
        painter.setPen(_muted())
        painter.drawText(text_left, y + fm.ascent(), "Parent: ")
        x = text_left + fm.horizontalAdvance("Parent: ")
        painter.setPen(on_surface)
        parents_text = "  ".join(c.parents) if c.parents else "(none)"
        painter.drawText(x, y + fm.ascent(), parents_text)

        painter.end()

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        if self._oid_rect is not None and self._oid_rect.contains(pos):
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        pos = event.position().toPoint()
        if (event.button() == Qt.LeftButton
                and self._oid_rect is not None
                and self._oid_rect.contains(pos)
                and self._commit is not None):
            self.commit_oid_copy_requested.emit(self._commit.oid)
            event.accept()
            return
        super().mousePressEvent(event)
