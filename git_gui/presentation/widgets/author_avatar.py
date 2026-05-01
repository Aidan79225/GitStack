# git_gui/presentation/widgets/author_avatar.py
from __future__ import annotations
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap

_PALETTE = [
    "#e57373", "#f06292", "#ba68c8", "#9575cd",
    "#7986cb", "#64b5f6", "#4fc3f7", "#4dd0e1",
    "#4db6ac", "#81c784", "#aed581", "#dce775",
    "#ffd54f", "#ffb74d", "#ff8a65", "#a1887f",
]


def _initials(author: str) -> str:
    name = author.split("<")[0].strip() if "<" in author else author.strip()
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    if parts:
        return parts[0][0].upper()
    return "?"


def _color_for_author(author: str) -> QColor:
    h = 0
    for ch in author:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return QColor(_PALETTE[h % len(_PALETTE)])


def paint_avatar(painter: QPainter, rect: QRect, author: str) -> None:
    """Paint a circular initials avatar inside *rect* (should be square)."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)

    path = QPainterPath()
    center = rect.center()
    radius = min(rect.width(), rect.height()) / 2.0
    path.addEllipse(center, radius, radius)

    painter.setClipPath(path)
    painter.fillRect(rect, _color_for_author(author))

    painter.setPen(QColor("#ffffff"))
    font = painter.font()
    font.setPixelSize(max(int(radius * 0.9), 8))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(rect, Qt.AlignCenter, _initials(author))

    painter.restore()
