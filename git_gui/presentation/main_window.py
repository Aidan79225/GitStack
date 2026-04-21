# git_gui/presentation/main_window.py
from __future__ import annotations
import threading
from typing import Callable
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QMessageBox, QSplitter, QStackedWidget,
    QVBoxLayout, QWidget,
)
from git_gui.domain.entities import WORKING_TREE_OID, ResetMode
from git_gui.domain.ports import IRepoStore
from git_gui.presentation.bus import CommandBus, QueryBus
from git_gui.presentation.widgets.diff import DiffWidget
from git_gui.presentation.widgets.graph import GraphWidget
from git_gui.presentation.widgets.log_panel import LogPanel
from git_gui.presentation.dialogs.merge_dialog import MergeDialog
from git_gui.presentation.dialogs.reset_dialog import ResetDialog
from git_gui.presentation.widgets.clone_dialog import CloneDialog
from git_gui.presentation.widgets.repo_list import RepoListWidget
from git_gui.presentation.widgets.sidebar import SidebarWidget
from git_gui.presentation.widgets.working_tree import WorkingTreeWidget
from git_gui.presentation.widgets.insight_dialog import InsightDialog
from git_gui.presentation.menus.appearance import install_appearance_menu
from git_gui.presentation.menus.git_menu import install_git_menu
from git_gui.presentation.dialogs.interactive_rebase_dialog import InteractiveRebaseDialog
from git_gui.presentation.main_window_pkg.branch_flows import BranchFlowsMixin
from git_gui.presentation.main_window_pkg.cherry_pick_revert_flows import CherryPickRevertFlowsMixin
from git_gui.presentation.main_window_pkg.reload_coordinator import ReloadCoordinatorMixin
from git_gui.presentation.main_window_pkg.remote_op_queue import RemoteOpQueueMixin
from git_gui.presentation.main_window_pkg.reset_flow import ResetFlowMixin
from git_gui.presentation.main_window_pkg.right_panel import RightPanelMixin
from git_gui.presentation.main_window_pkg.stash_flows import StashFlowsMixin
from git_gui.presentation.main_window_pkg.tag_flows import TagFlowsMixin


class _RepoReadySignals(QObject):
    ready = Signal(str, object, object)   # path, QueryBus, CommandBus
    failed = Signal(str, str)             # path, error


class MainWindow(QMainWindow, ReloadCoordinatorMixin, RightPanelMixin, ResetFlowMixin, StashFlowsMixin, BranchFlowsMixin, CherryPickRevertFlowsMixin, TagFlowsMixin, RemoteOpQueueMixin):
    def __init__(self, queries: QueryBus | None, commands: CommandBus | None,
                 repo_store: IRepoStore, remote_tag_cache=None, repo_path: str | None = None, parent=None,
                 *, session_factory: Callable[[str], tuple[QueryBus, CommandBus]]) -> None:
        super().__init__(parent)
        self._queries = queries
        self._commands = commands
        self._repo_store = repo_store
        self._remote_tag_cache = remote_tag_cache
        self._repo_path = repo_path
        self._session_factory = session_factory

        self._build_chrome()
        self._build_widgets()
        self._build_layout()
        self._build_shortcuts()

        self._wire_reload_signals()
        self._wire_right_panel_signals()
        self._wire_reset_flow_signals()
        self._wire_stash_flow_signals()
        self._wire_branch_flow_signals()
        self._wire_cherry_pick_revert_flow_signals()
        self._wire_tag_flow_signals()
        self._wire_remote_op_signals()

        # Wire cross-widget signals
        self._working_tree.merge_abort_requested.connect(self._on_merge_abort)
        self._working_tree.rebase_abort_requested.connect(self._on_rebase_abort)
        self._working_tree.merge_continue_requested.connect(self._on_merge_continue)
        self._working_tree.rebase_continue_requested.connect(self._on_rebase_continue)
        self._working_tree.commit_completed.connect(
            lambda msg: self._log_panel.log(f'Commit: "{msg}"')
        )
        self._working_tree.commit_failed.connect(
            lambda reason: (self._log_panel.expand(), self._log_panel.log_error(reason))
        )
        self._diff.merge_abort_requested.connect(self._on_merge_abort)
        self._diff.rebase_abort_requested.connect(self._on_rebase_abort)
        self._diff.rebase_continue_requested.connect(
            lambda: self._on_rebase_continue("")
        )
        self._sidebar.branch_clicked.connect(self._graph.reload_with_extra_tip)
        self._sidebar.branch_merge_requested.connect(self._on_merge)
        self._sidebar.branch_rebase_requested.connect(self._on_rebase)

        # Graph context menu signals
        self._graph.merge_branch_requested.connect(self._on_merge)
        self._graph.merge_commit_requested.connect(self._on_merge_commit)
        self._graph.rebase_onto_branch_requested.connect(self._on_rebase)
        self._graph.rebase_onto_commit_requested.connect(self._on_rebase_onto_commit)
        self._graph.interactive_rebase_branch_requested.connect(self._on_interactive_rebase_branch)
        self._graph.interactive_rebase_commit_requested.connect(self._on_interactive_rebase_commit)

        # Sidebar tag signals
        self._sidebar.tag_clicked.connect(self._graph.reload_with_extra_tip)

        # Repo list signals
        self._repo_list.repo_switch_requested.connect(self._switch_repo)
        self._repo_list.repo_open_requested.connect(self._on_repo_open)
        self._repo_list.repo_close_requested.connect(self._on_repo_close)
        self._repo_list.repo_remove_recent_requested.connect(self._on_repo_remove_recent)

        if self._queries is not None:
            self._reload()
        self._repo_list.reload()

    def _build_chrome(self) -> None:
        self.setWindowTitle(f"GitCrisp — {self._repo_path}" if self._repo_path else "GitCrisp")
        self.resize(1400, 800)
        self.menuBar().setStyleSheet(
            "QMenu { padding: 6px; }"
            "QMenu::item { padding: 6px 24px 6px 20px; }"
        )
        install_appearance_menu(self)

    def _build_widgets(self) -> None:
        self._repo_ready_signals = _RepoReadySignals()
        self._repo_ready_signals.ready.connect(self._on_repo_ready)
        self._repo_ready_signals.failed.connect(self._on_repo_failed)
        self._sidebar = SidebarWidget(self._queries, self._commands, self._remote_tag_cache, self._repo_path)
        self._graph = GraphWidget(self._queries, self._commands)
        self._diff = DiffWidget(self._queries, self._commands)
        self._working_tree = WorkingTreeWidget(self._queries, self._commands, repo_path=self._repo_path)
        self._repo_list = RepoListWidget(self._repo_store)
        self._log_panel = LogPanel()
        self._remote_running = False
        self._selected_oid: str | None = None

        self._right_stack = QStackedWidget()
        self._right_stack.addWidget(self._diff)           # index 0: commit mode
        self._right_stack.addWidget(self._working_tree)    # index 1: working tree

    def _build_layout(self) -> None:
        # Vertical splitter for sidebar: branches on top, repos on bottom
        sidebar_splitter = QSplitter(Qt.Vertical)
        sidebar_splitter.addWidget(self._sidebar)
        sidebar_splitter.addWidget(self._repo_list)
        sidebar_splitter.setSizes([400, 400])

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(sidebar_splitter)
        splitter.addWidget(self._graph)
        splitter.addWidget(self._right_stack)
        splitter.setSizes([220, 230, 950])
        # Lock the handle between graph and right_stack so it can't be dragged
        # Handle index 2 is between widget 1 (graph) and widget 2 (right_stack)
        handle = splitter.handle(2)
        if handle:
            handle.setEnabled(False)
            handle.setCursor(Qt.ArrowCursor)

        # Main layout: splitter on top, log panel at bottom
        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(splitter, 1)
        central_layout.addWidget(self._log_panel, 0)

        self.setCentralWidget(central)

    def _build_shortcuts(self) -> None:
        # F5 reload shortcut (global)
        self._reload_shortcut = QShortcut(QKeySequence(Qt.Key_F5), self)
        self._reload_shortcut.activated.connect(self._reload)

        # Ctrl+F — search commits
        self._search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._search_shortcut.activated.connect(self._graph.open_search)

        # Ctrl+W — close current repo (switch to previous open repo)
        self._close_repo_shortcut = QShortcut(QKeySequence("Ctrl+W"), self)
        self._close_repo_shortcut.activated.connect(self._close_current_repo)

        # Ctrl+1..9 — switch to Nth open repo
        self._repo_shortcuts: list[QShortcut] = []
        for i in range(1, 10):
            sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            sc.activated.connect(lambda idx=i: self._switch_to_repo_index(idx))
            self._repo_shortcuts.append(sc)

        install_git_menu(
            self,
            queries=self._queries,
            commands=self._commands,
            repo_workdir=self._repo_path,
            on_open_submodule=self._on_submodule_open_requested,
        )

    def _on_merge(self, branch: str) -> None:
        try:
            all_branches = self._queries.get_branches.execute()
            target = None
            for b in all_branches:
                if b.name == branch:
                    target = b
                    break
            if not target:
                self._log_panel.log_error(f"Branch not found: {branch}")
                return
            analysis = self._queries.get_merge_analysis.execute(target.target_oid)
            head_branch = self._queries.get_repo_state.execute().head_branch or "HEAD"
            default_msg = f"Merge branch '{branch}'"

            if analysis.is_up_to_date:
                self._log_panel.log(f"Merge {branch}: already up to date")
                return

            dlg = MergeDialog(branch, head_branch, analysis.can_ff, default_msg, parent=self)
            if dlg.exec() != MergeDialog.Accepted:
                return
            req = dlg.result_value()
            self._commands.merge.execute(branch, strategy=req.strategy, message=req.message)
            self._log_panel.log(f"Merge: {branch} into {head_branch}")
        except Exception as e:
            self._log_panel.expand()
            self._log_panel.log_error(f"Merge {branch} — ERROR: {e}")
        self._reload()

    def _on_rebase(self, branch: str) -> None:
        try:
            self._commands.rebase.execute(branch)
            self._log_panel.log(f"Rebase onto {branch}")
        except Exception as e:
            self._log_panel.expand()
            self._log_panel.log_error(f"Rebase onto {branch} — ERROR: {e}")
        self._reload()

    def _on_merge_commit(self, oid: str) -> None:
        try:
            analysis = self._queries.get_merge_analysis.execute(oid)
            head_branch = self._queries.get_repo_state.execute().head_branch or "HEAD"
            short_oid = oid[:7]
            default_msg = f"Merge commit {short_oid}"

            if analysis.is_up_to_date:
                self._log_panel.log(f"Merge commit {short_oid}: already up to date")
                return

            dlg = MergeDialog(f"commit {short_oid}", head_branch, analysis.can_ff, default_msg, parent=self)
            if dlg.exec() != MergeDialog.Accepted:
                return
            req = dlg.result_value()
            self._commands.merge_commit.execute(oid, strategy=req.strategy, message=req.message)
            self._log_panel.log(f"Merge: commit {short_oid} into {head_branch}")
        except Exception as e:
            self._log_panel.expand()
            self._log_panel.log_error(f"Merge commit {short_oid} — ERROR: {e}")
        self._reload()

    def _on_rebase_onto_commit(self, oid: str) -> None:
        try:
            self._commands.rebase_onto_commit.execute(oid)
            self._log_panel.log(f"Rebase onto commit {oid[:7]}")
        except Exception as e:
            self._log_panel.expand()
            self._log_panel.log_error(f"Rebase onto commit {oid[:7]} — ERROR: {e}")
        self._reload()

    def _on_interactive_rebase_branch(self, branch: str) -> None:
        try:
            all_branches = self._queries.get_branches.execute()
            target = None
            for b in all_branches:
                if b.name == branch:
                    target = b
                    break
            if not target:
                self._log_panel.log_error(f"Branch not found: {branch}")
                return
            self._open_interactive_rebase(target.target_oid, branch)
        except Exception as e:
            self._log_panel.expand()
            self._log_panel.log_error(f"Interactive rebase — ERROR: {e}")

    def _on_interactive_rebase_commit(self, oid: str) -> None:
        self._open_interactive_rebase(oid, f"commit {oid[:7]}")

    def _open_interactive_rebase(self, target_oid: str, target_label: str) -> None:
        try:
            head_oid = self._queries.get_head_oid.execute()
            if not head_oid:
                self._log_panel.log_error("No HEAD — cannot rebase")
                return
            commits = self._queries.get_commit_range.execute(head_oid, target_oid)
            if not commits:
                self._log_panel.log("No commits to rebase")
                return
            dlg = InteractiveRebaseDialog(commits, target_label, parent=self)
            if dlg.exec() != InteractiveRebaseDialog.Accepted:
                return
            entries = dlg.result_entries()
            self._run_remote_op(
                f"Interactive rebase onto {target_label}",
                lambda: self._commands.interactive_rebase.execute(target_oid, entries),
            )
        except Exception as e:
            self._log_panel.expand()
            self._log_panel.log_error(f"Interactive rebase — ERROR: {e}")

    def _on_merge_abort(self) -> None:
        try:
            self._commands.merge_abort.execute()
            self._log_panel.log("Merge aborted")
        except Exception as e:
            self._log_panel.expand()
            self._log_panel.log_error(f"Merge abort — ERROR: {e}")
        self._reload()

    def _on_rebase_abort(self) -> None:
        try:
            self._commands.rebase_abort.execute()
            self._log_panel.log("Rebase aborted")
        except Exception as e:
            self._log_panel.expand()
            self._log_panel.log_error(f"Rebase abort — ERROR: {e}")
        self._reload()

    def _on_merge_continue(self, msg: str) -> None:
        try:
            if self._queries.has_unresolved_conflicts.execute():
                self._log_panel.expand()
                self._log_panel.log_error("Resolve all conflicts and stage files first")
                return
            commit_msg = msg or self._queries.get_merge_msg.execute() or "Merge commit"
            self._commands.create_commit.execute(commit_msg)
            self._log_panel.log("Merge completed")
        except Exception as e:
            self._log_panel.expand()
            self._log_panel.log_error(f"Merge continue — ERROR: {e}")
        self._reload()

    def _on_rebase_continue(self, msg: str) -> None:
        try:
            if self._queries.has_unresolved_conflicts.execute():
                self._log_panel.expand()
                self._log_panel.log_error("Resolve all conflicts and stage files first")
                return
            self._commands.rebase_continue.execute(msg)
            self._log_panel.log("Rebase continued")
        except Exception as e:
            self._log_panel.expand()
            self._log_panel.log_error(f"Rebase continue — ERROR: {e}")
        self._reload()

    def _switch_repo(self, path: str) -> None:
        signals = self._repo_ready_signals

        def _worker():
            try:
                queries, commands = self._session_factory(path)
                signals.ready.emit(path, queries, commands)
            except Exception as e:
                signals.failed.emit(path, str(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_repo_ready(self, path: str, queries: QueryBus, commands: CommandBus) -> None:
        self._queries = queries
        self._commands = commands
        self._repo_path = path
        # set_repo_path BEFORE set_buses — set_buses immediately triggers
        # sidebar.reload() which captures _repo_path in a worker thread for the
        # remote-tag cache lookup. If we set it after, the worker reads the
        # previous repo's cache and the tag synced markers disappear.
        self._sidebar.set_repo_path(path)
        self._sidebar.set_buses(self._queries, self._commands)
        self._graph.set_buses(self._queries, self._commands)
        self._diff.set_buses(self._queries, self._commands)
        self._working_tree.set_buses(self._queries, self._commands)
        self._repo_store.set_active(path)
        self._repo_store.save()
        self._repo_list.reload()
        self.setWindowTitle(f"GitCrisp — {path}")
        # Re-install the Git menu so its actions bind to the new repo.
        bar = self.menuBar()
        for action in list(bar.actions()):
            if action.text() == "&Git":
                bar.removeAction(action)
        install_git_menu(
            self,
            queries=self._queries,
            commands=self._commands,
            repo_workdir=self._repo_path,
            on_open_submodule=self._on_submodule_open_requested,
        )
        self._right_stack.setCurrentIndex(0)

    def _on_repo_failed(self, path: str, error: str) -> None:
        self._log_panel.expand()
        self._log_panel.log_error(f"Cannot open {path}: {error}")

    def _enter_empty_state(self) -> None:
        self._queries = None
        self._commands = None
        self._sidebar.set_buses(None, None)
        self._graph.set_buses(None, None)
        self._diff.set_buses(None, None)
        self._working_tree.set_buses(None, None)
        self._repo_list.reload()
        self.setWindowTitle("GitCrisp")
        bar = self.menuBar()
        for action in list(bar.actions()):
            if action.text() == "&Git":
                bar.removeAction(action)
        install_git_menu(
            self,
            queries=None,
            commands=None,
            repo_workdir=None,
            on_open_submodule=self._on_submodule_open_requested,
        )

    def _on_repo_open(self, path: str) -> None:
        self._repo_store.add_open(path)
        self._repo_store.save()
        self._switch_repo(path)

    def _on_repo_close(self, path: str) -> None:
        self._repo_store.close_repo(path)
        self._repo_store.save()
        open_repos = self._repo_store.get_open_repos()
        if open_repos:
            self._switch_repo(open_repos[0])
        else:
            self._enter_empty_state()

    def _close_current_repo(self) -> None:
        """Ctrl+W: close the active repo and switch to the previous open one."""
        if not self._repo_path:
            return
        self._on_repo_close(self._repo_path)

    def _switch_to_repo_index(self, index: int) -> None:
        """Ctrl+1..9: switch to the Nth open repo (1-based)."""
        open_repos = self._repo_store.get_open_repos()
        i = index - 1  # 0-based
        if i < 0 or i >= len(open_repos):
            return
        path = open_repos[i]
        if path == self._repo_path:
            return  # already active
        self._switch_repo(path)

    def _on_repo_remove_recent(self, path: str) -> None:
        self._repo_store.remove_recent(path)
        self._repo_store.save()
        self._repo_list.reload()

