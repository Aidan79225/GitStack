"""Tests for the Qt message filter in main.py."""
from __future__ import annotations
from unittest.mock import MagicMock

import main


class TestQtMessageFilter:
    def test_suppresses_monitor_interface_warning(self):
        handler = MagicMock()
        main._default_handler = handler
        main._qt_message_filter(
            None, None,
            'qt.qpa.screen: "Unable to open monitor interface to \\\\.\\DISPLAY1:"',
        )
        handler.assert_not_called()

    def test_suppresses_cached_pixel_ratio_warning(self):
        handler = MagicMock()
        main._default_handler = handler
        main._qt_message_filter(
            None, None,
            "The cached device pixel ratio value was stale on window expose.",
        )
        handler.assert_not_called()

    def test_passes_through_normal_messages(self):
        handler = MagicMock()
        main._default_handler = handler
        main._qt_message_filter(None, None, "Some other Qt message")
        handler.assert_called_once_with(None, None, "Some other Qt message")

    def test_passes_through_when_no_default_handler(self):
        main._default_handler = None
        # Should not raise
        main._qt_message_filter(None, None, "Any message")
