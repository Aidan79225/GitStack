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
