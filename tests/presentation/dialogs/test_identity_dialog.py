"""Tests for IdentityDialog (inline prompt for missing git identity)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QDialogButtonBox

from git_gui.presentation.dialogs.identity_dialog import IdentityDialog


def _app():
    return QApplication.instance() or QApplication([])


def test_initial_empty_disables_ok(qtbot):
    _app()
    dlg = IdentityDialog(None, None)
    qtbot.addWidget(dlg)
    ok_btn = dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok)
    assert not ok_btn.isEnabled()


def test_filling_both_fields_enables_ok(qtbot):
    _app()
    dlg = IdentityDialog(None, None)
    qtbot.addWidget(dlg)
    ok_btn = dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok)
    dlg._name_edit.setText("Alice")
    dlg._email_edit.setText("alice@example.com")
    assert ok_btn.isEnabled()


def test_partial_initial_prefills_existing_field(qtbot):
    _app()
    dlg = IdentityDialog("Alice", None)
    qtbot.addWidget(dlg)
    assert dlg._name_edit.text() == "Alice"
    assert dlg._email_edit.text() == ""


def test_values_returns_trimmed_text_and_global_flag(qtbot):
    _app()
    dlg = IdentityDialog(None, None)
    qtbot.addWidget(dlg)
    dlg._name_edit.setText("  Alice  ")
    dlg._email_edit.setText("  alice@example.com  ")
    dlg._global_check.setChecked(True)
    name, email, global_ = dlg.values()
    assert name == "Alice"
    assert email == "alice@example.com"
    assert global_ is True


def test_global_checkbox_defaults_off(qtbot):
    _app()
    dlg = IdentityDialog(None, None)
    qtbot.addWidget(dlg)
    assert dlg._global_check.isChecked() is False
