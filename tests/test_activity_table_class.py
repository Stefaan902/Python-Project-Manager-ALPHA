import pytest
import uuid

from PyQt5.QtCore import Qt, QDateTime, QModelIndex
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import QApplication

# import your model here
# from project_manager import ActivityTableModel
from models import ActivityTableModel
# days_between must also be importable
from project_manager import days_between


@pytest.fixture(scope="session")
def qapp():
    """Ensure a QApplication exists for all Qt tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def model(qapp):
    """Return a fresh ActivityTableModel for each test."""
    return ActivityTableModel()


def populate_basic_data(model):
    """
    Helper to populate model with 3 rows:
    row 0 = parent
    row 1,2 = children
    """
    model._data = [
        ["p", "1", "", "Parent", "", QDateTime.fromString("2024-01-01 08:00", "yyyy-MM-dd HH:mm"),
         "2024-01-10 08:00", "0", "", "", "", "", ""],
        ["c1", "2", "", "Child 1", "p", QDateTime.fromString("2024-01-01 08:00", "yyyy-MM-dd HH:mm"),
         "2024-01-03 08:00", "2", "", "", "", "", ""],
        ["c2", "3", "", "Child 2", "p", QDateTime.fromString("2024-01-05 08:00", "yyyy-MM-dd HH:mm"),
         "2024-01-10 08:00", "5", "", "", "", "", ""],
    ]
    model.indentation_levels = [0, 1, 1]
    model.expanded_states = [True, True, True]
    model.parent_child_map = {0: [1, 2]}


# -------------------------------------------------------------------
# BASIC MODEL SHAPE
# -------------------------------------------------------------------

def test_row_and_column_count(model):
    assert model.rowCount() == 0
    assert model.columnCount() == len(model.headers)


def test_insert_and_remove_rows(model):
    assert model.insertRows(0, 2) is True
    assert model.rowCount() == 2
    assert model.removeRows(0, 1) is True
    assert model.rowCount() == 1


# -------------------------------------------------------------------
# DATA()
# -------------------------------------------------------------------

def test_data_invalid_index(model):
    assert model.data(QModelIndex()) is None


def test_data_display_and_roles(model):
    populate_basic_data(model)

    index_name = model.index(1, 3)
    index_start = model.index(1, 5)

    # DisplayRole with indentation
    text = model.data(index_name, Qt.DisplayRole)
    assert text.startswith("  ")

    # DisplayRole with QDateTime formatting
    date_text = model.data(index_start, Qt.DisplayRole)
    assert "2024-01-01" in date_text

    # EditRole
    assert model.data(index_name, Qt.EditRole) == "Child 1"

    # BackgroundRole (parent)
    brush = model.data(model.index(0, 0), Qt.BackgroundRole)
    assert isinstance(brush, QBrush)

    # Non-parent background
    assert model.data(model.index(1, 0), Qt.BackgroundRole) is None


# -------------------------------------------------------------------
# setData
# -------------------------------------------------------------------

def test_set_data(model):
    populate_basic_data(model)

    index = model.index(1, 7)
    assert model.setData(index, "10", Qt.EditRole) is True
    assert model._data[1][7] == "10"

    dt = QDateTime.currentDateTime()
    index_dt = model.index(1, 5)
    assert model.setData(index_dt, dt, Qt.EditRole) is True
    assert model._data[1][5] == dt

    assert model.setData(QModelIndex(), "x") is False
    assert model.setData(index, "x", Qt.DisplayRole) is False


# -------------------------------------------------------------------
# headerData
# -------------------------------------------------------------------

def test_header_data(model):
    assert model.headerData(0, Qt.Horizontal) == "ID"
    assert model.headerData(0, Qt.Vertical) is None


# -------------------------------------------------------------------
# flags
# -------------------------------------------------------------------

def test_flags(model):
    populate_basic_data(model)

    # Invalid
    assert model.flags(QModelIndex()) == Qt.NoItemFlags

    # System columns
    assert model.flags(model.index(0, 0)) != Qt.ItemIsEditable  # UUID is read-only
    assert model.flags(model.index(0, 1)) != Qt.ItemIsEditable  # ActivityID is read-only
    assert model.flags(model.index(0, 2)) != Qt.ItemIsEditable  # Wbs ID is read-only

    # Read-only column
    assert model.flags(model.index(0, 6)) != Qt.ItemIsEditable # End is read-only

    # Duration of parent is read-only
    assert model.flags(model.index(0, 7)) != Qt.ItemIsEditable

    # Editable column
    assert model.flags(model.index(1, 4)) == Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable


# -------------------------------------------------------------------
# getters/setters
# -------------------------------------------------------------------

def test_get_and_set_all_data(model):
    data = [["1"] * len(model.headers)]
    model.set_all_data(data)
    assert model.get_all_data() == data


# -------------------------------------------------------------------
# recalc_parent_activities
# -------------------------------------------------------------------

def test_recalc_parent_activities(model):
    populate_basic_data(model)
    model.recalc_parent_activities()

    parent = model._data[0]
    assert isinstance(parent[5], QDateTime)
    assert parent[6] == "2024-01-10 08:00"
    assert float(parent[7]) == 7.0  # 2 + 5


# -------------------------------------------------------------------
# recalculate_activity_numbers + WBS
# -------------------------------------------------------------------

def test_recalculate_activity_numbers_and_wbs(model):
    populate_basic_data(model)

    model.recalculate_activity_numbers()

    assert model._data[0][1] == "1"
    assert model._data[1][1] == "2"

    # WBS
    assert model._data[0][2] == "1"
    assert model._data[1][2] == "1.1"
    assert model._data[2][2] == "1.2"


# -------------------------------------------------------------------
# get_parent_row
# -------------------------------------------------------------------

def test_get_parent_row(model):
    populate_basic_data(model)

    assert model.get_parent_row(1) == 0
    assert model.get_parent_row(999) is None


# -------------------------------------------------------------------
# recalc_ancestors
# -------------------------------------------------------------------

def test_recalc_ancestors(model):
    populate_basic_data(model)

    # Trigger recalculation from child
    model.recalc_ancestors(2)

    parent = model._data[0]

    assert isinstance(parent[5], QDateTime)
    assert parent[6].startswith("2024-01-10")
    assert isinstance(parent[7], (int, float))


def test_recalc_ancestors_breaks(model):
    populate_basic_data(model)

    # no parent
    model.recalc_ancestors(0)

    # parent with empty children
    model.parent_child_map = {0: []}
    model.recalc_ancestors(1)