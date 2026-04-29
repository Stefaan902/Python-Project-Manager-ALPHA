"""
test_boq.py — Unit tests for BillOfQuantityTableModel.recalculate_row().

recalculate_row() has no dependency on a running QApplication — it only
reads and writes self._data[row].  We therefore instantiate the model
directly and mutate _data by hand, avoiding any GUI overhead.

Column layout:
  [0]  Number of Work      (str)
  [1]  Type of Work        (str)
  [2]  Unit of Measurement (str)
  [3]  Dimension 1         (str/float — input)
  [4]  Dimension 2         (str/float — input)
  [5]  Dimension 3         (str/float — input)
  [6]  Sum                 (float or "" — computed: D1 × D2 × D3)
  [7]  Cost per Unit       (str/float — input)
  [8]  Total Cost          (float or "" — computed: Sum × CostPerUnit)
  [9]  NOTES               (str)

Only numeric dimensions are included in the product.
Missing / non-numeric dimensions are silently skipped.
"""

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_model(app):
    """Return a fresh BillOfQuantityTableModel with one empty row."""
    from maincode import BillOfQuantityTableModel
    model = BillOfQuantityTableModel()
    # Inject one blank row directly — bypasses beginInsertRows signals
    model._data = [["", "", "", "", "", "", "", "", "", ""]]
    return model


def _set(model, d1="", d2="", d3="", cpu=""):
    """Write dimension and cost values into row 0, then recalculate."""
    model._data[0][3] = d1
    model._data[0][4] = d2
    model._data[0][5] = d3
    model._data[0][7] = cpu
    model.recalculate_row(0)


def _sum(model):
    return model._data[0][6]


def _total(model):
    return model._data[0][8]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def model(app):
    return _make_model(app)


# ---------------------------------------------------------------------------
# Sum (column 6) — product of whichever dimensions are numeric
# ---------------------------------------------------------------------------

class TestSum:

    def test_all_three_dimensions(self, model):
        """Sum = D1 × D2 × D3 when all three are present."""
        _set(model, "2", "3", "4")
        assert _sum(model) == pytest.approx(24.0)

    def test_two_dimensions(self, model):
        """Sum = D1 × D2 when D3 is absent."""
        _set(model, "5", "4", "")
        assert _sum(model) == pytest.approx(20.0)

    def test_one_dimension(self, model):
        """Sum = D1 when D2 and D3 are absent."""
        _set(model, "7", "", "")
        assert _sum(model) == pytest.approx(7.0)

    def test_no_dimensions_gives_empty_string(self, model):
        """When no dimension is numeric, Sum must be '' (not 0)."""
        _set(model, "", "", "")
        assert _sum(model) == ""

    def test_non_numeric_dimension_skipped(self, model):
        """A non-numeric dimension string is silently ignored."""
        _set(model, "3", "N/A", "2")
        # Only D1 and D3 are valid: 3 × 2 = 6
        assert _sum(model) == pytest.approx(6.0)

    def test_float_dimensions(self, model):
        """Decimal dimension strings are handled correctly."""
        _set(model, "1.5", "2.0", "4.0")
        assert _sum(model) == pytest.approx(12.0)

    def test_fractional_result(self, model):
        """Fractional products are preserved as floats."""
        _set(model, "1.5", "1.5", "")
        assert _sum(model) == pytest.approx(2.25)

    def test_zero_dimension_makes_sum_zero(self, model):
        """A zero dimension is valid and collapses the product to 0."""
        _set(model, "0", "5", "3")
        assert _sum(model) == pytest.approx(0.0)

    def test_whitespace_only_dimension_skipped(self, model):
        """Whitespace-only strings are not numeric and must be skipped."""
        _set(model, "4", "   ", "3")
        # Only D1 and D3: 4 × 3 = 12
        assert _sum(model) == pytest.approx(12.0)

    def test_negative_dimension(self, model):
        """Negative values are arithmetically valid and must be accepted."""
        _set(model, "-2", "3", "")
        assert _sum(model) == pytest.approx(-6.0)

    def test_large_values(self, model):
        """Large numbers must not overflow or lose precision."""
        _set(model, "1000", "1000", "1000")
        assert _sum(model) == pytest.approx(1_000_000_000.0)


# ---------------------------------------------------------------------------
# Total Cost (column 8) = Sum × Cost per Unit
# ---------------------------------------------------------------------------

class TestTotalCost:

    def test_basic_total_cost(self, model):
        """Total Cost = Sum × Cost per Unit."""
        _set(model, "2", "3", "4", cpu="10")
        # Sum = 24, Total = 240
        assert _total(model) == pytest.approx(240.0)

    def test_total_cost_with_two_dimensions(self, model):
        _set(model, "5", "4", "", cpu="3")
        # Sum = 20, Total = 60
        assert _total(model) == pytest.approx(60.0)

    def test_total_cost_with_one_dimension(self, model):
        _set(model, "8", "", "", cpu="5")
        # Sum = 8, Total = 40
        assert _total(model) == pytest.approx(40.0)

    def test_zero_cost_per_unit(self, model):
        """A zero unit cost yields a zero total, not an error."""
        _set(model, "5", "5", "", cpu="0")
        assert _total(model) == pytest.approx(0.0)

    def test_fractional_cost_per_unit(self, model):
        _set(model, "10", "", "", cpu="1.5")
        assert _total(model) == pytest.approx(15.0)

    def test_no_dimensions_total_is_empty(self, model):
        """When Sum is '', Total Cost must also be '' regardless of CPU."""
        _set(model, "", "", "", cpu="50")
        assert _total(model) == ""

    def test_no_cpu_total_is_empty(self, model):
        """When Cost per Unit is '', Total Cost must be ''."""
        _set(model, "5", "3", "")
        # cpu defaults to ""
        assert _total(model) == ""

    def test_non_numeric_cpu_total_is_empty(self, model):
        """A non-numeric CPU string must not crash; Total must be ''."""
        _set(model, "5", "3", "", cpu="TBD")
        assert _total(model) == ""

    def test_negative_cpu(self, model):
        """A negative unit cost is arithmetically valid."""
        _set(model, "4", "5", "", cpu="-2")
        # Sum = 20, Total = -40
        assert _total(model) == pytest.approx(-40.0)

    def test_both_dimensions_and_cpu_are_floats(self, model):
        _set(model, "2.5", "4.0", "", cpu="3.0")
        # Sum = 10.0, Total = 30.0
        assert _total(model) == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Idempotency — calling recalculate_row twice must give the same result
# ---------------------------------------------------------------------------

class TestIdempotency:

    def test_recalculate_twice_same_result(self, model):
        """recalculate_row() must be idempotent."""
        _set(model, "3", "4", "2", cpu="5")
        first_sum = _sum(model)
        first_total = _total(model)

        model.recalculate_row(0)   # call a second time
        assert _sum(model) == pytest.approx(first_sum)
        assert _total(model) == pytest.approx(first_total)


# ---------------------------------------------------------------------------
# Multiple rows — recalculate_row(n) must only affect row n
# ---------------------------------------------------------------------------

class TestMultipleRows:

    def test_recalculate_does_not_affect_other_rows(self, app):
        """Recalculating row 0 must leave row 1 untouched."""
        from maincode import BillOfQuantityTableModel
        model = BillOfQuantityTableModel()
        model._data = [
            ["", "", "", "2", "3", "", "", "10", "", ""],
            ["", "", "", "7", "8", "", "", "2",  "", ""],
        ]

        model.recalculate_row(0)
        # Row 0: Sum=6, Total=60
        assert model._data[0][6] == pytest.approx(6.0)
        assert model._data[0][8] == pytest.approx(60.0)
        # Row 1 columns 6 and 8 must still be their original values
        assert model._data[1][6] == ""
        assert model._data[1][8] == ""

    def test_recalculate_each_row_independently(self, app):
        """Each row can be recalculated independently."""
        from maincode import BillOfQuantityTableModel
        model = BillOfQuantityTableModel()
        model._data = [
            ["", "", "", "2", "3", "", "", "10", "", ""],
            ["", "", "", "7", "8", "", "", "2",  "", ""],
        ]

        model.recalculate_row(0)
        model.recalculate_row(1)

        assert model._data[0][6] == pytest.approx(6.0)
        assert model._data[0][8] == pytest.approx(60.0)
        assert model._data[1][6] == pytest.approx(56.0)
        assert model._data[1][8] == pytest.approx(112.0)


# ---------------------------------------------------------------------------
# Column read-only enforcement (flags)
# ---------------------------------------------------------------------------

class TestReadOnlyColumns:

    def test_sum_column_is_read_only(self, app):
        """Column 6 (Sum) must not be editable via flags()."""
        from maincode import BillOfQuantityTableModel
        from PyQt5.QtCore import Qt
        model = BillOfQuantityTableModel()
        model._data = [[""] * 10]
        index = model.index(0, 6)
        flags = model.flags(index)
        assert not (flags & Qt.ItemIsEditable), "Sum column must be read-only"

    def test_total_cost_column_is_read_only(self, app):
        """Column 8 (Total Cost) must not be editable via flags()."""
        from maincode import BillOfQuantityTableModel
        from PyQt5.QtCore import Qt
        model = BillOfQuantityTableModel()
        model._data = [[""] * 10]
        index = model.index(0, 8)
        flags = model.flags(index)
        assert not (flags & Qt.ItemIsEditable), "Total Cost column must be read-only"

    def test_dimension_column_is_editable(self, app):
        """Dimension columns (3, 4, 5) must be editable."""
        from maincode import BillOfQuantityTableModel
        from PyQt5.QtCore import Qt
        model = BillOfQuantityTableModel()
        model._data = [[""] * 10]
        for col in [3, 4, 5]:
            index = model.index(0, col)
            flags = model.flags(index)
            assert flags & Qt.ItemIsEditable, f"Column {col} must be editable"
