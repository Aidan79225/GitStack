"""Application-wide preferences backed by QSettings.

Keys are namespaced under group prefixes so future settings stay
organized. Add new helpers here rather than poking QSettings directly
from feature modules so tests have a single mock surface.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

_KEY_CHECK_UPDATES = "updates/check_on_startup"


def get_check_updates() -> bool:
    """Return whether the app should check for updates on startup. Default True."""
    return QSettings().value(_KEY_CHECK_UPDATES, True, type=bool)


def set_check_updates(value: bool) -> None:
    """Persist the update-check preference."""
    QSettings().setValue(_KEY_CHECK_UPDATES, value)
