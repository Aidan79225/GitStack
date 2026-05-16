# git_gui/presentation/main_window/branch_flows.py
from __future__ import annotations
from PySide6.QtWidgets import QInputDialog, QMessageBox


class BranchFlowsMixin:
    """Branch operations — checkout, create, delete, and commit checkout.

    Mixin — not instantiable on its own. Relies on composite-provided
    attributes set up by MainWindow's __init__.
    """

    def _wire_branch_flow_signals(self) -> None:
        self._sidebar.branch_checkout_requested.connect(self._on_branch_changed)
        self._sidebar.branch_delete_requested.connect(self._on_delete_branch)
        self._sidebar.remote_branch_delete_requested.connect(self._on_delete_remote_branch)
        self._graph.remote_branch_delete_requested.connect(self._on_delete_remote_branch)
        self._graph.delete_branch_requested.connect(self._on_delete_branch)
        self._graph.create_branch_requested.connect(self._on_create_branch)
        self._graph.checkout_commit_requested.connect(self._on_checkout_commit)
        self._graph.checkout_branch_requested.connect(self._on_checkout_branch)

    def _on_branch_changed(self, branch: str) -> None:
        if self._queries is None:
            return
        self._sidebar.reload()
        head_oid = self._queries.get_head_oid.execute()
        if head_oid:
            self._graph.reload_and_scroll_to(head_oid)
        else:
            self._graph.reload()

    def _on_delete_branch(self, branch: str) -> None:
        try:
            self._commands.delete_branch.execute(branch)
            self._log_panel.log(f"Deleted branch: {branch}")
        except Exception as e:
            self._log_panel.expand()
            self._log_panel.log_error(f"Delete branch {branch} — ERROR: {e}")
        self._reload()

    def _on_delete_remote_branch(self, remote: str, branch: str) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Remote Branch",
            f"Delete remote branch `{remote}/{branch}`? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._run_remote_op(
            f"Delete {remote}/{branch}",
            lambda: self._commands.delete_remote_branch.execute(remote, branch),
        )

    def _on_create_branch(self, oid: str) -> None:
        name, ok = QInputDialog.getText(self, "Create Branch", "Branch name:")
        if not ok or not name.strip():
            return
        branch_name = name.strip()
        try:
            self._commands.create_branch.execute(branch_name, oid)
            self._commands.checkout.execute(branch_name)
            self._log_panel.log(f"Created and checked out branch: {branch_name}")
        except Exception as e:
            self._log_panel.expand()
            self._log_panel.log_error(f"Create branch — ERROR: {e}")
        self._reload()

    def _on_checkout_commit(self, oid: str) -> None:
        try:
            self._commands.checkout_commit.execute(oid)
            self._log_panel.log(f"Checkout (detached HEAD): {oid[:8]}")
        except Exception as e:
            self._log_panel.expand()
            self._log_panel.log_error(f"Checkout {oid[:8]} — ERROR: {e}")
        self._reload()

    def _on_checkout_branch(self, name: str) -> None:
        try:
            all_branches = self._queries.get_branches.execute()
            local_names = {b.name for b in all_branches if not b.is_remote}

            if name in local_names:
                self._commands.checkout.execute(name)
                self._log_panel.log(f"Checkout branch: {name}")
            else:
                local_name = name.split("/", 1)[1] if "/" in name else name
                if local_name in local_names:
                    reply = QMessageBox.question(
                        self,
                        "Local branch exists",
                        f"Local branch '{local_name}' already exists.\n\n"
                        f"Reset it to '{name}' (HEAD)? This discards any local "
                        f"commits and uncommitted changes on '{local_name}'.",
                        QMessageBox.Yes | QMessageBox.Cancel,
                        QMessageBox.Cancel,
                    )
                    if reply != QMessageBox.Yes:
                        return
                    self._commands.checkout.execute(local_name)
                    self._commands.reset_branch_to_ref.execute(local_name, name)
                    self._log_panel.log(f"Reset {local_name} to {name}")
                else:
                    self._commands.checkout_remote_branch.execute(name)
                    self._log_panel.log(f"Checkout remote: {name} → local {local_name}")
        except Exception as e:
            self._log_panel.expand()
            self._log_panel.log_error(f"Checkout {name} — ERROR: {e}")
        self._reload()
