# File List Row Cap — Design Spec

**Date:** 2026-05-05
**Author:** Aidan Wang (with Claude Opus 4.7)
**Status:** Approved for implementation planning

## Goal

Make the vertical file list inside the unified commit-detail scroll size itself
to its row count up to 5 rows; show an internal vertical scrollbar when there
are more than 5 files. Today the list is sized to `QListView`'s default
`sizeHint` (256×192) regardless of row count, which the parent layout often
shrinks to ~2 rows of visible content — making the file list feel cramped on
typical commits.

## Motivation

The unified-scroll spec (2026-05-04) decided the file list takes its
"natural height" at scroll = 0. In practice `QListView` reports a fixed
default `sizeHint` that doesn't track row count, so the parent layout doesn't
know how tall to make the widget. The user reports the list visibly capped at
~2 rows on real commits, which fights the design intent (read-as-one-page,
file list visible above the diff blocks).

UX decision (Q1 in brainstorming): **option D — hybrid.**
- ≤ 5 files: list takes natural height (one row per file).
- > 5 files: list capped at 5 rows tall with an internal vertical scrollbar.

This re-introduces a small nested scroll surface for big commits, but keeps
the common case (most commits have ≤ 5 files) free of nesting.

## Architecture

Pure presentation-layer change confined to `FileListView` (already a
`QListView` subclass at `git_gui/presentation/widgets/file_list_view.py`).
No domain, application, infrastructure, or theme changes.

`FileNavigatorWidget` already overrides `sizeHint` to delegate to its current
stacked widget (commit `c01c765`), so making `FileListView` report the right
size flows through to the navigator and to `_flow_slot` automatically — no
changes needed at the navigator or `DiffWidget` level.

## Components

### `FileListView` — modified

Public surface (no new public API):
- New class constant `MAX_VISIBLE_ROWS = 5`.
- New constant `_FALLBACK_ROW_HEIGHT = 28` (matches `FileDeltaDelegate.sizeHint`'s
  `BADGE_SIZE + 8` for an empty model where `sizeHintForRow(0) == -1`).

New overrides:
- `sizeHint()` — returns `QSize(super().sizeHint().width(), height)` where
  `height = min(rowCount, MAX_VISIBLE_ROWS) * row_height + 2 * frameWidth()`.
  For `rowCount == 0`, height collapses to just the frame border
  (~2 px on default Qt styles, 0 px if `NoFrame` is set).
- `minimumSizeHint()` — returns `QSize(super().minimumSizeHint().width(),
  min(rowCount, 1) * row_height + 2 * frameWidth())`. (Lets the layout
  shrink the list to one row's worth in tight situations without it
  collapsing to nothing.)
- `setModel(model)` — overridden to (a) call super, (b) connect the new
  model's `modelReset`, `rowsInserted`, `rowsRemoved` signals to
  `self.updateGeometry()`. Disconnect the previous model's signals first
  if there was one. This makes the parent layout re-read `sizeHint()`
  whenever the row count changes.

Constructor change:
- `setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)` so the internal
  scrollbar appears for the > 5 files case. (Default is already
  `ScrollBarAsNeeded`, but set it explicitly for clarity since the rest
  of the family uses explicit policies.)

Behaviour invariants:
- ≤ 5 files: `sizeHint().height() == rowCount * row_height + 2 * frame_width`.
  The internal scrollbar never shows because the list fits.
- > 5 files: `sizeHint().height() == 5 * row_height + 2 * frame_width`.
  Internal scrollbar shows.
- 0 files: `sizeHint().height() == 2 * frameWidth()` (~2 px, effectively
  collapsed). The widget is still in the layout tree, so
  `_flow_slot.geometry().top()` for the sticky-pin threshold still
  resolves correctly.

## Data flow

```
DiffWidget.load_commit(oid)
  → _diff_model.reload(files)                        [unchanged]
    → DiffModel.modelReset                           [unchanged]
      → FileListView (sees modelReset on its bound model)
        → updateGeometry()                           [new]
          → _file_navigator.sizeHint() re-asked      [unchanged plumbing]
            → _flow_slot resizes                     [unchanged plumbing]
              → _scroll_content layout settles
              → _StickyPinController.recompute_threshold runs after
                _render_all_files (already in load_commit's success path)
```

The threshold-recompute that already runs in `load_commit` (commit
`2585571`) reads `_flow_slot.geometry().top()` after the model has been
reloaded and the diff blocks have rendered, so the new `updateGeometry()`
fires before the threshold read — the threshold reflects the new list
height correctly.

## Edge cases

- **0 files** (empty merge commit): `sizeHint().height() == 0`. The list
  widget is invisible-ish in the layout (zero height) but `_flow_slot`
  still has its zero-margin layout, so the sticky pin threshold falls
  back to `_msg_view`'s bottom edge. No special-casing needed.
- **1 file**: 1 row of natural height — same code path as ≤ 5 files.
- **Exactly 5 files**: 5 rows, no scrollbar (still fits without overflow).
- **6+ files**: capped at 5 rows, internal scrollbar visible.
- **Switching between commits with different file counts** (e.g., 2-file
  commit → 50-file commit): `setModel` connects new-model signals once;
  every subsequent `model.reload()` fires `modelReset` → `updateGeometry`
  → layout re-reads `sizeHint`. Works.
- **Hidden state** (no commit selected): `_set_empty_state(True)` already
  hides `_file_navigator` so the list view doesn't render. No interaction
  with this change.

## Theming

No theme changes. The internal scrollbar uses the existing global QSS
applied at the application level (the same scrollbar already appears in
the diff scroll area, working tree, etc.).

## Error handling

No new error paths. `sizeHintForRow(0)` returns `-1` for an empty model;
we fall back to `_FALLBACK_ROW_HEIGHT = 28`. No exceptions are caught or
raised.

## Testing

New file: `tests/presentation/widgets/test_file_list_view.py`.

Test cases:

1. `test_sizeHint_height_for_three_rows_is_three_row_heights` — populate
   the model with 3 files, assert
   `view.sizeHint().height() == 3 * row_height + 2 * frame`.
2. `test_sizeHint_height_caps_at_five_rows_for_ten_files` — populate
   with 10 files, assert
   `view.sizeHint().height() == 5 * row_height + 2 * frame`.
3. `test_sizeHint_height_for_empty_model_collapses` — empty model, assert
   `view.sizeHint().height() == 2 * view.frameWidth()` (zero rows
   contributes zero, only the frame remains).
4. `test_sizeHint_updates_after_model_reload` — start with 3 files, assert
   3-row height; reload with 10 files, assert 5-row height; reload with
   2 files, assert 2-row height.
5. `test_internal_vertical_scrollbar_has_range_when_over_five_rows` — 10
   files at exact 5-row sizeHint, assert
   `view.verticalScrollBar().maximum() > 0` (the bar has somewhere to
   scroll). Using `maximum() > 0` instead of `isVisible()` because the
   bar can be in the layout but not yet painted in headless tests.
6. `test_internal_vertical_scrollbar_has_no_range_when_five_or_fewer_rows`
   — 5 files at exact 5-row sizeHint, assert
   `view.verticalScrollBar().maximum() == 0`.

`row_height` in tests: read via `view.sizeHintForRow(0)` after a model
with at least one row is set. For test 3 (empty model), `_FALLBACK_ROW_HEIGHT`
is irrelevant because the formula returns 0 regardless.

`frame` (frame width) in tests: `view.frameWidth()` — typically 1 px on
desktop styles, may be 0 with `setFrameShape(NoFrame)`.

## Files changed

| Path | Action |
|---|---|
| `git_gui/presentation/widgets/file_list_view.py` | Modify (add constants, sizeHint/minimumSizeHint overrides, setModel override, scrollbar policy) |
| `tests/presentation/widgets/test_file_list_view.py` | Create |

Untouched: domain, application, infrastructure, theme, `file_navigator.py`,
`diff.py`, `commit_detail.py`, `working_tree.py`. The
`FileNavigatorWidget.sizeHint()` delegation added in commit `c01c765`
already forwards the new sizing through to `_flow_slot`.

## Out of scope

- Making `MAX_VISIBLE_ROWS` configurable. The 5 was a deliberate choice in
  brainstorming. If a different cap is wanted later, it's a one-line
  change.
- Changing the working-tree panel to use the same cap. The working-tree
  view has its own staging UX with checkboxes and may benefit from a
  different sizing strategy. Out of scope.
- Persisting the list's internal scroll position across commits. Probably
  not desired anyway (each commit's file list is its own thing).
