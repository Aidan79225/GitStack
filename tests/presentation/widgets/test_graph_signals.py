"""Signal and method-contract tests for GraphWidget.

Closes coverage gaps not addressed by test_graph_context_menu.py,
test_graph_synthetic.py, or test_keyboard_shortcuts.py: row-selection
emission, scroll_to_oid behavior, reload_with_extra_tip short-circuit,
set_buses bus-detach, and search-with-pending-load dispatch."""
from __future__ import annotations
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtWidgets import QWidget

from git_gui.domain.entities import Commit
from git_gui.presentation.models.graph_model import GraphModel
from git_gui.presentation.widgets.graph import GraphWidget


def _make_commit(oid: str, msg: str = "m") -> Commit:
    return Commit(
        oid=oid, message=msg, author="A <a@a.com>",
        timestamp=datetime(2026, 1, 1), parents=[],
    )


def _make_widget(qtbot, commits: list[Commit] | None = None) -> GraphWidget:
    """Create a minimal GraphWidget bypassing its heavy __init__.

    Same pattern as tests/presentation/widgets/test_graph_synthetic.py.
    """
    w = GraphWidget.__new__(GraphWidget)
    QWidget.__init__(w)

    w._queries = MagicMock()
    w._model = GraphModel(commits or [], {})
    w._loading = False
    w._loaded_count = len(commits or [])
    w._has_more = False
    w._reload_limit = 50
    w._pending_scroll_oid = None
    w._pending_search = None
    w._stash_btn = MagicMock()
    w._update_column_widths = lambda: None

    # _view is used by scroll_to_oid, clear_selection, and _on_row_changed.
    # A MagicMock suffices — we assert on call targets, not Qt rendering.
    w._view = MagicMock()

    # _search_bar is used by search handlers; mock it.
    w._search_bar = MagicMock()
    w._search_matches = []
    w._search_idx = -1

    qtbot.addWidget(w)
    return w


# ── 1. Row selection emits commit_selected ───────────────────────────────


def test_on_row_changed_emits_commit_selected_with_oid(qtbot):
    w = _make_widget(qtbot, commits=[_make_commit("first"), _make_commit("second")])

    # Build a QModelIndex pointing at row 1 (the "second" commit).
    current = w._model.index(1, 0)
    previous = QModelIndex()

    with qtbot.waitSignal(w.commit_selected, timeout=1000) as blocker:
        w._on_row_changed(current, previous)
    assert blocker.args == ["second"]


# ── 2. scroll_to_oid updates current row when select=True ────────────────


def test_scroll_to_oid_with_select_sets_current_index(qtbot):
    w = _make_widget(qtbot, commits=[
        _make_commit("A"), _make_commit("B"), _make_commit("C"),
    ])

    w.scroll_to_oid("B", select=True)

    # _view.setCurrentIndex should have been called once with an index
    # pointing at row 1 (the row holding B).
    assert w._view.setCurrentIndex.call_count == 1
    called_index = w._view.setCurrentIndex.call_args.args[0]
    assert called_index.row() == 1

    # _view.scrollTo should also have been called.
    assert w._view.scrollTo.call_count == 1


# ── 3. reload_with_extra_tip short-circuits when oid already in model ───


def test_reload_with_extra_tip_short_circuits_when_oid_present(qtbot):
    w = _make_widget(qtbot, commits=[
        _make_commit("X"), _make_commit("Y"),
    ])
    # Ensure reload is NOT called; replace it with a spy.
    w.reload = MagicMock()

    w.reload_with_extra_tip("X")

    w.reload.assert_not_called()
    # scroll_to_oid should have been called — verify via _view.setCurrentIndex.
    assert w._view.setCurrentIndex.call_count == 1


# ── 4. set_buses(None, None) clears model ────────────────────────────────


def test_set_buses_none_clears_model(qtbot):
    w = _make_widget(qtbot, commits=[_make_commit("A"), _make_commit("B")])
    assert w._model.rowCount() == 2

    w.set_buses(None, None)

    assert w._model.rowCount() == 0


# ── 5. Search with _has_more triggers full reload ────────────────────────


def test_search_with_has_more_triggers_full_reload_and_stores_query(qtbot):
    w = _make_widget(qtbot)
    w._has_more = True
    w.reload = MagicMock()

    w._on_search_text_changed("needle")

    # reload must be called with limit >= 999_999 (the "load everything" signal).
    w.reload.assert_called_once()
    call_kwargs = w.reload.call_args.kwargs
    assert call_kwargs.get("limit", 0) >= 999_999

    # Pending search should be stored for the post-reload dispatch.
    assert w._pending_search == "needle"
