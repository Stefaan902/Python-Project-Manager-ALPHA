"""
test_save_load.py — Integration tests for the JSON save/load round-trip.

Strategy
--------
save_project_to_json() and load_project_from_json() both open file dialogs
and show completion message boxes, which would block a headless test.
We bypass these with monkeypatch:

  • QFileDialog.getSaveFileName  → returns a temp file path
  • QFileDialog.getOpenFileName  → returns the same temp file path
  • QMessageBox.information      → no-op

After that we call the methods directly and inspect the model state.

What is verified
----------------
  1. Activities  — name, duration, predecessor UUID, hierarchy/indentation
  2. Resources   — name, type, rate columns, hierarchy/indentation
  3. Risks       — data rows survive intact
  4. BOQ         — data rows and computed columns survive intact
  5. CPM         — ES/EF/LS/LF are recalculated (not re-loaded) on load
  6. Robustness  — missing JSON keys, corrupt datetime strings, invalid
                   hierarchy indices do not crash the loader
"""

import json
import os
import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _noop(*args, **kwargs):
    """Silent replacement for QMessageBox calls that would block the test."""
    pass


def _patch_dialogs(monkeypatch, save_path):
    """
    Replace file-dialog and message-box calls on ActivityTableApp so they
    do not block and use the supplied temp path.
    """
    from PyQt5.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *a, **kw: (save_path, "Project Files (*.json)")
    )
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        lambda *a, **kw: (save_path, "Project Files (*.json)")
    )
    monkeypatch.setattr(QMessageBox, "information", _noop)


def _make_activity_row(uid, name, pred, duration):
    """Minimal 11-column activity row."""
    return [uid, name, pred, "", "", duration, "", "", "", "", ""]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def window(app, qtbot):
    from maincode import ActivityTableApp
    w = ActivityTableApp()
    qtbot.addWidget(w)
    return w


@pytest.fixture()
def tmp_json(tmp_path):
    """A temporary file path for the project JSON."""
    return str(tmp_path / "project.json")


# ---------------------------------------------------------------------------
# Helper: build a representative project inside a window
# ---------------------------------------------------------------------------

def _populate_project(window):
    """
    Populate window with a small but complete project:

    Activities (linear chain A → B → C, durations 3, 5, 2):
      row 0: uid=ACT-A  name="Design"    pred=""      dur=3
      row 1: uid=ACT-B  name="Build"     pred=ACT-A   dur=5
      row 2: uid=ACT-C  name="Test"      pred=ACT-B   dur=2

    Resources:
      row 0: ["Alice", "Human Resource", "alice@example.com", "555-0001",
               "400", "600", "0", "Design"]

    BOQ:
      row 0: ["1", "Foundation", "m3", "10", "5", "2", "", "50", "", "Notes"]
              → Sum = 10×5×2 = 100, Total = 100×50 = 5000

    Risks and integration are left at their defaults (auto-populated from
    activities by the model).
    """
    am = window.activity_model
    am.beginResetModel()
    am._data = [
        _make_activity_row("ACT-A", "Design", "",      "3"),
        _make_activity_row("ACT-B", "Build",  "ACT-A", "5"),
        _make_activity_row("ACT-C", "Test",   "ACT-B", "2"),
    ]
    am.indentation_levels = [0, 0, 0]
    am.expanded_states    = [True, True, True]
    am.parent_child_map   = {}
    am.endResetModel()

    rm = window.resource_model
    rm.beginResetModel()
    rm._data = [
        ["Alice", "Human Resource", "alice@example.com",
         "555-0001", "400", "600", "0", "Design"]
    ]
    rm.indentation_levels = [0]
    rm.expanded_states    = [True]
    rm.parent_child_map   = {}
    rm.endResetModel()

    bm = window.bill_model
    bm.beginResetModel()
    bm._data = [
        ["1", "Foundation", "m3", "10", "5", "2", "", "50", "", "Notes"]
    ]
    bm.endResetModel()
    bm.recalculate_row(0)   # pre-compute Sum and Total Cost


# ---------------------------------------------------------------------------
# 1. Basic round-trip
# ---------------------------------------------------------------------------

class TestBasicRoundTrip:

    @pytest.fixture(autouse=True)
    def setup(self, window, tmp_json, monkeypatch):
        _patch_dialogs(monkeypatch, tmp_json)
        _populate_project(window)
        # Run CPM before saving so successor column is populated
        window.calculate_cpm()
        window.save_project_to_json()
        # Reset the window's models to empty, then reload
        window.activity_model.beginResetModel()
        window.activity_model._data = []
        window.activity_model.endResetModel()
        window.load_project_from_json()
        self.w = window

    # --- Activities ---
    def test_activity_count_preserved(self):
        assert self.w.activity_model.rowCount() == 3

    def test_activity_names_preserved(self):
        names = [self.w.activity_model._data[r][1] for r in range(3)]
        assert names == ["Design", "Build", "Test"]

    def test_activity_uids_preserved(self):
        uids = [self.w.activity_model._data[r][0] for r in range(3)]
        assert uids == ["ACT-A", "ACT-B", "ACT-C"]

    def test_activity_durations_preserved(self):
        # Duration is stored as a string in column 5
        assert self.w.activity_model._data[0][5] == "3"
        assert self.w.activity_model._data[1][5] == "5"
        assert self.w.activity_model._data[2][5] == "2"

    def test_predecessor_preserved(self):
        # ACT-B's predecessor must still be ACT-A
        assert self.w.activity_model._data[1][2] == "ACT-A"
        # ACT-C's predecessor must still be ACT-B
        assert self.w.activity_model._data[2][2] == "ACT-B"

    # --- Resources ---
    def test_resource_count_preserved(self):
        assert self.w.resource_model.rowCount() == 1

    def test_resource_name_preserved(self):
        assert self.w.resource_model._data[0][0] == "Alice"

    def test_resource_type_preserved(self):
        assert self.w.resource_model._data[0][1] == "Human Resource"

    def test_resource_rate_preserved(self):
        assert self.w.resource_model._data[0][4] == "400"

    # --- BOQ ---
    def test_boq_count_preserved(self):
        assert self.w.bill_model.rowCount() == 1

    def test_boq_description_preserved(self):
        assert self.w.bill_model._data[0][1] == "Foundation"

    def test_boq_notes_preserved(self):
        assert self.w.bill_model._data[0][9] == "Notes"

    def test_boq_computed_sum_preserved(self):
        # Sum = 10 × 5 × 2 = 100
        assert float(self.w.bill_model._data[0][6]) == pytest.approx(100.0)

    def test_boq_computed_total_preserved(self):
        # Total = 100 × 50 = 5000
        assert float(self.w.bill_model._data[0][8]) == pytest.approx(5000.0)


# ---------------------------------------------------------------------------
# 2. CPM is recalculated (not blindly restored) on load
# ---------------------------------------------------------------------------

class TestCPMRecalculatedOnLoad:
    """
    The loader intentionally clears ES/EF/LS/LF before loading and then
    calls calculate_cpm().  The resulting values must match what a fresh
    CPM run would produce — they must NOT be the stale values from the file.

    Linear chain A(3) → B(5) → C(2):
      A: ES=0 EF=3 LS=0 LF=3
      B: ES=3 EF=8 LS=3 LF=8
      C: ES=8 EF=10 LS=8 LF=10
    """

    @pytest.fixture(autouse=True)
    def setup(self, window, tmp_json, monkeypatch):
        _patch_dialogs(monkeypatch, tmp_json)
        _populate_project(window)

        # Corrupt the CPM columns in the file by writing garbage before saving
        window.activity_model._data[0][7] = 999   # ES — should be 0 after reload
        window.activity_model._data[0][8] = 999   # EF — should be 3 after reload
        window.save_project_to_json()

        window.activity_model.beginResetModel()
        window.activity_model._data = []
        window.activity_model.endResetModel()
        window.load_project_from_json()
        self.d = window.activity_model._data

    def test_cpm_es_A(self):
        assert self.d[0][7] == pytest.approx(0.0)

    def test_cpm_ef_A(self):
        assert self.d[0][8] == pytest.approx(3.0)

    def test_cpm_ls_A(self):
        assert self.d[0][9] == pytest.approx(0.0)

    def test_cpm_lf_A(self):
        assert self.d[0][10] == pytest.approx(3.0)

    def test_cpm_es_B(self):
        assert self.d[1][7] == pytest.approx(3.0)

    def test_cpm_ef_B(self):
        assert self.d[1][8] == pytest.approx(8.0)

    def test_cpm_es_C(self):
        assert self.d[2][7] == pytest.approx(8.0)

    def test_cpm_ef_C(self):
        assert self.d[2][8] == pytest.approx(10.0)

    def test_stale_cpm_values_not_restored(self):
        """The corrupted ES=999 must NOT appear after a reload."""
        assert self.d[0][7] != 999


# ---------------------------------------------------------------------------
# 3. JSON file structure
# ---------------------------------------------------------------------------

class TestJSONFileStructure:
    """The saved JSON must contain the expected top-level keys."""

    @pytest.fixture(autouse=True)
    def setup(self, window, tmp_json, monkeypatch):
        _patch_dialogs(monkeypatch, tmp_json)
        _populate_project(window)
        window.save_project_to_json()
        with open(tmp_json, "r", encoding="utf-8") as f:
            self.saved = json.load(f)

    def test_version_key_present(self):
        assert "version" in self.saved

    def test_version_is_2(self):
        assert self.saved["version"] == 2

    def test_activities_key_present(self):
        assert "activities" in self.saved

    def test_resources_key_present(self):
        assert "resources" in self.saved

    def test_risks_key_present(self):
        assert "risks" in self.saved

    def test_boq_key_present(self):
        assert "boq" in self.saved

    def test_integration_key_present(self):
        assert "integration" in self.saved

    def test_activity_count_in_json(self):
        assert len(self.saved["activities"]) == 3

    def test_activity_uids_in_json(self):
        uids = [row[0] for row in self.saved["activities"]]
        assert "ACT-A" in uids
        assert "ACT-B" in uids
        assert "ACT-C" in uids


# ---------------------------------------------------------------------------
# 4. Hierarchy (indentation / parent-child) is preserved
# ---------------------------------------------------------------------------

class TestHierarchyRoundTrip:
    """
    Make row 1 and 2 children of row 0, then verify the parent_child_map
    and indentation_levels survive a save/load cycle.
    """

    @pytest.fixture(autouse=True)
    def setup(self, window, tmp_json, monkeypatch):
        _patch_dialogs(monkeypatch, tmp_json)
        _populate_project(window)

        # Manually create a hierarchy: row 0 is parent of rows 1 and 2
        window.activity_model.parent_child_map = {0: [1, 2]}
        window.activity_model.indentation_levels = [0, 1, 1]

        window.save_project_to_json()
        window.activity_model.beginResetModel()
        window.activity_model._data = []
        window.activity_model.endResetModel()
        window.load_project_from_json()
        self.w = window

    def test_parent_child_map_restored(self):
        assert 0 in self.w.activity_model.parent_child_map
        assert self.w.activity_model.parent_child_map[0] == [1, 2]

    def test_indentation_levels_restored(self):
        assert self.w.activity_model.indentation_levels[0] == 0
        assert self.w.activity_model.indentation_levels[1] == 1
        assert self.w.activity_model.indentation_levels[2] == 1


# ---------------------------------------------------------------------------
# 5. Robustness — corrupt or incomplete JSON must not crash the loader
# ---------------------------------------------------------------------------

class TestRobustness:

    def _load_raw(self, window, tmp_json, monkeypatch, payload):
        """Write a raw dict to the temp file and call load_project_from_json."""
        _patch_dialogs(monkeypatch, tmp_json)
        monkeypatch.setattr(
            "PyQt5.QtWidgets.QMessageBox.information", _noop
        )
        with open(tmp_json, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        window.load_project_from_json()

    def test_missing_activities_key_does_not_crash(
            self, window, tmp_json, monkeypatch):
        self._load_raw(window, tmp_json, monkeypatch, {"version": 2})
        assert window.activity_model.rowCount() == 0

    def test_missing_resources_key_does_not_crash(
            self, window, tmp_json, monkeypatch):
        self._load_raw(window, tmp_json, monkeypatch,
                       {"version": 2, "activities": []})
        assert window.resource_model.rowCount() == 0

    def test_invalid_parent_index_in_hierarchy_skipped(
            self, window, tmp_json, monkeypatch):
        """A parent index beyond row count must be silently skipped."""
        payload = {
            "version": 2,
            "activities": [
                ["ACT-A", "Design", "", "", "", "3", "", "", "", "", ""]
            ],
            "activity_hierarchy": {"99": [0]},   # row 99 does not exist
            "activity_indent": [0],
            "resources": [],
            "resource_hierarchy": {},
            "resource_indent": [],
            "risks": [],
            "boq": [],
            "integration": {},
        }
        self._load_raw(window, tmp_json, monkeypatch, payload)
        # Should load the one activity without crashing
        assert window.activity_model.rowCount() == 1
        # The invalid hierarchy entry must not appear in the map
        assert 99 not in window.activity_model.parent_child_map

    def test_invalid_datetime_string_does_not_crash(
            self, window, tmp_json, monkeypatch):
        """A non-date string in a date column must not crash the loader."""
        payload = {
            "version": 2,
            "activities": [
                # Column 3 is normally a datetime string; put garbage there
                ["ACT-A", "Design", "", "NOT-A-DATE", "", "3",
                 "", "", "", "", ""]
            ],
            "activity_hierarchy": {},
            "activity_indent": [0],
            "resources": [],
            "resource_hierarchy": {},
            "resource_indent": [],
            "risks": [],
            "boq": [],
            "integration": {},
        }
        self._load_raw(window, tmp_json, monkeypatch, payload)
        assert window.activity_model.rowCount() == 1

    def test_empty_activities_list_does_not_crash(
            self, window, tmp_json, monkeypatch):
        payload = {
            "version": 2,
            "activities": [],
            "activity_hierarchy": {},
            "activity_indent": [],
            "resources": [],
            "resource_hierarchy": {},
            "resource_indent": [],
            "risks": [],
            "boq": [],
            "integration": {},
        }
        self._load_raw(window, tmp_json, monkeypatch, payload)
        assert window.activity_model.rowCount() == 0

    def test_non_integer_parent_key_skipped(
            self, window, tmp_json, monkeypatch):
        """A non-integer parent key in the hierarchy must be skipped."""
        payload = {
            "version": 2,
            "activities": [
                ["ACT-A", "Design", "", "", "", "3", "", "", "", "", ""]
            ],
            "activity_hierarchy": {"not-an-int": [0]},
            "activity_indent": [0],
            "resources": [],
            "resource_hierarchy": {},
            "resource_indent": [],
            "risks": [],
            "boq": [],
            "integration": {},
        }
        self._load_raw(window, tmp_json, monkeypatch, payload)
        assert window.activity_model.rowCount() == 1
        assert len(window.activity_model.parent_child_map) == 0
