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
