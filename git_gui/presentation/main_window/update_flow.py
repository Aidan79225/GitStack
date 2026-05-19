# git_gui/presentation/main_window/update_flow.py
from __future__ import annotations


class UpdateFlowMixin:
    """Background update-check wiring.

    Mixin -- not instantiable on its own. Relies on composite-provided
    attributes (``_log_panel``) set up by ``MainWindow.__init__``.
    """

    def _start_update_check(self) -> None:
        """Kick off the GitHub release check if the user hasn't opted out.

        Skipped for dev builds (no baked version) so local ``uv run`` runs
        don't surface phantom updates against the running checkout.
        """
        from git_gui.observability import _get_version
        from git_gui.presentation.app_settings import get_check_updates
        from git_gui.presentation.services.update_checker import UpdateChecker

        if not get_check_updates():
            return
        current = _get_version()
        if current == "unknown":
            return
        self._update_checker = UpdateChecker(current_version=current, parent=self)  # type: ignore[arg-type]
        self._update_checker.update_available.connect(self._on_update_available)
        self._update_checker.check()

    def _on_update_available(self, version: str, url: str) -> None:
        self._log_panel.log_link(f"New version available: {version} — Download", url)  # type: ignore[attr-defined]
