"""Tests for commit error surfacing in WorkingTreeWidget._on_commit."""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtWidgets import QPlainTextEdit, QWidget

from git_gui.presentation.widgets.working_tree import WorkingTreeWidget


def _make_commit_widget(qtbot) -> WorkingTreeWidget:
    """Create a WorkingTreeWidget with minimal init bypass for commit-path tests."""
    w = WorkingTreeWidget.__new__(WorkingTreeWidget)
    QWidget.__init__(w)
    w._msg_edit = QPlainTextEdit()
    qtbot.addWidget(w)
    return w


def test_on_commit_emits_failed_when_create_commit_raises(qtbot, monkeypatch):
    """When create_commit.execute raises, _on_commit must emit
    commit_failed with the error text and not call reload."""
    queries = MagicMock()
    commands = MagicMock()
    queries.get_identity.execute.return_value = ("Alice", "alice@example.com")
    commands.create_commit.execute.side_effect = RuntimeError("boom")

    w = _make_commit_widget(qtbot)
    w._queries = queries
    w._commands = commands

    received: list[str] = []
    w.commit_failed.connect(lambda reason: received.append(reason))
    reload_called = []
    w.reload_requested.connect(lambda: reload_called.append(True))

    w._msg_edit.setPlainText("test commit message")
    # Simulate a clean repo state.
    w._current_state = "CLEAN"
    w._on_commit()

    assert received == ["Commit failed: boom"]
    assert reload_called == []
