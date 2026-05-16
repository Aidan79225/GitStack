"""Crash reporting via Sentry (opt-in by env var).

Disabled unless ``GITCRISP_SENTRY_DSN`` is set, so local dev runs never
ship events. Performance/profile sampling is forced to zero — the free
tier's quota is 5k errors/month and the desktop population doesn't
need transaction tracing.

``before_send`` redacts the user's HOME path from exception messages
and breadcrumbs, since repo paths frequently contain real names.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("gitcrisp")
    except PackageNotFoundError:
        return os.environ.get("GITCRISP_VERSION", "unknown")


def _redact_home(text: str, home: str) -> str:
    if not text:
        return text
    return text.replace(home, "~")


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    home = str(Path.home())
    for exc in event.get("exception", {}).get("values", []):
        if "value" in exc and isinstance(exc["value"], str):
            exc["value"] = _redact_home(exc["value"], home)
    for crumb in event.get("breadcrumbs", {}).get("values", []) or []:
        if isinstance(crumb.get("message"), str):
            crumb["message"] = _redact_home(crumb["message"], home)
    return event


def init_crash_reporting() -> bool:
    """Initialize Sentry if ``GITCRISP_SENTRY_DSN`` is set.

    Returns True if Sentry was initialized, False otherwise.
    Safe to call multiple times — the SDK itself is idempotent.
    """
    dsn = os.environ.get("GITCRISP_SENTRY_DSN")
    if not dsn:
        logger.debug("GITCRISP_SENTRY_DSN not set; crash reporting disabled")
        return False
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("sentry-sdk not installed; crash reporting disabled")
        return False

    sentry_sdk.init(
        dsn=dsn,
        release=f"gitcrisp@{_get_version()}",
        environment=os.environ.get("GITCRISP_ENV", "production"),
        traces_sample_rate=0.0,
        profiles_sample_rate=0.0,
        send_default_pii=False,
        before_send=_before_send,
    )
    logger.info("Crash reporting initialized")
    return True
