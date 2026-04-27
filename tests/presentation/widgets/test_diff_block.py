"""Tests for chunked rendering of large hunks in diff_block."""
from __future__ import annotations
from PySide6.QtCore import QEvent
from PySide6.QtGui import QTextDocument, QTextCursor
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from git_gui.domain.entities import Hunk
from git_gui.presentation.widgets import diff_block
from git_gui.presentation.widgets.diff_block import (
    render_hunk_content_lines, make_diff_formats,
)


def _make_cursor(qtbot):
    edit = QPlainTextEdit()
    qtbot.addWidget(edit)
    return edit.textCursor(), edit


def test_small_hunk_renders_immediately(qtbot):
    """A 50-line hunk is fully rendered in the initial call."""
    lines = [(" ", f"line {i}\n") for i in range(50)]
    hunk = Hunk(header="@@ -1,50 +1,50 @@", lines=lines)
    cursor, edit = _make_cursor(qtbot)
    formats = make_diff_formats()

    render_hunk_content_lines(cursor, hunk, formats)

    assert edit.document().blockCount() >= 50


def test_large_hunk_renders_first_chunk_immediately(qtbot):
    """A 500-line hunk has at least 100 lines rendered immediately."""
    lines = [(" ", f"line {i}\n") for i in range(500)]
    hunk = Hunk(header="@@ -1,500 +1,500 @@", lines=lines)
    cursor, edit = _make_cursor(qtbot)
    formats = make_diff_formats()

    render_hunk_content_lines(cursor, hunk, formats)

    # Immediately after the call, first chunk (100 lines) should be rendered
    assert edit.document().blockCount() >= 100


def test_large_hunk_completes_rendering_after_event_loop(qtbot):
    """A 500-line hunk completes rendering after the event loop processes QTimer callbacks."""
    lines = [(" ", f"line {i}\n") for i in range(500)]
    hunk = Hunk(header="@@ -1,500 +1,500 @@", lines=lines)
    cursor, edit = _make_cursor(qtbot)
    formats = make_diff_formats()

    render_hunk_content_lines(cursor, hunk, formats)

    # Wait for QTimer.singleShot callbacks to fire
    qtbot.wait(200)
    assert edit.document().blockCount() >= 500


def test_chunked_render_canceled_when_widget_deleted(qtbot, monkeypatch):
    """Regression: scheduling chunked rendering then destroying the parent
    QPlainTextEdit must not invoke _render_lines_range against the destroyed
    QTextDocument. Without the QTimer.singleShot context guard, the deferred
    callback dereferences a dangling cursor → EXCEPTION_ACCESS_VIOLATION on
    Windows (faulthandler-confirmed in the wild)."""
    lines = [(" ", f"line {i}\n") for i in range(500)]
    hunk = Hunk(header="@@ -1,500 +1,500 @@", lines=lines)

    calls: list[tuple] = []
    monkeypatch.setattr(
        diff_block, "_render_lines_range",
        lambda *args, **kwargs: calls.append(args),
    )

    cursor, edit = _make_cursor(qtbot)
    formats = make_diff_formats()
    render_hunk_content_lines(cursor, hunk, formats)
    assert len(calls) == 1, "first chunk should render synchronously"

    # Destroy the widget (and its QTextDocument). Force the DeferredDelete
    # event to run before the singleShot timer fires.
    edit.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    qtbot.wait(50)

    assert len(calls) == 1, (
        "no chunk should render after the parent widget is deleted; "
        "the QTimer.singleShot context guard must cancel the pending callback"
    )
