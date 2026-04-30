"""
test_cpm.py — Step 2: Unit tests for calculate_cpm().

Strategy
--------
calculate_cpm() reads directly from self.activity_model._data and writes
results back to the same list.  We therefore bypass the full GUI by:

  1. Creating an ActivityTableApp (requires a QApplication, but no display).
  2. Populating activity_model._data by hand with minimal rows.
  3. Calling calculate_cpm() directly.
  4. Reading the results back from _data.

Row layout (columns 0-10):
  [0]  activity UUID  (str)
  [1]  name           (str)
  [2]  predecessor(s) (str, semicolon-separated UUIDs; "" = none)
  [3]  start date     (QDateTime or str — not used by calculate_cpm)
  [4]  end date       (str  — not used by calculate_cpm)
  [5]  duration       (str  — converted to float inside calculate_cpm)
  [6]  successors     (str  — written back by calculate_cpm)
  [7]  ES             (float — written by calculate_cpm)
  [8]  EF             (float — written by calculate_cpm)
  [9]  LS             (float — written by calculate_cpm)
  [10] LF             (float — written by calculate_cpm)

Predecessor references use the UUID stored in column 0, NOT row numbers.
"""

import pytest
from maincode import days_between

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(uid, name="", pred="", duration="0", actID="", wbsID=""):
    """Return a minimal 13-element data row for ActivityTableModel."""
    """[0]UUID [1]ActivityNo [2]WBS_ID [3]Name [4]Predecessor [5]StartDate [6]EndDate [7]Duration [8]Successors [9]ES [10]EF [11]LS [12]LF"""
    return [uid, actID, wbsID, name, pred, "", "", duration, "", "", "", "", ""]


def _load_rows(window, rows):
    """
    Directly inject pre-built rows into the activity model, bypassing
    insertRows() so we avoid any side-effects (signal emissions, etc.).
    """
    model = window.activity_model
    model.beginResetModel()
    model._data = rows
    model.indentation_levels = [0] * len(rows)
    model.expanded_states = [True] * len(rows)
    model.parent_child_map = {}
    model.endResetModel()


def _cpm(window):
    """Run CPM and return (data, ES, EF, LS, LF) indexed by UUID."""
    window.calculate_cpm()
    result = {}
    for row in window.activity_model._data:
        uid = row[0]
        result[uid] = {
            "ES": row[9],
            "EF": row[10],
            "LS": row[11],
            "LF": row[12],
            "successors": row[8],
        }
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def window(app, qtbot):
    """Fresh ActivityTableApp for each test, never shown on screen."""
    from maincode import ActivityTableApp
    w = ActivityTableApp()
    qtbot.addWidget(w)
    return w


# ---------------------------------------------------------------------------
# Single activity
# ---------------------------------------------------------------------------

class TestSingleActivity:
    """A project with one activity and no dependencies."""

    def test_single_activity_es_is_zero(self, window):
        rows = [_make_row("A", "Task A", "", "5")]
        _load_rows(window, rows)
        r = _cpm(window)
        assert r["A"]["ES"] == 0

    def test_single_activity_ef_equals_duration(self, window):
        rows = [_make_row("A", "Task A", "", "5")]
        _load_rows(window, rows)
        r = _cpm(window)
        assert r["A"]["EF"] == 5

    def test_single_activity_ls_is_zero(self, window):
        rows = [_make_row("A", "Task A", "", "5")]
        _load_rows(window, rows)
        r = _cpm(window)
        assert r["A"]["LS"] == 0

    def test_single_activity_lf_equals_duration(self, window):
        rows = [_make_row("A", "Task A", "", "5")]
        _load_rows(window, rows)
        r = _cpm(window)
        assert r["A"]["LF"] == 5

    def test_single_activity_zero_duration(self, window):
        rows = [_make_row("A", "Milestone", "", "0")]
        _load_rows(window, rows)
        r = _cpm(window)
        assert r["A"]["ES"] == 0
        assert r["A"]["EF"] == 0
        assert r["A"]["LS"] == 0
        assert r["A"]["LF"] == 0


# ---------------------------------------------------------------------------
# Linear chain  A → B → C
# ---------------------------------------------------------------------------

class TestLinearChain:
    """
    A → B → C  (durations 2, 3, 4)

    Expected values (hand-calculated):
      A: ES=0  EF=2  LS=0  LF=2   float=0
      B: ES=2  EF=5  LS=2  LF=5   float=0
      C: ES=5  EF=9  LS=5  LF=9   float=0
    All activities are on the critical path.
    """

    @pytest.fixture(autouse=True)
    def setup(self, window):
        rows = [
            _make_row("A", "Task A", "",  "2"),
            _make_row("B", "Task B", "A", "3"),
            _make_row("C", "Task C", "B", "4"),
        ]
        _load_rows(window, rows)
        self.r = _cpm(window)

    def test_A_ES(self): assert self.r["A"]["ES"] == 0
    def test_A_EF(self): assert self.r["A"]["EF"] == 2
    def test_A_LS(self): assert self.r["A"]["LS"] == 0
    def test_A_LF(self): assert self.r["A"]["LF"] == 2

    def test_B_ES(self): assert self.r["B"]["ES"] == 2
    def test_B_EF(self): assert self.r["B"]["EF"] == 5
    def test_B_LS(self): assert self.r["B"]["LS"] == 2
    def test_B_LF(self): assert self.r["B"]["LF"] == 5

    def test_C_ES(self): assert self.r["C"]["ES"] == 5
    def test_C_EF(self): assert self.r["C"]["EF"] == 9
    def test_C_LS(self): assert self.r["C"]["LS"] == 5
    def test_C_LF(self): assert self.r["C"]["LF"] == 9

    def test_all_float_zero(self):
        """Every activity in a linear chain has zero float."""
        for uid in ("A", "B", "C"):
            float_val = self.r[uid]["LS"] - self.r[uid]["ES"]
            assert float_val == 0, f"Activity {uid} should have zero float"

    def test_successors_written_back(self):
        """calculate_cpm must populate the successors column (col 6)."""
        assert "B" in self.r["A"]["successors"]
        assert "C" in self.r["B"]["successors"]
        assert self.r["C"]["successors"] == ""


# ---------------------------------------------------------------------------
# Fork-join (diamond) network
#
#        B (dur=3)
#       / \
#  A  -    - D
#       \ /
#        C (dur=6)
#
#  A=2, B=3, C=6, D=1
# ---------------------------------------------------------------------------

class TestDiamondNetwork:
    """
    Diamond: A → B → D  and  A → C → D

    Durations: A=2, B=3, C=6, D=1
    Project duration = 2 + 6 + 1 = 9

    Expected (hand-calculated):
      A: ES=0  EF=2  LS=0  LF=2   float=0  (critical)
      B: ES=2  EF=5  LS=4  LF=7   float=2  (non-critical)
      C: ES=2  EF=8  LS=2  LF=8   float=0  (critical)
      D: ES=8  EF=9  LS=8  LF=9   float=0  (critical)
    """

    @pytest.fixture(autouse=True)
    def setup(self, window):
        rows = [
            _make_row("A", "Start",   "",    "2"),
            _make_row("B", "Short",   "A",   "3"),
            _make_row("C", "Long",    "A",   "6"),
            _make_row("D", "Finish",  "B;C", "1"),
        ]
        _load_rows(window, rows)
        self.r = _cpm(window)

    def test_project_duration(self):
        assert self.r["D"]["EF"] == 9

    def test_A_is_critical(self):
        assert self.r["A"]["ES"] == 0
        assert self.r["A"]["EF"] == 2
        assert self.r["A"]["LS"] == 0
        assert self.r["A"]["LF"] == 2

    def test_B_has_float(self):
        """B is on the non-critical path — it must have positive float."""
        assert self.r["B"]["ES"] == 2
        assert self.r["B"]["EF"] == 5
        assert self.r["B"]["LS"] == 5
        assert self.r["B"]["LF"] == 8
        assert (self.r["B"]["LS"] - self.r["B"]["ES"]) == 3

    def test_C_is_critical(self):
        assert self.r["C"]["ES"] == 2
        assert self.r["C"]["EF"] == 8
        assert self.r["C"]["LS"] == 2
        assert self.r["C"]["LF"] == 8
        assert (self.r["C"]["LS"] - self.r["C"]["ES"]) == 0

    def test_D_is_critical(self):
        assert self.r["D"]["ES"] == 8
        assert self.r["D"]["EF"] == 9
        assert self.r["D"]["LS"] == 8
        assert self.r["D"]["LF"] == 9

    def test_D_waits_for_longest_predecessor(self):
        """D's ES must be driven by C (EF=8), not B (EF=5)."""
        assert self.r["D"]["ES"] == 8


# ---------------------------------------------------------------------------
# Multiple independent start activities (no shared root)
# ---------------------------------------------------------------------------

class TestParallelIndependentChains:
    """
    Two completely independent chains: X→Y  and  P→Q
    Durations: X=4, Y=3, P=1, Q=10
    Project duration = max(7, 11) = 11

    Expected:
      X: ES=0  EF=4   LS=4   LF=8   float=4
      Y: ES=4  EF=7   LS=8   LF=11  float=4
      P: ES=0  EF=1   LS=0   LF=1   float=0
      Q: ES=1  EF=11  LS=1   LF=11  float=0
    """

    @pytest.fixture(autouse=True)
    def setup(self, window):
        rows = [
            _make_row("X", "X", "",  "4"),
            _make_row("Y", "Y", "X", "3"),
            _make_row("P", "P", "",  "1"),
            _make_row("Q", "Q", "P", "10"),
        ]
        _load_rows(window, rows)
        self.r = _cpm(window)

    def test_project_duration(self):
        assert self.r["Q"]["EF"] == 11

    def test_X_float(self):
        assert (self.r["X"]["LS"] - self.r["X"]["ES"]) == 4

    def test_Y_float(self):
        assert (self.r["Y"]["LS"] - self.r["Y"]["ES"]) == 4

    def test_P_float(self):
        assert (self.r["P"]["LS"] - self.r["P"]["ES"]) == 0

    def test_Q_float(self):
        assert (self.r["Q"]["LS"] - self.r["Q"]["ES"]) == 0


# ---------------------------------------------------------------------------
# Edge cases — duration parsing
# ---------------------------------------------------------------------------

class TestDurationParsing:
    """calculate_cpm must tolerate unusual duration values gracefully."""

    def test_float_duration_string(self, window):
        """A decimal string like '2.5' must be parsed as float, not crash."""
        rows = [_make_row("A", "A", "", "2.5")]
        _load_rows(window, rows)
        r = _cpm(window)
        assert r["A"]["EF"] == pytest.approx(2.5)

    def test_empty_duration_treated_as_zero(self, window):
        """An empty duration string must not crash; treated as 0."""
        rows = [
            _make_row("A", "A", "",  "3"),
            _make_row("B", "B", "A", ""),   # empty duration
        ]
        _load_rows(window, rows)
        r = _cpm(window)
        assert r["B"]["EF"] == pytest.approx(3.0)   # ES=3 + 0 duration

    def test_non_numeric_duration_treated_as_zero(self, window):
        """A non-numeric duration string must not crash; treated as 0."""
        rows = [_make_row("A", "A", "", "N/A")]
        _load_rows(window, rows)
        r = _cpm(window)
        assert r["A"]["EF"] == 0

    def test_whitespace_only_duration_treated_as_zero(self, window):
        rows = [_make_row("A", "A", "", "   ")]
        _load_rows(window, rows)
        r = _cpm(window)
        # "   " is falsy after strip → treated as 0
        assert r["A"]["EF"] == 0


# ---------------------------------------------------------------------------
# Edge cases — predecessor parsing
# ---------------------------------------------------------------------------

class TestPredecessorParsing:
    """Semicolon-separated predecessor strings must be handled robustly."""

    def test_predecessor_with_spaces(self, window):
        """Spaces around the semicolon separator must be stripped."""
        rows = [
            _make_row("A", "A", "",       "3"),
            _make_row("B", "B", " A ; ", "4"),   # spaces around A and trailing
        ]
        _load_rows(window, rows)
        r = _cpm(window)
        assert r["B"]["ES"] == 3

    def test_unknown_predecessor_uuid_is_ignored(self, window):
        """A predecessor UUID not present in the model must not crash."""
        rows = [
            _make_row("A", "A", "UNKNOWN-UUID", "5"),
        ]
        _load_rows(window, rows)
        r = _cpm(window)
        # UNKNOWN-UUID is silently skipped; A is treated as a start activity
        assert r["A"]["ES"] == 0
        assert r["A"]["EF"] == 5

    def test_multiple_predecessors_semicolon_separated(self, window):
        """B depends on both A1 and A2; ES(B) = max(EF(A1), EF(A2))."""
        rows = [
            _make_row("A1", "A1", "",       "3"),
            _make_row("A2", "A2", "",       "7"),
            _make_row("B",  "B",  "A1;A2",  "2"),
        ]
        _load_rows(window, rows)
        r = _cpm(window)
        assert r["B"]["ES"] == 7   # driven by A2, not A1


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------

class TestCycleDetection:
    """A cyclic dependency graph must be detected and must not crash."""

    def test_direct_cycle_does_not_crash(self, window, qtbot, monkeypatch):
        """
        A → B → A forms a cycle.
        calculate_cpm must call QMessageBox.critical and return cleanly
        (the model is left in whatever partial state it was in).
        """
        from PyQt5.QtWidgets import QMessageBox

        # Intercept QMessageBox.critical so the test does not block waiting
        # for user input.
        critical_calls = []
        monkeypatch.setattr(
            QMessageBox, "critical",
            lambda *args, **kwargs: critical_calls.append(args)
        )

        rows = [
            _make_row("A", "A", "B", "3"),
            _make_row("B", "B", "A", "3"),
        ]
        _load_rows(window, rows)
        window.calculate_cpm()   # must not raise

        assert len(critical_calls) == 1, (
            "QMessageBox.critical must be called exactly once for a cycle"
        )
        # The error message must mention "cycle" (case-insensitive)
        error_message = str(critical_calls[0]).lower()
        assert "cycle" in error_message

    def test_three_way_cycle_does_not_crash(self, window, monkeypatch):
        """A → B → C → A is a three-node cycle."""
        from PyQt5.QtWidgets import QMessageBox

        critical_calls = []
        monkeypatch.setattr(
            QMessageBox, "critical",
            lambda *args, **kwargs: critical_calls.append(args)
        )

        rows = [
            _make_row("A", "A", "C", "1"),
            _make_row("B", "B", "A", "1"),
            _make_row("C", "C", "B", "1"),
        ]
        _load_rows(window, rows)
        window.calculate_cpm()

        assert len(critical_calls) == 1


# ---------------------------------------------------------------------------
# Empty model
# ---------------------------------------------------------------------------

class TestEmptyModel:
    """calculate_cpm on an empty model must be a no-op."""

    def test_empty_model_does_not_crash(self, window):
        # No rows loaded → _data is []
        window.activity_model._data = []
        window.activity_model.indentation_levels = []
        window.activity_model.expanded_states = []
        window.calculate_cpm()   # must not raise

    def test_empty_model_leaves_data_empty(self, window):
        window.activity_model._data = []
        window.activity_model.indentation_levels = []
        window.activity_model.expanded_states = []
        window.calculate_cpm()
        assert window.activity_model._data == []


# ---------------------------------------------------------------------------
# Successor column is written back correctly
# ---------------------------------------------------------------------------

class TestSuccessorWriteback:
    """
    calculate_cpm also populates column 8 (successors) as a side effect.
    Verify this separately for correctness.
    """

    def test_successor_written_for_simple_chain(self, window):
        rows = [
            _make_row("A", "A", "",  "2"),
            _make_row("B", "B", "A", "3"),
        ]
        _load_rows(window, rows)
        window.calculate_cpm()
        # Column 8 of row 0 (A) must reference B
        assert window.activity_model._data[0][8] == "B"

    def test_leaf_has_empty_successors(self, window):
        rows = [
            _make_row("A", "A", "",  "2"),
            _make_row("B", "B", "A", "3"),
        ]
        _load_rows(window, rows)
        window.calculate_cpm()
        # Column 8 of row 1 (B) must be empty
        assert window.activity_model._data[1][8] == ""

    def test_multiple_successors_written(self, window):
        """A has two successors (B and C); both must appear in col 8."""
        rows = [
            _make_row("A", "A", "",  "1"),
            _make_row("B", "B", "A", "2"),
            _make_row("C", "C", "A", "3"),
        ]
        _load_rows(window, rows)
        window.calculate_cpm()
        successors = window.activity_model._data[0][8].split(";")
        assert "B" in successors
        assert "C" in successors

"""
test_days_between.py — Unit tests for the days_between() utility function.

Paste the implementation under test at the top of this file, or import it
from wherever you define it in your project, e.g.:

    from project_manager import days_between

The implementation assumed here:

    from datetime import datetime

    FMT = "%Y-%m-%d %H:%M"

    def days_between(start: str, end: str) -> int | None:
        try:
            return (datetime.strptime(end, FMT) - datetime.strptime(start, FMT)).days
        except (ValueError, TypeError):
            return None
"""

# ═════════════════════════════════════════════════════════════════════════════
# 1. Normal positive differences
# ═════════════════════════════════════════════════════════════════════════════

class TestPositiveDifference:

    def test_exactly_one_day(self, window):
        assert days_between("2025-01-01 00:00", "2025-01-02 00:00") == 1

    def test_exactly_one_week(self, window):
        assert days_between("2025-01-01 00:00", "2025-01-08 00:00") == 7

    def test_across_month_boundary(self, window):
        assert days_between("2025-01-28 00:00", "2025-02-03 00:00") == 6

    def test_across_year_boundary(self, window):
        assert days_between("2024-12-25 00:00", "2025-01-05 00:00") == 11

    def test_known_span_73_days(self, window):
        assert days_between("2025-01-01 08:00", "2025-03-15 08:00") == 73

    def test_large_span_multiple_years(self, window):
        assert days_between("2020-01-01 00:00", "2025-01-01 00:00") == 1827  # includes 2020, 2024 leap years


# ═════════════════════════════════════════════════════════════════════════════
# 2. Zero difference
# ═════════════════════════════════════════════════════════════════════════════

class TestZeroDifference:

    def test_same_datetime_is_zero(self, window):
        assert days_between("2025-06-15 09:30", "2025-06-15 09:30") == 0

    def test_same_date_different_time_is_zero(self, window):
        """Times differ but not by a full day — result must be 0, not 1."""
        assert days_between("2025-06-15 08:00", "2025-06-15 23:59") == 0


# ═════════════════════════════════════════════════════════════════════════════
# 3. Negative difference (end before start)
# ═════════════════════════════════════════════════════════════════════════════

class TestNegativeDifference:

    def test_end_before_start_is_negative(self, window):
        assert days_between("2025-03-01 00:00", "2025-01-01 00:00") == -59

    def test_one_day_negative(self):
        assert days_between("2025-01-02 00:00", "2025-01-01 00:00") == -1


# ═════════════════════════════════════════════════════════════════════════════
# 4. Leap year handling
# ═════════════════════════════════════════════════════════════════════════════

class TestLeapYear:

    def test_span_across_feb29_in_leap_year(self, window):
        """2024 is a leap year — Feb has 29 days."""
        assert days_between("2024-02-28 00:00", "2024-03-01 00:00") == 2

    def test_span_across_feb_in_non_leap_year(self, window):
        """2025 is not a leap year — Feb has 28 days."""
        assert days_between("2025-02-28 00:00", "2025-03-01 00:00") == 1

    def test_full_leap_year(self, window):
        assert days_between("2024-01-01 00:00", "2025-01-01 00:00") == 366

    def test_full_non_leap_year(self):
        assert days_between("2025-01-01 00:00", "2026-01-01 00:00") == 365


# ═════════════════════════════════════════════════════════════════════════════
# 5. Time-of-day truncation behaviour
# ═════════════════════════════════════════════════════════════════════════════

class TestTimeOfDayTruncation:
    """
    .days truncates toward zero — it does NOT round.
    23h 59m difference → 0 days.
    24h 01m difference → 1 day.
    """

    def test_23h59m_is_zero_days(self, window):
        assert days_between("2025-01-01 00:00", "2025-01-01 23:59") == 0

    def test_24h01m_is_one_day(self, window):
        assert days_between("2025-01-01 00:00", "2025-01-02 00:01") == 1

    def test_morning_to_next_morning_is_one_day(self, window):
        assert days_between("2025-04-01 08:00", "2025-04-02 08:00") == 1

    def test_late_to_early_next_day_is_zero(self):
        """Start at 22:00, end at 06:00 next day — less than 24 h → 0 days."""
        assert days_between("2025-04-01 22:00", "2025-04-02 06:00") == 0


# ═════════════════════════════════════════════════════════════════════════════
# 6. Invalid / malformed input
# ═════════════════════════════════════════════════════════════════════════════

class TestInvalidInput:

    def test_empty_start_returns_none(self, window):
        assert days_between("", "2025-01-01 00:00") is None

    def test_empty_end_returns_none(self, window):
        assert days_between("2025-01-01 00:00", "") is None

    def test_both_empty_returns_none(self, window):
        assert days_between("", "") is None

    def test_none_start_returns_none(self, window):
        assert days_between(None, "2025-01-01 00:00") is None

    def test_none_end_returns_none(self, window):
        assert days_between("2025-01-01 00:00", None) is None

    def test_wrong_format_returns_none(self, window):
        """DD/MM/YYYY is not the expected mask."""
        assert days_between("01/01/2025", "02/01/2025") is None

    def test_date_only_no_time_returns_none(self, window):
        """Missing HH:mm component does not match the mask."""
        assert days_between("2025-01-01", "2025-01-02") is None

    def test_invalid_month_returns_none(self, window):
        assert days_between("2025-13-01 00:00", "2025-01-01 00:00") is None

    def test_invalid_day_returns_none(self, window):
        assert days_between("2025-01-32 00:00", "2025-02-01 00:00") is None

    def test_non_string_integer_returns_none(self, window):
        assert days_between(20250101, "2025-01-02 00:00") is None

    def test_arbitrary_string_returns_none(self, window):
        assert days_between("not a date", "also not a date") is None


# ═════════════════════════════════════════════════════════════════════════════
# 7. Symmetry property
# ═════════════════════════════════════════════════════════════════════════════

class TestSymmetry:
    """days_between(a, b) == -days_between(b, a) for any valid pair if they specify the same time."""

    @pytest.mark.parametrize("start, end", [
        ("2025-01-01 00:00", "2025-06-30 00:00"),
        ("2024-02-29 08:00", "2024-03-15 08:00"),
        ("2020-01-01 23:59", "2030-12-31 23:59"),
    ])
    def test_reverse_is_ok(self, start, end, window):
        assert days_between(start, end) == -days_between(end, start)

    @pytest.mark.parametrize("start, end", [
        ("2025-01-01 01:00", "2025-06-30 00:00"),
        ("2024-02-29 08:00", "2024-03-15 12:00"),
        ("2020-01-01 01:01", "2030-12-31 23:59"),
    ])
    def test_reverse_is_not_ok(self, start, end, window):
        assert days_between(start, end) != -days_between(end, start)