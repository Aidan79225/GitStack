import logging
import sys
import pygit2
from pathlib import Path
from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from git_gui.infrastructure.pygit2 import Pygit2Repository
from git_gui.infrastructure.repo_store import JsonRepoStore
from git_gui.infrastructure.remote_tag_cache import JsonRemoteTagCache
from git_gui.presentation.bus import CommandBus, QueryBus
from git_gui.presentation.main_window import MainWindow
from git_gui.presentation.theme import ThemeManager, set_theme_manager
from git_gui.logging_setup import setup_logging


def _is_git_repo(path: str) -> bool:
    return pygit2.discover_repository(path) is not None


def _find_valid_repo(repo_store: JsonRepoStore) -> str | None:
    """Return the first valid repo path from active or open list, pruning invalid ones."""
    active = repo_store.get_active()
    if active and Path(active).is_dir() and _is_git_repo(active):
        return active

    for path in list(repo_store.get_open_repos()):
        if Path(path).is_dir() and _is_git_repo(path):
            repo_store.set_active(path)
            return path
        repo_store.close_repo(path)

    repo_store.save()
    return None


def _open_session(path: str) -> tuple[QueryBus, CommandBus]:
    repo = Pygit2Repository(path)
    return QueryBus.from_reader(repo), CommandBus.from_writer(repo)


_SUPPRESSED_FRAGMENTS = (
    "Unable to open monitor interface",
    "cached device pixel ratio value was stale",
)


def _qt_message_filter(mode, context, message):
    """Filter out known-noisy Qt platform warnings (Windows QPA bugs)."""
    if any(fragment in message for fragment in _SUPPRESSED_FRAGMENTS):
        logging.debug("Suppressed Qt warning: %s", message)
        return
    sys.stderr.write(f"Qt {mode.name}: {message}\n")


def main() -> None:
    setup_logging()
    qInstallMessageHandler(_qt_message_filter)
    app = QApplication(sys.argv)
    app.setApplicationName("GitCrisp")

    theme_manager = ThemeManager(app)
    set_theme_manager(theme_manager)

    repo_store = JsonRepoStore()
    repo_store.load()
    remote_tag_cache = JsonRemoteTagCache()

    repo_path = _find_valid_repo(repo_store)

    if repo_path and repo_path not in repo_store.get_open_repos():
        repo_store.add_open(repo_path)
        repo_store.save()

    if repo_path:
        queries, commands = _open_session(repo_path)
    else:
        queries, commands = None, None

    window = MainWindow(
        queries, commands, repo_store, remote_tag_cache, repo_path,
        session_factory=_open_session,
    )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
