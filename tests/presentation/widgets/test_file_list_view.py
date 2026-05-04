"""Tests for FileListView's row-cap sizing.

Verifies that the QListView reports a sizeHint that grows with row count
up to MAX_VISIBLE_ROWS = 5, then caps. Also verifies the internal
vertical scrollbar correctly reflects overflow when the cap is hit.
"""
from __future__ import annotations

import pytest

from git_gui.domain.entities import FileStatus
from git_gui.presentation.models.diff_model import DiffModel
from git_gui.presentation.widgets.file_list_view import (
    FileDeltaDelegate,
    FileListView,
)


def _files(n: int) -> list[FileStatus]:
    return [
        FileStatus(path=f"file_{i}.py", status="staged", delta="modified")
        for i in range(n)
    ]


@pytest.fixture
def make_view(qtbot):
    """Factory: builds a FileListView with N files. Resizes width so the
    delegate has a known viewport for sizeHintForRow to compute against."""
    def _make(n: int):
        model = DiffModel(_files(n))
        view = FileListView()
        view.setItemDelegate(FileDeltaDelegate(view))
        view.setModel(model)
        qtbot.addWidget(view)
        view.resize(200, 500)
        view.show()
        qtbot.wait(1)  # Let Qt compute sizeHintForRow once visible
        return view, model
    return _make


def _row_h(view: FileListView) -> int:
    """Look up row height from the live view (depends on font + delegate)."""
    h = view.sizeHintForRow(0)
    if h <= 0:
        h = FileListView._FALLBACK_ROW_HEIGHT
    return h


def test_sizeHint_height_for_three_rows_is_three_row_heights(make_view):
    view, _ = make_view(3)
    expected = 3 * _row_h(view) + 2 * view.frameWidth()
    assert view.sizeHint().height() == expected


def test_sizeHint_height_caps_at_five_rows_for_ten_files(make_view):
    view, _ = make_view(10)
    expected = 5 * _row_h(view) + 2 * view.frameWidth()
    assert view.sizeHint().height() == expected


def test_sizeHint_height_for_empty_model_collapses(make_view):
    view, _ = make_view(0)
    # Zero rows × any row_h is zero; only the frame border remains.
    assert view.sizeHint().height() == 2 * view.frameWidth()


def test_sizeHint_updates_after_model_reload(make_view, qtbot):
    view, model = make_view(3)
    row_h = _row_h(view)
    assert view.sizeHint().height() == 3 * row_h + 2 * view.frameWidth()

    model.reload(_files(10))
    qtbot.wait(1)
    assert view.sizeHint().height() == 5 * row_h + 2 * view.frameWidth()

    model.reload(_files(2))
    qtbot.wait(1)
    assert view.sizeHint().height() == 2 * row_h + 2 * view.frameWidth()


def test_internal_vertical_scrollbar_has_range_when_over_five_rows(make_view, qtbot):
    view, _ = make_view(10)
    row_h = _row_h(view)
    # Resize view to exactly the cap so the 10-row content overflows.
    view.resize(view.width(), 5 * row_h + 2 * view.frameWidth())
    qtbot.wait(1)
    assert view.verticalScrollBar().maximum() > 0


def test_internal_vertical_scrollbar_has_no_range_when_five_or_fewer_rows(
    make_view, qtbot
):
    view, _ = make_view(5)
    row_h = _row_h(view)
    view.resize(view.width(), 5 * row_h + 2 * view.frameWidth())
    qtbot.wait(1)
    assert view.verticalScrollBar().maximum() == 0
