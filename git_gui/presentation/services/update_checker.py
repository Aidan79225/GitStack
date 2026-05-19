"""GitHub release-check service.

Two layers:

- `fetch_latest_release`: pure sync function. Easy to test by patching
  `urllib.request.urlopen`. Returns ``(tag, html_url)`` or ``None`` for
  any failure (network, HTTP, JSON, missing fields).
- `UpdateChecker`: a QObject that runs ``fetch_latest_release`` on a
  background ``QThread`` and emits ``update_available(version, url)``
  when the remote version is newer than the running one. (Added in the
  next task.)
"""

from __future__ import annotations

import json
import logging
import urllib.request

from packaging.version import InvalidVersion, Version
from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)

LATEST_RELEASE_URL = "https://api.github.com/repos/Aidan79225/GitCrisp/releases/latest"
_TIMEOUT_SECONDS = 5


def fetch_latest_release(url: str) -> tuple[str, str] | None:
    """Return ``(tag_name, html_url)`` for the latest release, or None on any failure."""
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as resp:
            body = resp.read()
    except Exception as e:
        logger.debug("Update check network error: %s", e)
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        logger.debug("Update check JSON decode error: %s", e)
        return None
    tag = payload.get("tag_name")
    url_ = payload.get("html_url")
    if not isinstance(tag, str) or not isinstance(url_, str):
        logger.debug("Update check payload missing tag_name/html_url")
        return None
    return tag, url_


class _CheckWorker(QObject):
    finished = Signal(object)  # tuple[str, str] | None

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url

    def run(self) -> None:
        self.finished.emit(fetch_latest_release(self._url))


class UpdateChecker(QObject):
    """Background GitHub release check. Emits when a newer release is found.

    Owns its worker thread. ``check()`` is fire-and-forget; if you need
    to re-check later, just call it again.
    """

    update_available = Signal(str, str)  # (version_tag, html_url)

    def __init__(
        self,
        current_version: str,
        url: str = LATEST_RELEASE_URL,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._current_version = current_version
        self._url = url
        self._thread: QThread | None = None
        self._worker: _CheckWorker | None = None

    def check(self) -> None:
        self._thread = QThread()
        self._worker = _CheckWorker(self._url)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_finished(self, result: tuple[str, str] | None) -> None:
        if result is None:
            return
        tag, url = result
        try:
            remote = Version(tag.lstrip("v"))
            current = Version(self._current_version.lstrip("v"))
        except InvalidVersion as e:
            logger.debug("Update check version parse failed: %s", e)
            return
        if remote > current:
            self.update_available.emit(tag, url)
