"""Integration tests for DiffWidget lazy loading flow."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from git_gui.domain.entities import Branch, Commit, FileStatus
from git_gui.presentation.widgets.diff import DiffWidget


def _make_mock_queries():
    """Build a MagicMock that satisfies every QueryBus attribute DiffWidget touches."""
    queries = MagicMock()

    # get_commit_detail.execute(oid) -> Commit
    queries.get_commit_detail.execute.return_value = Commit(
        oid="abc123",
        message="Initial commit\n",
        author="Test Author",
        timestamp=datetime(2025, 1, 1),
        parents=[],
    )

    # get_branches.execute() -> list[Branch]
    queries.get_branches.execute.return_value = [
        Branch(name="main", is_remote=False, is_head=True, target_oid="abc123"),
    ]

    # get_commit_files.execute(oid) -> list[FileStatus]
    queries.get_commit_files.execute.return_value = [
        FileStatus(path="hello.py", status="staged", delta="added"),
    ]

    # list_submodules.execute() -> []
    queries.list_submodules.execute.return_value = []

    # get_commit_diff_map.execute(oid) -> dict  (background thread)
    queries.get_commit_diff_map.execute.return_value = {}

    return queries


@pytest.fixture
def diff_widget(qtbot):
    queries = _make_mock_queries()
    commands = MagicMock()
    widget = DiffWidget(queries, commands)
    qtbot.addWidget(widget)
    widget.show()
    return widget, queries


# ── 1. load_commit shows panels ───────────────────────────────────────


def test_load_commit_shows_panels(diff_widget, qtbot):
    """After a successful load_commit, detail/message/scroll_area are visible."""
    widget, queries = diff_widget

    # Patch Thread so _render_all_files doesn't spawn a real thread
    with patch("threading.Thread"):
        widget.load_commit("abc123")

    assert widget._detail.isVisible()
    assert widget._msg_view.isVisible()
    assert widget._scroll_area.isVisible()
    assert widget._file_navigator.isVisible()


# ── 2. load_commit error hides panels ─────────────────────────────────


def test_load_commit_error_hides_panels(diff_widget, qtbot):
    """When get_commit_detail raises, the widget enters empty state."""
    widget, queries = diff_widget

    queries.get_commit_detail.execute.side_effect = RuntimeError("gone")

    widget.load_commit("bad_oid")

    assert not widget._detail.isVisible()
    assert not widget._msg_view.isVisible()
    assert not widget._scroll_area.isVisible()
    assert not widget._file_navigator.isVisible()


# ── 3. set_buses(None, None) enters empty state ──────────────────────


def test_set_buses_none_enters_empty_state(diff_widget, qtbot):
    """Calling set_buses(None, None) hides all panels."""
    widget, queries = diff_widget

    # First show panels so we can verify they get hidden
    with patch("threading.Thread"):
        widget.load_commit("abc123")
    assert widget._scroll_area.isVisible()

    widget.set_buses(None, None)

    assert not widget._detail.isVisible()
    assert not widget._msg_view.isVisible()
    assert not widget._scroll_area.isVisible()
    assert not widget._file_navigator.isVisible()


# ── 4. _clear_blocks clears loader ───────────────────────────────────


def test_clear_blocks_clears_loader(diff_widget, qtbot):
    """_clear_blocks() empties the loader's block_refs list."""
    widget, queries = diff_widget

    # Populate blocks via load_commit
    with patch("threading.Thread"):
        widget.load_commit("abc123")

    # Loader should have block refs from _render_all_files
    assert widget._loader is not None
    assert len(widget._loader._block_refs) > 0

    widget._clear_blocks()

    assert widget._loader._block_refs == []
    assert widget._loader._loaded_paths == set()
    assert widget._loader._diff_map == {}


# ── 5. Sticky-pin controller ─────────────────────────────────────────


from git_gui.presentation.widgets.file_navigator import NavMode


def test_threshold_recomputes_to_flow_slot_top_after_load(diff_widget, qtbot):
    """recompute_threshold reads _flow_slot.geometry().top() and stores it."""
    widget, _ = diff_widget
    with patch("threading.Thread"):
        widget.load_commit("abc123")
    widget.adjustSize()
    widget.layout().activate()
    # Whatever value Qt computed for _flow_slot.geometry().top() must equal
    # what the controller cached during load_commit's recompute call.
    assert widget._sticky_controller._threshold == widget._flow_slot.geometry().top()


def test_pin_when_scroll_passes_threshold(diff_widget, qtbot):
    """Driving _on_scroll past _threshold reparents the navigator to _pin_slot."""
    widget, _ = diff_widget
    with patch("threading.Thread"):
        widget.load_commit("abc123")

    # Inject a known threshold so the test does not depend on Qt geometry,
    # which is unreliable for a hidden/small qtbot widget.
    widget._sticky_controller._threshold = 100
    widget._sticky_controller._on_scroll(150)

    assert widget._sticky_controller._pinned is True
    assert widget._file_navigator.parent() is widget._pin_slot
    assert widget._file_navigator.mode() == NavMode.PILL


def test_unpin_when_scroll_below_threshold_minus_hysteresis(diff_widget, qtbot):
    widget, _ = diff_widget
    with patch("threading.Thread"):
        widget.load_commit("abc123")

    widget._sticky_controller._threshold = 100
    widget._sticky_controller._on_scroll(150)
    assert widget._sticky_controller._pinned

    # Drop well below threshold (more than hysteresis = 4)
    widget._sticky_controller._on_scroll(50)

    assert widget._sticky_controller._pinned is False
    assert widget._file_navigator.parent() is widget._flow_slot
    assert widget._file_navigator.mode() == NavMode.LIST


def test_hysteresis_prevents_unpin_just_below_threshold(diff_widget, qtbot):
    widget, _ = diff_widget
    with patch("threading.Thread"):
        widget.load_commit("abc123")

    widget._sticky_controller._threshold = 100
    widget._sticky_controller._on_scroll(150)
    assert widget._sticky_controller._pinned

    # Within hysteresis (98 > threshold - 4 = 96): stay pinned
    widget._sticky_controller._on_scroll(98)
    assert widget._sticky_controller._pinned is True

    # Outside hysteresis (95 < 96): unpin
    widget._sticky_controller._on_scroll(95)
    assert widget._sticky_controller._pinned is False


def test_load_error_forces_unpin(diff_widget, qtbot):
    widget, queries = diff_widget
    with patch("threading.Thread"):
        widget.load_commit("abc123")

    widget._sticky_controller._threshold = 100
    widget._sticky_controller._on_scroll(150)
    assert widget._sticky_controller._pinned

    queries.get_commit_detail.execute.side_effect = RuntimeError("gone")
    widget.load_commit("bad_oid")

    assert widget._sticky_controller._pinned is False
    assert widget._file_navigator.parent() is widget._flow_slot


# ── 6. Auto-highlight on scroll ───────────────────────────────────────


@pytest.fixture
def multi_file_diff_widget(qtbot):
    """A DiffWidget loaded with three files for auto-highlight testing."""
    queries = _make_mock_queries()
    queries.get_commit_files.execute.return_value = [
        FileStatus(path="a.py", status="staged", delta="modified"),
        FileStatus(path="b.py", status="staged", delta="added"),
        FileStatus(path="c.py", status="staged", delta="deleted"),
    ]
    commands = MagicMock()
    widget = DiffWidget(queries, commands)
    qtbot.addWidget(widget)
    widget.show()
    with patch("threading.Thread"):
        widget.load_commit("abc123")
    widget.adjustSize()
    widget.layout().activate()
    return widget, queries


def test_auto_highlight_calls_set_active_file_when_pinned_and_unfiltered(
    multi_file_diff_widget, qtbot
):
    """When _on_scroll runs while pinned + unfiltered, the controller
    consults _find_active_file_block and calls set_active_file with its result.

    Stubbed: threshold (so we can pin without depending on real geometry) and
    _find_active_file_block (so we don't depend on file frames having real
    geometry in a hidden qtbot widget).
    """
    widget, _ = multi_file_diff_widget

    # Pin via the controller's own logic (deterministic).
    widget._sticky_controller._threshold = 100
    widget._sticky_controller._on_scroll(150)
    assert widget._sticky_controller._pinned

    # Stub the block-finder to return a known path.
    widget._sticky_controller._find_active_file_block = lambda v: "b.py"

    # Spy on set_active_file.
    calls = []
    widget._file_navigator.set_active_file = lambda p: calls.append(p)

    # Trigger another scroll event.
    widget._sticky_controller._on_scroll(200)

    assert calls == ["b.py"]


def test_auto_highlight_disabled_while_filtered(multi_file_diff_widget, qtbot):
    widget, queries = multi_file_diff_widget
    queries.get_file_diff.execute.return_value = []

    # Pin
    widget._sticky_controller._threshold = 100
    widget._sticky_controller._on_scroll(150)
    assert widget._sticky_controller._pinned

    # Filter to one file (sets the selection model)
    widget._file_navigator.selection_model.setCurrentIndex(
        widget._diff_model.index(1),
        widget._file_navigator.selection_model.SelectionFlag.ClearAndSelect,
    )

    # Stub the block-finder so we'd see calls if the gate failed.
    widget._sticky_controller._find_active_file_block = lambda v: "b.py"

    # Spy
    calls = []
    widget._file_navigator.set_active_file = lambda p: calls.append(p)

    # Scroll while filtered.
    widget._sticky_controller._on_scroll(200)

    assert calls == [], f"set_active_file should not fire while filtered; got {calls}"


def test_auto_highlight_disabled_while_unpinned(multi_file_diff_widget, qtbot):
    widget, _ = multi_file_diff_widget

    # Stay unpinned; threshold high enough that _on_scroll(50) doesn't pin.
    widget._sticky_controller._threshold = 100

    # Stub
    widget._sticky_controller._find_active_file_block = lambda v: "b.py"

    # Spy
    calls = []
    widget._file_navigator.set_active_file = lambda p: calls.append(p)

    widget._sticky_controller._on_scroll(50)

    assert widget._sticky_controller._pinned is False
    assert calls == [], f"set_active_file should not fire while unpinned; got {calls}"
