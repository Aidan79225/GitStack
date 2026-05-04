# File List Row Cap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cap the unified-scroll's vertical file list at 5 rows tall (with internal vertical scrollbar for overflow); show natural height for ≤ 5 files.

**Architecture:** Pure encapsulation inside `FileListView` (a `QListView` subclass at `git_gui/presentation/widgets/file_list_view.py`). Add a `sizeHint`/`minimumSizeHint` override that returns `min(rowCount, 5) * row_height + 2 * frameWidth` and a `setModel` override that wires `modelReset`/`rowsInserted`/`rowsRemoved` to `updateGeometry()`. The existing `FileNavigatorWidget.sizeHint` delegation (commit `c01c765`) propagates the new sizing through to `_flow_slot` automatically — no changes elsewhere.

**Tech Stack:** Python, PySide6, pytest, pytest-qt, uv.

**Spec:** `docs/superpowers/specs/2026-05-05-file-list-row-cap-design.md`

---

## File Map

| Path | Action |
|------|--------|
| `git_gui/presentation/widgets/file_list_view.py` | Modify (add `MAX_VISIBLE_ROWS`, `_FALLBACK_ROW_HEIGHT`, `sizeHint`, `minimumSizeHint`, `setModel`, scrollbar policy in `__init__`) |
| `tests/presentation/widgets/test_file_list_view.py` | Create |

Untouched: domain (`entities.py`, `ports.py`), application, infrastructure, theme, `file_navigator.py`, `diff.py`, `commit_detail.py`, `working_tree.py`. The `FileNavigatorWidget.sizeHint()` delegation already forwards the new sizing through.

---

## Task 1: Row-cap sizing for `FileListView`

This is one logical change with TDD: failing tests first, minimal implementation, verify, commit.

**Files:**
- Create: `tests/presentation/widgets/test_file_list_view.py`
- Modify: `git_gui/presentation/widgets/file_list_view.py`

### 1.1 Verify baseline tests pass

- [ ] **Step 1: Run the full test suite from a clean tree**

Run: `uv run pytest tests/ --tb=no -q`

Expected: 633 tests pass (matching the post-merge state of master). Note the count.

### 1.2 Write the failing tests

- [ ] **Step 2: Create the test file**

Create `tests/presentation/widgets/test_file_list_view.py` with this content:

```python
"""Tests for FileListView's row-cap sizing.

Verifies that the QListView reports a sizeHint that grows with row count
up to MAX_VISIBLE_ROWS = 5, then caps. Also verifies the internal
vertical scrollbar correctly reflects overflow when the cap is hit.
"""
from __future__ import annotations

import pytest

from git_gui.domain.entities import FileStatus
from git_gui.presentation.models.diff_model import DiffModel
from git_gui.presentation.widgets.file_list_view import (
    FileDeltaDelegate,
    FileListView,
)


def _files(n: int) -> list[FileStatus]:
    return [
        FileStatus(path=f"file_{i}.py", status="staged", delta="modified")
        for i in range(n)
    ]


@pytest.fixture
def make_view(qtbot):
    """Factory: builds a FileListView with N files. Resizes width so the
    delegate has a known viewport for sizeHintForRow to compute against."""
    def _make(n: int):
        model = DiffModel(_files(n))
        view = FileListView()
        view.setItemDelegate(FileDeltaDelegate(view))
        view.setModel(model)
        qtbot.addWidget(view)
        view.resize(200, 500)
        view.show()
        qtbot.wait(1)  # Let Qt compute sizeHintForRow once visible
        return view, model
    return _make


def _row_h(view: FileListView) -> int:
    """Look up row height from the live view (depends on font + delegate)."""
    h = view.sizeHintForRow(0)
    if h <= 0:
        h = FileListView._FALLBACK_ROW_HEIGHT
    return h


def test_sizeHint_height_for_three_rows_is_three_row_heights(make_view):
    view, _ = make_view(3)
    expected = 3 * _row_h(view) + 2 * view.frameWidth()
    assert view.sizeHint().height() == expected


def test_sizeHint_height_caps_at_five_rows_for_ten_files(make_view):
    view, _ = make_view(10)
    expected = 5 * _row_h(view) + 2 * view.frameWidth()
    assert view.sizeHint().height() == expected


def test_sizeHint_height_for_empty_model_collapses(make_view):
    view, _ = make_view(0)
    # Zero rows × any row_h is zero; only the frame border remains.
    assert view.sizeHint().height() == 2 * view.frameWidth()


def test_sizeHint_updates_after_model_reload(make_view, qtbot):
    view, model = make_view(3)
    row_h = _row_h(view)
    assert view.sizeHint().height() == 3 * row_h + 2 * view.frameWidth()

    model.reload(_files(10))
    qtbot.wait(1)
    assert view.sizeHint().height() == 5 * row_h + 2 * view.frameWidth()

    model.reload(_files(2))
    qtbot.wait(1)
    assert view.sizeHint().height() == 2 * row_h + 2 * view.frameWidth()


def test_internal_vertical_scrollbar_has_range_when_over_five_rows(make_view, qtbot):
    view, _ = make_view(10)
    row_h = _row_h(view)
    # Resize view to exactly the cap so the 10-row content overflows.
    view.resize(view.width(), 5 * row_h + 2 * view.frameWidth())
    qtbot.wait(1)
    assert view.verticalScrollBar().maximum() > 0


def test_internal_vertical_scrollbar_has_no_range_when_five_or_fewer_rows(
    make_view, qtbot
):
    view, _ = make_view(5)
    row_h = _row_h(view)
    view.resize(view.width(), 5 * row_h + 2 * view.frameWidth())
    qtbot.wait(1)
    assert view.verticalScrollBar().maximum() == 0
```

- [ ] **Step 3: Run the tests — expect failure**

Run: `uv run pytest tests/presentation/widgets/test_file_list_view.py -v`

Expected: tests fail. The first failure mode will be `AttributeError: type object 'FileListView' has no attribute '_FALLBACK_ROW_HEIGHT'` (raised in the `_row_h` helper). Even before that, every assertion against `view.sizeHint().height()` will fail because `QListView`'s default `sizeHint` returns 256×192 regardless of row count.

### 1.3 Implement the override

- [ ] **Step 4: Update `FileListView` in `file_list_view.py`**

Open `git_gui/presentation/widgets/file_list_view.py`. The current top-level imports include `QModelIndex, QRect, QSize, Qt, Signal` from QtCore. Verify `QSize` is imported (it should be — added in the FileDeltaDelegate move). Verify the existing `FileListView` class starts at around line 9 with `class FileListView(QListView):`.

Modify the class to add the new constants, scrollbar policy in `__init__`, and the three new overrides. Find:

```python
class FileListView(QListView):
    """QListView with two custom click behaviors:

    1. Clicking the checkbox indicator toggles the check state WITHOUT changing
       the row selection (so the blue highlight on another row is preserved).
    2. Clicking an already-selected row deselects it and emits ``deselected``,
       without delegating to ``super()`` so Qt cannot re-select.
    """

    deselected = Signal()

    def _checkbox_rect(self, index):
```

Replace with:

```python
class FileListView(QListView):
    """QListView with two custom click behaviors:

    1. Clicking the checkbox indicator toggles the check state WITHOUT changing
       the row selection (so the blue highlight on another row is preserved).
    2. Clicking an already-selected row deselects it and emits ``deselected``,
       without delegating to ``super()`` so Qt cannot re-select.

    Also caps the reported sizeHint at MAX_VISIBLE_ROWS rows tall so the
    unified commit-detail scroll doesn't get a runaway-tall file list on big
    commits. Past the cap, the view's internal vertical scrollbar takes over.
    """

    deselected = Signal()

    MAX_VISIBLE_ROWS = 5
    _FALLBACK_ROW_HEIGHT = 28  # Matches FileDeltaDelegate.sizeHint (BADGE_SIZE + 8).

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._connected_model = None

    # ── Sizing ──────────────────────────────────────────────────────────────

    def sizeHint(self) -> QSize:
        base = super().sizeHint()
        m = self.model()
        if m is None:
            return QSize(base.width(), 2 * self.frameWidth())
        rows = m.rowCount()
        visible = min(rows, self.MAX_VISIBLE_ROWS)
        if rows == 0:
            return QSize(base.width(), 2 * self.frameWidth())
        row_h = self.sizeHintForRow(0)
        if row_h <= 0:
            row_h = self._FALLBACK_ROW_HEIGHT
        return QSize(base.width(), visible * row_h + 2 * self.frameWidth())

    def minimumSizeHint(self) -> QSize:
        base = super().minimumSizeHint()
        m = self.model()
        if m is None or m.rowCount() == 0:
            return QSize(base.width(), 2 * self.frameWidth())
        row_h = self.sizeHintForRow(0)
        if row_h <= 0:
            row_h = self._FALLBACK_ROW_HEIGHT
        # Allow the layout to shrink the list down to one row's worth in
        # tight situations, without it collapsing entirely.
        return QSize(base.width(), row_h + 2 * self.frameWidth())

    def setModel(self, model) -> None:
        # Disconnect the previous model's row-count signals, if any.
        if self._connected_model is not None:
            try:
                self._connected_model.modelReset.disconnect(self.updateGeometry)
                self._connected_model.rowsInserted.disconnect(self.updateGeometry)
                self._connected_model.rowsRemoved.disconnect(self.updateGeometry)
            except (TypeError, RuntimeError):
                # Signal wasn't connected (e.g., model was deleted) — ignore.
                pass

        super().setModel(model)
        self._connected_model = model

        if model is not None:
            # Any row-count change should re-trigger the parent layout to
            # re-read sizeHint(). updateGeometry() takes no args; PySide6
            # discards the extra args from rowsInserted/rowsRemoved.
            model.modelReset.connect(self.updateGeometry)
            model.rowsInserted.connect(self.updateGeometry)
            model.rowsRemoved.connect(self.updateGeometry)

    # ── Existing custom click behaviour (unchanged below) ──────────────────

    def _checkbox_rect(self, index):
```

Notes for the implementer:
- `Qt` and `QSize` are already imported at the top of the file from prior commits — no import changes needed.
- The `__init__` constructor is new (`FileListView` previously had no explicit `__init__`). Adding one is necessary to set the scrollbar policy and initialise `_connected_model`. The default constructor parent argument follows Qt's convention.
- `sizeHint` and `minimumSizeHint` go ABOVE `_checkbox_rect` (the existing first method). Don't reorder the existing methods.
- `setModel` goes between the new sizing methods and the existing `_checkbox_rect` for proximity to the related state (`_connected_model`).

- [ ] **Step 5: Run the new tests**

Run: `uv run pytest tests/presentation/widgets/test_file_list_view.py -v`

Expected: all 6 tests pass.

### 1.4 Verify nothing else regressed

- [ ] **Step 6: Run the full test suite**

Run: `uv run pytest tests/ --tb=no -q`

Expected: 639 tests pass (633 prior + 6 new). No regressions in `test_file_navigator.py` (15 tests) or `test_diff_widget.py` (16 tests) — both depend on `FileListView` indirectly via `FileNavigatorWidget`.

If any existing test fails, surface it. Most likely failure mode would be a test that previously called `view.setModel(model)` and then immediately checked `view.sizeHint()` on the assumption it returned 256×192. Search for such tests:

Run: `rtk grep -n "FileListView" tests/`

Verify each match doesn't depend on the old default sizeHint behaviour. If one does, update it to either explicitly set a model with N rows and assert against the new formula, or to read sizeHint dynamically.

- [ ] **Step 7: Sanity-import**

Run: `uv run python -c "from git_gui.presentation.widgets.file_list_view import FileListView; v = FileListView(); print('ok', v.MAX_VISIBLE_ROWS)"`

Expected: prints `ok 5`. (Note: this runs without a QApplication, which Qt typically tolerates for `__init__` of a QWidget but not for show/paint operations. If it fails with a Qt application error, replace with: `uv run python -c "from PySide6.QtWidgets import QApplication; from git_gui.presentation.widgets.file_list_view import FileListView; app = QApplication([]); v = FileListView(); print('ok', v.MAX_VISIBLE_ROWS)"`)

### 1.5 Manual smoke check

- [ ] **Step 8: Launch the app and verify visually**

Run: `uv run python main.py`

Open a repository and click:

1. **A commit with 3-5 files.** The vertical file list should be tall enough to show all files at scroll = 0 (one row per file). No internal scrollbar visible.
2. **A commit with 10+ files.** The vertical file list should be exactly 5 rows tall with an internal vertical scrollbar on its right edge. Scrolling the internal bar reveals files 6–N. Scrolling the unified panel scrolls past the (5-row) list to the diff section.
3. **An empty merge commit** (if available). The list should be effectively absent (zero height); the diff section starts immediately below the message. (If no empty merge commit is available in the test repo, skip this step.)

If the rendered behaviour differs (e.g., list still ~2 rows on a 5-file commit), check that `_FileNavigatorWidget`'s parent layout isn't accidentally constraining the height — the `FileNavigatorWidget.sizeHint()` delegation should be forwarding `_list_view.sizeHint()` which now reflects the row count.

### 1.6 Commit

- [ ] **Step 9: Stage and commit**

```bash
rtk git add git_gui/presentation/widgets/file_list_view.py tests/presentation/widgets/test_file_list_view.py
rtk git commit -m "$(cat <<'EOF'
feat(file_list_view): cap visible rows at 5 with internal scroll

QListView's default sizeHint (256x192) doesn't track row count, so the
unified commit-detail scroll's vertical file list ended up ~2 rows of
visible content regardless of how many files the commit had. Override
sizeHint / minimumSizeHint to return min(rowCount, 5) * row_height +
2 * frameWidth, and override setModel to wire the model's row-count
signals to updateGeometry() so the layout re-asks when the user
switches commits.

For commits with 6+ files, the list caps at 5 rows tall and uses
QListView's internal vertical scrollbar (ScrollBarAsNeeded) to reach
files 6 through N. The hybrid is a deliberate UX trade-off picked in
the 2026-05-05 spec brainstorm: most commits fall within the cap, and
the natural-height case stays free of nesting.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit succeeds.

---

## Self-Review Notes

- **Spec coverage:** every section/requirement in the spec maps to a step:
  - `MAX_VISIBLE_ROWS = 5` → Step 4.
  - `_FALLBACK_ROW_HEIGHT = 28` → Step 4.
  - `sizeHint()` override → Step 4 (and tests 1, 2, 3, 4 in Step 2).
  - `minimumSizeHint()` override → Step 4.
  - `setModel()` override with signal disconnect/connect → Step 4 (and test 4 in Step 2).
  - `setVerticalScrollBarPolicy(ScrollBarAsNeeded)` in `__init__` → Step 4 (and tests 5, 6 in Step 2).
  - 6 test cases from the spec's testing section → Step 2 (all six present).
  - Edge cases (0 files, 1 file, exactly 5, 6+, switching commits) → covered by tests 1, 3, and 4.
- **Placeholder scan:** every step has concrete code or commands. No "TODO", "TBD", or "implement appropriately".
- **Type/symbol consistency:** `MAX_VISIBLE_ROWS` (constant), `_FALLBACK_ROW_HEIGHT` (constant), `_connected_model` (instance attr), `sizeHint`, `minimumSizeHint`, `setModel`, `frameWidth`, `sizeHintForRow`, `updateGeometry`, `modelReset`, `rowsInserted`, `rowsRemoved` — all spelled identically across the plan and the spec.
- **No cross-file dependency drift:** `FileNavigatorWidget.sizeHint()` (in `file_navigator.py` after commit `c01c765`) already does `return self._stack.currentWidget().sizeHint()`, which is the integration point. We're not modifying it. The new `FileListView.sizeHint` flows through this path automatically. Confirmed by tracing in spec's "Architecture" section.
