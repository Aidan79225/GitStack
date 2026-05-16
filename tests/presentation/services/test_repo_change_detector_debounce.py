"""Debounce behaviour of RepoChangeDetector — events within 200 ms coalesce
into a single reload callback."""

from __future__ import annotations

import pytest

from git_gui.presentation.services.repo_change_detector import RepoChangeDetector


@pytest.fixture
def detector(qtbot, tmp_path):
    """Construct a detector rooted in an empty temp directory. The .git/
    watch paths all fail to add (dir missing), which is fine — we exercise
    only the debouncer here."""
    calls: list[None] = []
    d = RepoChangeDetector(str(tmp_path), on_reload=lambda: calls.append(None))
    # RepoChangeDetector is a plain QObject, not a QWidget, so don't
    # register with qtbot.addWidget — the fixture holding the reference
    # keeps it alive for the test's duration.
    yield d, calls
    d.stop()


def test_single_event_triggers_one_reload_after_debounce(detector, qtbot):
    d, calls = detector
    d._schedule_reload()
    # Immediately: not yet fired.
    assert calls == []
    # After 300 ms: fired exactly once.
    qtbot.wait(300)
    assert len(calls) == 1


def test_multiple_events_within_debounce_window_coalesce_into_one_reload(detector, qtbot):
    d, calls = detector
    for _ in range(5):
        d._schedule_reload()
        qtbot.wait(30)  # 5 events across 150 ms — still within the 200 ms window
    # At this point the debouncer has been restarted each time; nothing fired yet.
    assert calls == []
    qtbot.wait(300)
    # Only one reload fired after the storm settled.
    assert len(calls) == 1


def test_events_separated_by_longer_than_debounce_fire_separately(detector, qtbot):
    d, calls = detector
    d._schedule_reload()
    qtbot.wait(300)
    assert len(calls) == 1
    d._schedule_reload()
    qtbot.wait(300)
    assert len(calls) == 2


def test_stop_cancels_pending_reload(detector, qtbot):
    d, calls = detector
    d._schedule_reload()
    # Before the timer fires, stop the detector.
    d.stop()
    qtbot.wait(300)
    # No reload should have fired.
    assert calls == []


def test_self_reload_suppression_drops_subsequent_filesystem_events(detector, qtbot):
    """After notify_self_reload, filesystem events within the suppression
    window do NOT fire a reload."""
    d, calls = detector
    d.notify_self_reload()
    d._schedule_reload()  # simulate a filesystem event
    qtbot.wait(400)
    assert calls == [], "suppression should have dropped the event"


def test_focus_events_bypass_self_reload_suppression(detector, qtbot):
    """Focus changes are user-driven, not consequences of our own writes,
    so suppression must NOT block them."""
    d, calls = detector
    d.notify_self_reload()
    d._schedule_reload_force()  # simulate focus event
    qtbot.wait(400)
    assert len(calls) == 1, "focus events must bypass suppression"
