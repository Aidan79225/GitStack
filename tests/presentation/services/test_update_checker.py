"""Tests for fetch_latest_release.

The function is sync and pure — mock urllib.request.urlopen with a
context manager whose .read() returns bytes.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from git_gui.presentation.services.update_checker import fetch_latest_release


def _fake_response(payload: dict, status: int = 200):
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.status = status
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_returns_tag_and_url_on_success():
    payload = {
        "tag_name": "v0.16.0",
        "html_url": "https://github.com/Aidan79225/GitCrisp/releases/tag/v0.16.0",
    }
    with patch("urllib.request.urlopen", return_value=_fake_response(payload)):
        result = fetch_latest_release(
            "https://api.github.com/repos/Aidan79225/GitCrisp/releases/latest"
        )
    assert result == (
        "v0.16.0",
        "https://github.com/Aidan79225/GitCrisp/releases/tag/v0.16.0",
    )


def test_returns_none_on_network_error():
    with patch("urllib.request.urlopen", side_effect=URLError("DNS")):
        assert fetch_latest_release("https://api.github.com/...") is None


def test_returns_none_on_missing_keys():
    payload = {"tag_name": "v0.16.0"}  # no html_url
    with patch("urllib.request.urlopen", return_value=_fake_response(payload)):
        assert fetch_latest_release("https://api.github.com/...") is None


def test_returns_none_on_malformed_json():
    resp = MagicMock()
    resp.read.return_value = b"not-json"
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp):
        assert fetch_latest_release("https://api.github.com/...") is None
