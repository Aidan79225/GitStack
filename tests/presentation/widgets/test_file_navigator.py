"""Tests for FileNavigatorWidget."""
from __future__ import annotations

import pytest

from git_gui.domain.entities import FileStatus
from git_gui.presentation.models.diff_model import DiffModel
from git_gui.presentation.widgets.file_navigator import FileNavigatorWidget, NavMode


@pytest.fixture
def files():
    return [
        FileStatus(path="a.py", status="staged", delta="modified"),
        FileStatus(path="b.py", status="staged", delta="added"),
        FileStatus(path="c.py", status="staged", delta="deleted"),
    ]


@pytest.fixture
def navigator(qtbot, files):
    model = DiffModel(files)
    widget = FileNavigatorWidget(model)
    qtbot.addWidget(widget)
    widget.show()
    return widget, model


def test_default_mode_is_list(navigator):
    widget, _ = navigator
    assert widget.mode() == NavMode.LIST
    assert widget._list_view.isVisible()


def test_set_mode_list_shows_list_view(navigator):
    widget, _ = navigator
    widget.set_mode(NavMode.LIST)
    assert widget._stack.currentWidget() is widget._list_view


def test_selection_model_is_list_views(navigator):
    widget, _ = navigator
    assert widget.selection_model is widget._list_view.selectionModel()


def test_currentChanged_signal_propagates_from_list_view(navigator, qtbot):
    widget, model = navigator
    received = []
    widget.currentChanged.connect(lambda cur, prev: received.append(cur.row()))

    idx = model.index(1)
    widget.selection_model.setCurrentIndex(idx, widget.selection_model.SelectionFlag.ClearAndSelect)

    assert received == [1]


def test_deselected_signal_propagates_from_list_view(navigator, qtbot):
    widget, model = navigator
    received = []
    widget.deselected.connect(lambda: received.append(True))

    widget._list_view.deselected.emit()

    assert received == [True]


# ── Pill mode ──────────────────────────────────────────────────────────


def test_set_mode_pill_shows_pill_strip(navigator):
    widget, _ = navigator
    widget.set_mode(NavMode.PILL)
    assert widget.mode() == NavMode.PILL
    assert widget._stack.currentWidget() is widget._pill_root


def test_pill_strip_has_all_pill_plus_one_per_file(navigator):
    widget, _ = navigator
    widget.set_mode(NavMode.PILL)
    # 1 "All" pill + 3 file pills (a.py, b.py, c.py)
    assert len(widget._pill_buttons) == 3
    assert widget._all_pill is not None


def test_clicking_pill_updates_shared_selection(navigator, qtbot):
    widget, model = navigator
    widget.set_mode(NavMode.PILL)

    # Click the pill for "b.py" (row 1)
    pill = widget._pill_buttons["b.py"]
    pill.click()

    assert widget.selection_model.currentIndex().row() == 1
    assert widget.selection_model.hasSelection()


def test_clicking_all_pill_clears_selection(navigator, qtbot):
    widget, model = navigator
    widget.set_mode(NavMode.PILL)

    # First select something via the list view's selection model
    widget.selection_model.setCurrentIndex(
        model.index(1),
        widget.selection_model.SelectionFlag.ClearAndSelect,
    )
    assert widget.selection_model.hasSelection()

    # Then click "All"
    widget._all_pill.click()

    assert not widget.selection_model.hasSelection()


def test_set_active_file_marks_corresponding_pill_checked(navigator):
    widget, _ = navigator
    widget.set_mode(NavMode.PILL)

    widget.set_active_file("c.py")

    assert widget._pill_buttons["c.py"].isChecked()
    assert not widget._pill_buttons["a.py"].isChecked()
    assert not widget._pill_buttons["b.py"].isChecked()


def test_set_active_file_does_not_change_selection(navigator):
    widget, _ = navigator
    widget.set_mode(NavMode.PILL)

    widget.set_active_file("a.py")

    assert not widget.selection_model.hasSelection()


def test_set_active_file_none_marks_all_pill(navigator):
    widget, _ = navigator
    widget.set_mode(NavMode.PILL)

    widget.set_active_file(None)

    assert widget._all_pill.isChecked()
    assert not any(p.isChecked() for p in widget._pill_buttons.values())


def test_model_reset_rebuilds_pill_strip(navigator, qtbot):
    from git_gui.domain.entities import FileStatus
    widget, model = navigator
    widget.set_mode(NavMode.PILL)

    new_files = [FileStatus(path="x.py", status="staged", delta="modified")]
    model.reload(new_files)

    assert "x.py" in widget._pill_buttons
    assert "a.py" not in widget._pill_buttons


def test_clicking_active_pill_keeps_visual_in_sync(navigator, qtbot):
    """Re-clicking an already-active pill should not desync visual state.

    QPushButton.click() toggles checked before emitting clicked, so without
    a defensive resync the pill would end up unchecked while the selection
    model still holds it selected.
    """
    widget, _ = navigator
    widget.set_mode(NavMode.PILL)

    pill = widget._pill_buttons["b.py"]
    pill.click()  # First click: select b.py
    assert widget.selection_model.currentIndex().row() == 1
    assert pill.isChecked()

    pill.click()  # Second click on the same pill
    assert widget.selection_model.currentIndex().row() == 1, "selection should still be b.py"
    assert pill.isChecked(), "pill should remain checked since selection didn't change"


def test_set_active_file_unknown_path_falls_back_to_all(navigator):
    """An unknown path (e.g., stale after model reload) highlights All, not nothing."""
    widget, _ = navigator
    widget.set_mode(NavMode.PILL)

    widget.set_active_file("nonexistent.py")

    assert widget._all_pill.isChecked()
    assert not any(p.isChecked() for p in widget._pill_buttons.values())
