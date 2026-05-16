from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from git_gui.observability import _before_send, init_crash_reporting


def test_init_returns_false_when_dsn_missing(monkeypatch):
    monkeypatch.delenv("GITCRISP_SENTRY_DSN", raising=False)
    assert init_crash_reporting() is False


def test_init_calls_sentry_when_dsn_set(monkeypatch):
    monkeypatch.setenv("GITCRISP_SENTRY_DSN", "https://key@example.ingest.sentry.io/123")
    fake_sentry = MagicMock()
    with patch.dict("sys.modules", {"sentry_sdk": fake_sentry}):
        assert init_crash_reporting() is True
    fake_sentry.init.assert_called_once()
    kwargs = fake_sentry.init.call_args.kwargs
    assert kwargs["dsn"] == "https://key@example.ingest.sentry.io/123"
    assert kwargs["traces_sample_rate"] == 0.0
    assert kwargs["profiles_sample_rate"] == 0.0
    assert kwargs["send_default_pii"] is False
    assert kwargs["release"].startswith("gitcrisp@")


def test_before_send_redacts_home_in_exception_value():
    home = str(Path.home())
    event = {
        "exception": {
            "values": [
                {"type": "FileNotFoundError", "value": f"No such file: {home}/secret/repo"},
            ]
        }
    }
    out = _before_send(event, {})
    assert out is not None
    assert home not in out["exception"]["values"][0]["value"]
    assert "~/secret/repo" in out["exception"]["values"][0]["value"]


def test_before_send_redacts_home_in_breadcrumbs():
    home = str(Path.home())
    event = {
        "breadcrumbs": {
            "values": [{"message": f"opened {home}/work/proj"}],
        }
    }
    out = _before_send(event, {})
    assert out is not None
    assert "~/work/proj" in out["breadcrumbs"]["values"][0]["message"]
