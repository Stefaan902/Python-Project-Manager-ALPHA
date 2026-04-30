"""
test_activity_number_wbs.py
─────────────────────────────────────────────────────────────────────────────
Tests for ActivityTableModel.recalculate_activity_numbers() and
                             .recalculate_wbs_ids()

These methods are called after every structural change (add row, remove row,
indent, outdent) and after load_project_from_json().  The tests exercise the
methods directly — no main window or file I/O is needed.

Post-patch column layout (13 columns):
  [0]  UUID
  [1]  Activity No   ← computed by recalculate_activity_numbers()
  [2]  WBS ID        ← computed by recalculate_wbs_ids()
  [3]  Name
  [4]  Predecessor
  [5]  Start Date
  [6]  End Date
  [7]  Duration
  [8]  Successors
  [9]  ES
  [10] EF
  [11] LS
  [12] LF
─────────────────────────────────────────────────────────────────────────────
"""

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_row(uid, name=""):
    """Return a blank 13-column activity row for the patched model."""
    return [uid, "", "", name, "", "", "", "", "", "", "", "", ""]


def _load(model, rows, parent_child_map=None, indentation_levels=None):
    """
    Inject rows directly into the model, bypassing Qt signals.
    parent_child_map  — dict {parent_row: [child_row, …]}  (default: no hierarchy)
    indentation_levels — list of ints, one per row            (default: all 0)
    """
    n = len(rows)
    model.beginResetModel()
    model._data = rows
    model.parent_child_map   = dict(parent_child_map)   if parent_child_map   else {}
    model.indentation_levels = list(indentation_levels) if indentation_levels else [0] * n
    model.expanded_states    = [True] * n
    model.endResetModel()


def _act_no(model, row):
    """Return Activity No for a row (column 1) as a string."""
    return str(model._data[row][1])


def _wbs(model, row):
    """Return WBS ID for a row (column 2) as a string."""
    return str(model._data[row][2])


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def model(app):
    from maincode import ActivityTableModel
    return ActivityTableModel()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Activity Number — flat list (no hierarchy)
# ─────────────────────────────────────────────────────────────────────────────

class TestActivityNumberFlat:
    """Sequential 1-based numbering for a flat activity list."""

    def test_single_row_gets_number_1(self, model):
        _load(model, [_make_row("A", "Task A")])
        model.recalculate_activity_numbers()
        assert _act_no(model, 0) == "1"

    def test_three_rows_numbered_sequentially(self, model):
        _load(model, [_make_row("A"), _make_row("B"), _make_row("C")])
        model.recalculate_activity_numbers()
        assert _act_no(model, 0) == "1"
        assert _act_no(model, 1) == "2"
        assert _act_no(model, 2) == "3"

    def test_numbers_match_display_order(self, model):
        """Activity No must equal row_index + 1 for every row in a flat list."""
        rows = [_make_row(str(i)) for i in range(10)]
        _load(model, rows)
        model.recalculate_activity_numbers()
        for i in range(10):
            assert _act_no(model, i) == str(i + 1)

    def test_empty_model_does_not_crash(self, model):
        _load(model, [])
        model.recalculate_activity_numbers()   # must not raise
        assert model.rowCount() == 0

    def test_single_row_after_delete_renumbers(self, model):
        """
        Simulate: start with 3 rows, remove the middle one,
        recalculate — remaining rows get 1, 2.
        """
        rows = [_make_row("A"), _make_row("B"), _make_row("C")]
        _load(model, rows)
        # Remove row 1 directly (simulating removeRows)
        del model._data[1]
        del model.indentation_levels[1]
        model.recalculate_activity_numbers()
        assert _act_no(model, 0) == "1"
        assert _act_no(model, 1) == "2"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Activity Number — does not change with hierarchy
# ─────────────────────────────────────────────────────────────────────────────

class TestActivityNumberWithHierarchy:
    """
    Activity numbers are purely positional — they ignore indentation level
    and parent-child relationships.  A child row still gets the next number.
    """

    def test_parent_child_rows_numbered_sequentially(self, model):
        """
        Row 0 (parent), row 1 (child of 0), row 2 (child of 0).
        Expected numbers: 1, 2, 3.
        """
        rows = [_make_row("P"), _make_row("C1"), _make_row("C2")]
        _load(model, rows,
              parent_child_map={0: [1, 2]},
              indentation_levels=[0, 1, 1])
        model.recalculate_activity_numbers()
        assert _act_no(model, 0) == "1"
        assert _act_no(model, 1) == "2"
        assert _act_no(model, 2) == "3"

    def test_nested_hierarchy_still_sequential(self, model):
        """
        Row 0 (top), row 1 (child of 0), row 2 (grandchild of 1), row 3 (top).
        Expected numbers: 1, 2, 3, 4.
        """
        rows = [_make_row("A"), _make_row("B"), _make_row("C"), _make_row("D")]
        _load(model, rows,
              parent_child_map={0: [1], 1: [2]},
              indentation_levels=[0, 1, 2, 0])
        model.recalculate_activity_numbers()
        assert _act_no(model, 0) == "1"
        assert _act_no(model, 1) == "2"
        assert _act_no(model, 2) == "3"
        assert _act_no(model, 3) == "4"


# ─────────────────────────────────────────────────────────────────────────────
# 3. WBS ID — flat list (no hierarchy)
# ─────────────────────────────────────────────────────────────────────────────

class TestWbsIdFlat:
    """
    With no parent-child relationships every row is top-level.
    WBS ID must equal the Activity Number.
    """

    def test_single_top_level_row(self, model):
        _load(model, [_make_row("A", "Task A")])
        model.recalculate_activity_numbers()
        assert _wbs(model, 0) == "1"

    def test_three_top_level_rows(self, model):
        _load(model, [_make_row("A"), _make_row("B"), _make_row("C")])
        model.recalculate_activity_numbers()
        assert _wbs(model, 0) == "1"
        assert _wbs(model, 1) == "2"
        assert _wbs(model, 2) == "3"

    def test_wbs_top_levels_increment_all(self, model):
        """WBS ID is incremented for every new top-level row."""
        rows = [_make_row(str(i)) for i in range(6)]
        _load(model, rows)
        model.recalculate_activity_numbers()
        for i in range(6):
            assert _wbs(model, i) == _act_no(model, i)

    def test_wbs_top_levels_increment_all(self, model):
        """
        Row 0 (top), row 1 (child of 0), row 2 (grandchild of 1), row 3 (top).
        Expected numbers: 1, 1.1, 1.1.1, 2.
        """
        rows = [_make_row("A"), _make_row("B"), _make_row("C"), _make_row("D")]
        _load(model, rows,
              parent_child_map={0: [1], 1: [2]},
              indentation_levels=[0, 1, 2, 0])
        model.recalculate_activity_numbers()
        assert _wbs(model, 0) == "1"
        assert _wbs(model, 1) == "1.1"
        assert _wbs(model, 2) == "1.1.1"
        assert _wbs(model, 3) == "2"



# ─────────────────────────────────────────────────────────────────────────────
# 4. WBS ID — one level of children
# ─────────────────────────────────────────────────────────────────────────────

class TestWbsIdOneLevel:
    """
    Classic single-level parent / children structure.

    Row 0: top-level (WBS "1")
    Row 1: child of row 0, first child  (WBS "1.1")
    Row 2: child of row 0, second child (WBS "1.2")
    Row 3: top-level (WBS "2")   ← second top-level counter
    """

    @pytest.fixture(autouse=True)
    def setup(self, model):
        rows = [_make_row("P1"), _make_row("C1"),
                _make_row("C2"), _make_row("P2")]
        _load(model, rows,
              parent_child_map={0: [1, 2]},
              indentation_levels=[0, 1, 1, 0])
        model.recalculate_activity_numbers()
        self.m = model

    def test_parent_wbs(self):
        assert _wbs(self.m, 0) == "1"

    def test_first_child_wbs(self):
        assert _wbs(self.m, 1) == "1.1"

    def test_second_child_wbs(self):
        assert _wbs(self.m, 2) == "1.2"

    def test_second_top_level_wbs(self):
        assert _wbs(self.m, 3) == "2"   # second top-level: wbs id is "2"… wait
        # Actually: row 3 has Activity Nb "4" (sequential), but top-level counter
        # is 2 because there are 2 top-level rows (rows 0 and 3).
        assert _wbs(self.m, 3) != _act_no(self.m, 3)


class TestWbsIdOneLevelExplicit:
    """
    Two top-level parents, each with two children.
    Verify dotted notation and sibling counter reset between parents.

    Layout:
      row 0: top-level parent A  → WBS "1"
      row 1: child 1 of A        → WBS "1.1"
      row 2: child 2 of A        → WBS "1.2"
      row 3: top-level parent B  → WBS "2"  (Activity No = 4)
      row 4: child 1 of B        → WBS "2.1"
      row 5: child 2 of B        → WBS "2.2"
    """

    @pytest.fixture(autouse=True)
    def setup(self, model):
        rows = [_make_row("A"), _make_row("A1"), _make_row("A2"),
                _make_row("B"), _make_row("B1"), _make_row("B2")]
        _load(model, rows,
              parent_child_map={0: [1, 2], 3: [4, 5]},
              indentation_levels=[0, 1, 1, 0, 1, 1])
        model.recalculate_activity_numbers()
        self.m = model

    def test_parent_A_wbs(self):
        assert _wbs(self.m, 0) == "1"

    def test_A_child1_wbs(self):
        assert _wbs(self.m, 1) == "1.1"

    def test_A_child2_wbs(self):
        assert _wbs(self.m, 2) == "1.2"

    def test_parent_B_wbs(self):
        # B is the 4th row so its Activity No is "4"
        assert _wbs(self.m, 3) == "2"

    def test_B_child1_wbs(self):
        assert _wbs(self.m, 4) == "2.1"

    def test_B_child2_wbs(self):
        assert _wbs(self.m, 5) == "2.2"

    def test_sibling_counters_reset_between_parents(self):
        """
        B's children must start at .1, not continue from A's children.
        """
        assert _wbs(self.m, 4).endswith(".1")
        assert _wbs(self.m, 5).endswith(".2")
        # Verify B's children do NOT carry A's counter
        assert not _wbs(self.m, 4).endswith(".3")


# ─────────────────────────────────────────────────────────────────────────────
# 5. WBS ID — two levels of nesting (grandchildren)
# ─────────────────────────────────────────────────────────────────────────────

class TestWbsIdTwoLevels:
    """
    Three-level deep hierarchy.

    Layout:
      row 0: top-level                → WBS "1"
      row 1: child of row 0           → WBS "1.1"
      row 2: grandchild of row 1      → WBS "1.1.1"
      row 3: second grandchild of 1   → WBS "1.1.2"
      row 4: second child of row 0    → WBS "1.2"
    """

    @pytest.fixture(autouse=True)
    def setup(self, model):
        rows = [_make_row("R"), _make_row("C1"),
                _make_row("G1"), _make_row("G2"), _make_row("C2")]
        _load(model, rows,
              parent_child_map={0: [1, 4], 1: [2, 3]},
              indentation_levels=[0, 1, 2, 2, 1])
        model.recalculate_activity_numbers()
        self.m = model

    def test_root_wbs(self):
        assert _wbs(self.m, 0) == "1"

    def test_first_child_wbs(self):
        assert _wbs(self.m, 1) == "1.1"

    def test_first_grandchild_wbs(self):
        assert _wbs(self.m, 2) == "1.1.1"

    def test_second_grandchild_wbs(self):
        assert _wbs(self.m, 3) == "1.1.2"

    def test_second_child_wbs(self):
        assert _wbs(self.m, 4) == "1.2"

    def test_depth_three_dot_count(self):
        """A grandchild WBS ID must contain exactly two dots."""
        assert _wbs(self.m, 2).count(".") == 2
        assert _wbs(self.m, 3).count(".") == 2

    def test_depth_two_dot_count(self):
        """A child WBS ID must contain exactly one dot."""
        assert _wbs(self.m, 1).count(".") == 1
        assert _wbs(self.m, 4).count(".") == 1

    def test_depth_one_no_dot(self):
        """A top-level WBS ID must contain no dots."""
        assert "." not in _wbs(self.m, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 6. WBS ID — the example from the requirements ("3.2.5")
# ─────────────────────────────────────────────────────────────────────────────

class TestWbsIdRequirementsExample:
    """
    Reproduce the exact example from the requirements:
    '3.2.5' is the 5th child of parent '3.2'.

    We need at least 3 top-level nodes, the third having at least 2 children,
    the second child of which having at least 5 grandchildren.

    Minimal layout:
      row  0: top-level 1                → "1"
      row  1: top-level 2                → "2"
      row  2: top-level 3                → "3"
      row  3: child 3.1                  → "3.1"
      row  4: child 3.2                  → "3.2"
      row  5: grandchild 3.2.1           → "3.2.1"
      row  6: grandchild 3.2.2           → "3.2.2"
      row  7: grandchild 3.2.3           → "3.2.3"
      row  8: grandchild 3.2.4           → "3.2.4"
      row  9: grandchild 3.2.5           → "3.2.5"  ← the target
    """

    @pytest.fixture(autouse=True)
    def setup(self, model):
        rows = [
            _make_row("T1"),               # row 0  top-level 1
            _make_row("T2"),               # row 1  top-level 2
            _make_row("T3"),               # row 2  top-level 3
            _make_row("C31"),              # row 3  child 3.1
            _make_row("C32"),              # row 4  child 3.2
            _make_row("G321"),             # row 5  grandchild 3.2.1
            _make_row("G322"),             # row 6  grandchild 3.2.2
            _make_row("G323"),             # row 7  grandchild 3.2.3
            _make_row("G324"),             # row 8  grandchild 3.2.4
            _make_row("G325"),             # row 9  grandchild 3.2.5
        ]
        _load(model, rows,
              parent_child_map={
                  2: [3, 4],          # T3 → C31, C32
                  4: [5, 6, 7, 8, 9], # C32 → 5 grandchildren
              },
              indentation_levels=[0, 0, 0, 1, 1, 2, 2, 2, 2, 2])
        model.recalculate_activity_numbers()
        self.m = model

    def test_target_wbs_is_3_2_5(self):
        assert _wbs(self.m, 9) == "3.2.5"

    def test_parent_3_2_wbs(self):
        assert _wbs(self.m, 4) == "3.2"

    def test_parent_3_wbs(self):
        assert _wbs(self.m, 2) == "3"

    def test_first_top_level_wbs(self):
        assert _wbs(self.m, 0) == "1"

    def test_second_top_level_wbs(self):
        assert _wbs(self.m, 1) == "2"

    def test_3_2_1_through_3_2_4(self):
        for i, expected in enumerate(["3.2.1", "3.2.2", "3.2.3", "3.2.4"], start=5):
            assert _wbs(self.m, i) == expected, \
                f"row {i}: expected {expected}, got {_wbs(self.m, i)}"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Idempotency — calling recalculate_activity_numbers() twice gives same result
# ─────────────────────────────────────────────────────────────────────────────

class TestIdempotency:

    def test_flat_idempotent(self, model):
        rows = [_make_row("A"), _make_row("B"), _make_row("C")]
        _load(model, rows)
        model.recalculate_activity_numbers()
        first = [(_act_no(model, r), _wbs(model, r)) for r in range(3)]
        model.recalculate_activity_numbers()
        second = [(_act_no(model, r), _wbs(model, r)) for r in range(3)]
        assert first == second

    def test_hierarchy_idempotent(self, model):
        rows = [_make_row("P"), _make_row("C1"), _make_row("C2")]
        _load(model, rows,
              parent_child_map={0: [1, 2]},
              indentation_levels=[0, 1, 1])
        model.recalculate_activity_numbers()
        first = [(_act_no(model, r), _wbs(model, r)) for r in range(3)]
        model.recalculate_activity_numbers()
        second = [(_act_no(model, r), _wbs(model, r)) for r in range(3)]
        assert first == second


# ─────────────────────────────────────────────────────────────────────────────
# 8. Recalculation after structural changes (simulate add / remove / indent)
# ─────────────────────────────────────────────────────────────────────────────

class TestRecalcAfterStructuralChanges:

    def test_after_append_row_numbers_update(self, model):
        """Adding a row and recalculating must extend the numbering."""
        rows = [_make_row("A"), _make_row("B")]
        _load(model, rows)
        model.recalculate_activity_numbers()
        # Simulate append
        model._data.append(_make_row("C"))
        model.indentation_levels.append(0)
        model.recalculate_activity_numbers()
        assert _act_no(model, 2) == "3"
        assert _wbs(model, 2) == "3"

    def test_after_remove_middle_row_renumbers(self, model):
        """Removing a middle row must close the gap in numbering."""
        rows = [_make_row("A"), _make_row("B"), _make_row("C")]
        _load(model, rows)
        model.recalculate_activity_numbers()
        # Simulate removal of row 1
        del model._data[1]
        del model.indentation_levels[1]
        model.recalculate_activity_numbers()
        assert _act_no(model, 0) == "1"
        assert _act_no(model, 1) == "2"   # was "C", now becomes row 1 → no. 2

    def test_after_indent_wbs_updates(self, model):
        """
        Make row 1 a child of row 0 and recalculate.
        WBS of row 1 should change from "2" to "1.1".
        """
        rows = [_make_row("A"), _make_row("B")]
        _load(model, rows)
        model.recalculate_activity_numbers()
        # Verify flat WBS before indent
        assert _wbs(model, 1) == "2"

        # Simulate indent
        model.parent_child_map = {0: [1]}
        model.indentation_levels[1] = 1
        model.recalculate_activity_numbers()
        assert _wbs(model, 1) == "1.1"

    def test_after_outdent_wbs_updates(self, model):
        """
        Remove child relationship for row 1 and recalculate.
        WBS of row 1 should change from "1.1" back to "2".
        """
        rows = [_make_row("A"), _make_row("B")]
        _load(model, rows,
              parent_child_map={0: [1]},
              indentation_levels=[0, 1])
        model.recalculate_activity_numbers()
        assert _wbs(model, 1) == "1.1"

        # Simulate outdent
        model.parent_child_map = {}
        model.indentation_levels[1] = 0
        model.recalculate_activity_numbers()
        assert _wbs(model, 1) == "2"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Integration with load_project_from_json()
#    Verify that stale Activity No / WBS ID from the file are discarded
#    and freshly computed values appear after loading.
# ─────────────────────────────────────────────────────────────────────────────

class TestRecalcAfterLoad:
    """
    Full round-trip: save a project that intentionally has wrong/stale
    Activity No and WBS ID values in the JSON, then load it and confirm
    the correct values are computed.
    """

    def _patch_dialogs(self, monkeypatch, path):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            lambda *a, **kw: (path, ""))
        monkeypatch.setattr(QFileDialog, "getOpenFileName",
                            lambda *a, **kw: (path, ""))
        monkeypatch.setattr(QMessageBox, "information",
                            lambda *a, **kw: None)

    @pytest.fixture()
    def window(self, app, qtbot):
        from maincode import ActivityTableApp
        w = ActivityTableApp()
        qtbot.addWidget(w)
        return w

    def _populate(self, window):
        """
        Three activities, flat list — no hierarchy.
        Activity No and WBS ID are intentionally left as stale garbage
        to confirm they are cleared on load and recomputed correctly.
        """
        am = window.activity_model
        am.beginResetModel()
        am._data = [
            ["ACT-1", "STALE", "STALE", "Design", "", "", "", "3", "", "", "", "", ""],
            ["ACT-2", "STALE", "STALE", "Build",  "", "", "", "5", "", "", "", "", ""],
            ["ACT-3", "STALE", "STALE", "Test",   "", "", "", "2", "", "", "", "", ""],
        ]
        am.indentation_levels = [0, 0, 0]
        am.expanded_states    = [True, True, True]
        am.parent_child_map   = {}
        am.endResetModel()

    def _populate_with_hierarchy(self, window):
        """
        Row 0: top-level parent
        Row 1: child of row 0
        Row 2: second child of row 0
        Row 3: top-level

        Expected WBS after recalc:
          row 0 → "1"
          row 1 → "1.1"
          row 2 → "1.2"
          row 3 → "2"   (Activity No 2, top-level)
        """
        am = window.activity_model
        am.beginResetModel()
        am._data = [
            ["P1", "STALE", "STALE", "Phase",   "", "", "", "0", "", "", "", "", ""],
            ["C1", "STALE", "STALE", "Dig",     "", "", "", "3", "", "", "", "", ""],
            ["C2", "STALE", "STALE", "Pour",    "", "", "", "2", "", "", "", "", ""],
            ["T1", "STALE", "STALE", "Inspect", "", "", "", "1", "", "", "", "", ""],
        ]
        am.indentation_levels = [0, 1, 1, 0]
        am.expanded_states    = [True, True, True, True]
        am.parent_child_map   = {0: [1, 2]}
        am.endResetModel()

    # ── flat list ──────────────────────────────────────────────────────────

    def test_stale_activity_no_cleared_before_load(
            self, window, tmp_path, monkeypatch):
        """The loader must clear column 1 before recalculating."""
        path = str(tmp_path / "proj.json")
        self._patch_dialogs(monkeypatch, path)
        self._populate(window)
        window.save_project_to_json()
        # Corrupt col 1 directly in the saved JSON
        import json
        with open(path) as f:
            data = json.load(f)
        for row in data["activities"]:
            row[1] = "STALE"
        with open(path, "w") as f:
            json.dump(data, f)
        # Now load — stale values must be replaced
        window.load_project_from_json()
        am = window.activity_model
        assert am._data[0][1] == "1"
        assert am._data[1][1] == "2"
        assert am._data[2][1] == "3"

    def test_activity_numbers_correct_after_load_flat(
            self, window, tmp_path, monkeypatch):
        path = str(tmp_path / "proj.json")
        self._patch_dialogs(monkeypatch, path)
        self._populate(window)
        window.save_project_to_json()
        window.load_project_from_json()
        am = window.activity_model
        assert am._data[0][1] == "1"
        assert am._data[1][1] == "2"
        assert am._data[2][1] == "3"

    def test_wbs_ids_correct_after_load_flat(
            self, window, tmp_path, monkeypatch):
        path = str(tmp_path / "proj.json")
        self._patch_dialogs(monkeypatch, path)
        self._populate(window)
        window.save_project_to_json()
        window.load_project_from_json()
        am = window.activity_model
        assert am._data[0][2] == "1"
        assert am._data[1][2] == "2"
        assert am._data[2][2] == "3"

    def test_wbs_equals_activity_no_for_flat_list_after_load(
            self, window, tmp_path, monkeypatch):
        path = str(tmp_path / "proj.json")
        self._patch_dialogs(monkeypatch, path)
        self._populate(window)
        window.save_project_to_json()
        window.load_project_from_json()
        am = window.activity_model
        for r in range(am.rowCount()):
            assert am._data[r][1] == am._data[r][2], \
                f"Row {r}: Activity No ({am._data[r][1]}) != WBS ({am._data[r][2]})"

    # ── hierarchy ──────────────────────────────────────────────────────────

    def test_activity_numbers_correct_after_load_hierarchy(
            self, window, tmp_path, monkeypatch):
        path = str(tmp_path / "proj.json")
        self._patch_dialogs(monkeypatch, path)
        self._populate_with_hierarchy(window)
        window.save_project_to_json()
        window.load_project_from_json()
        am = window.activity_model
        assert am._data[0][1] == "1"
        assert am._data[1][1] == "2"
        assert am._data[2][1] == "3"
        assert am._data[3][1] == "4"

    def test_wbs_parent_after_load(self, window, tmp_path, monkeypatch):
        path = str(tmp_path / "proj.json")
        self._patch_dialogs(monkeypatch, path)
        self._populate_with_hierarchy(window)
        window.save_project_to_json()
        window.load_project_from_json()
        assert window.activity_model._data[0][2] == "1"

    def test_wbs_first_child_after_load(self, window, tmp_path, monkeypatch):
        path = str(tmp_path / "proj.json")
        self._patch_dialogs(monkeypatch, path)
        self._populate_with_hierarchy(window)
        window.save_project_to_json()
        window.load_project_from_json()
        assert window.activity_model._data[1][2] == "1.1"

    def test_wbs_second_child_after_load(self, window, tmp_path, monkeypatch):
        path = str(tmp_path / "proj.json")
        self._patch_dialogs(monkeypatch, path)
        self._populate_with_hierarchy(window)
        window.save_project_to_json()
        window.load_project_from_json()
        assert window.activity_model._data[2][2] == "1.2"

    def test_wbs_second_top_level_after_load(
            self, window, tmp_path, monkeypatch):
        path = str(tmp_path / "proj.json")
        self._patch_dialogs(monkeypatch, path)
        self._populate_with_hierarchy(window)
        window.save_project_to_json()
        window.load_project_from_json()
        # Row 3 is the 4th row (Activity No "4"), top-level → WBS "2"
        assert window.activity_model._data[3][2] == "2"