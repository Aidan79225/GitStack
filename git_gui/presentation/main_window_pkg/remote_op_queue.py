# git_gui/presentation/main_window_pkg/remote_op_queue.py
from __future__ import annotations
import threading
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox


class _RemoteSignals(QObject):
    """Signal bridge — lives on main thread, emitted from background thread."""
    finished = Signal(str)
    failed = Signal(str, str)


class RemoteOpQueueMixin:
    """Remote-operation serializer and queue.

    Provides `_run_remote_op` — a single-flight serializer that runs a
    callable on a background thread and marshals completion back to the
    main thread via Qt signals. Also hosts the push/pull/fetch slots.

    Mixin — not instantiable on its own. Relies on composite-provided
    attributes set up by MainWindow's __init__.
    """

    def _wire_remote_op_signals(self) -> None:
        self._graph.push_requested.connect(self._on_push)
        self._graph.pull_requested.connect(self._on_pull)
        self._graph.fetch_all_requested.connect(self._on_fetch_all_prune)
        self._sidebar.fetch_requested.connect(self._on_fetch_single)
        self._sidebar.tag_push_requested.connect(self._on_push_tag)
        self._sidebar.branch_push_requested.connect(
            lambda b: self._run_remote_op(f"Push origin/{b}", lambda: self._commands.push.execute("origin", b)))

    def _run_remote_op(self, name: str, fn) -> None:
        if self._remote_running:
            return

        self._log_panel.expand()
        self._log_panel.log(f"{name} — started...")
        self._remote_running = True
        self.statusBar().showMessage(f"\u23f3 {name}...")

        signals = _RemoteSignals()
        signals.finished.connect(self._on_remote_done)
        signals.failed.connect(self._on_remote_error)
        self._remote_signals = signals  # prevent GC

        def _worker():
            try:
                fn()
                signals.finished.emit(name)
            except Exception as e:
                signals.failed.emit(name, str(e))

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def _on_remote_done(self, name: str) -> None:
        self._log_panel.log(f"{name} — done")
        self._remote_running = False
        self.statusBar().clearMessage()
        self._reload()

    def _on_remote_error(self, name: str, error: str) -> None:
        self._log_panel.log_error(f"{name} — ERROR: {error}")
        self._remote_running = False
        self.statusBar().clearMessage()
        self._reload()

        # Detect push rejection and offer force push
        if name.startswith("Push ") and "non-fast-forward" in error:
            branch = self._get_current_branch()
            if branch:
                reply = QMessageBox.warning(
                    self,
                    "Push Rejected",
                    f"Push was rejected because the remote branch has changes "
                    f"you don't have locally.\n\n"
                    f"Would you like to force push with --force-with-lease?\n"
                    f"This will overwrite the remote branch.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self._run_remote_op(
                        f"Force push origin/{branch}",
                        lambda: self._commands.force_push.execute("origin", branch),
                    )

    def _on_push(self) -> None:
        branch = self._get_current_branch()
        if branch:
            self._run_remote_op(
                f"Push origin/{branch}",
                lambda: self._commands.push.execute("origin", branch),
            )

    def _on_pull(self) -> None:
        branch = self._get_current_branch()
        if branch:
            self._run_remote_op(
                f"Pull origin/{branch}",
                lambda: self._commands.pull.execute("origin", branch),
            )

    def _on_fetch_all_prune(self) -> None:
        def _fn():
            self._commands.fetch_all_prune.execute()
            self._update_remote_tag_cache("origin")
        self._run_remote_op("Fetch --all --prune", _fn)

    def _on_fetch_single(self, remote: str) -> None:
        def _fn():
            self._commands.fetch.execute(remote)
            self._update_remote_tag_cache(remote)
        self._run_remote_op(f"Fetch {remote}", _fn)

    def _on_push_tag(self, name: str) -> None:
        def _fn():
            self._commands.push_tag.execute("origin", name)
            self._update_remote_tag_cache("origin")
        self._run_remote_op(f"Push tag {name}", _fn)

    def _get_current_branch(self) -> str | None:
        if self._queries is None:
            return None
        branches = self._queries.get_branches.execute()
        for b in branches:
            if b.is_head and not b.is_remote:
                return b.name
        return None

    def _update_remote_tag_cache(self, remote: str) -> None:
        if not self._remote_tag_cache or not self._repo_path or not self._queries:
            return
        try:
            remote_tags = self._queries.get_remote_tags.execute(remote)
            data = self._remote_tag_cache.load(self._repo_path)
            data[remote] = remote_tags
            self._remote_tag_cache.save(self._repo_path, data)
        except Exception:
            pass  # cache update failure is non-critical
