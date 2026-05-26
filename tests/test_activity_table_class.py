import pytest
import uuid

from PyQt5.QtCore import Qt, QDateTime, QModelIndex
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import QApplication

# import your model here
from project_manager import ActivityTableModel
# from models import ActivityTableModel

# days_between must also be importable
from models import days_between


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
    Helper to populate model with 9 rows:
    act id 1, 4 = parent
    act id 2, 3, 5, 6, 7, 8, 9 = children
        Parent 1 has children 2 and 3
        Parent 2 has children 5, 7
            child 5 has children 6
            child 7 has children 8, 9
    """
    model._data = [
        ["p1", "1", "", "Parent 1", "", QDateTime.fromString("2024-01-01 08:00", "yyyy-MM-dd HH:mm"), "2024-01-01 08:00", "0", "", "", "", "", ""],
        ["c1", "2", "", "Child 1", "", QDateTime.fromString("2024-01-01 08:00", "yyyy-MM-dd HH:mm"),
         "2024-01-03 08:00", "2", "", "", "", "", ""],
        ["c2", "3", "", "Child 2", "c1", QDateTime.fromString("2024-01-05 08:00", "yyyy-MM-dd HH:mm"),
         "2024-01-10 08:00", "5", "", "", "", "", ""],
        ["p2", "4", "", "Parent 2", "p1", QDateTime.fromString("2024-01-01 08:00", "yyyy-MM-dd HH:mm"), "2024-01-01 08:00", "0", "", "", "", "", ""],
        ["c01", "5", "", "Child 1 of Parent 2", "", QDateTime.fromString("2024-01-01 08:00", "yyyy-MM-dd HH:mm"), "2024-01-01 08:00", "0", "", "", "", "", ""],
        ["c12", "6", "", "Child 2.1.1", "c2", QDateTime.fromString("2024-01-05 08:00", "yyyy-MM-dd HH:mm"),
         "2024-01-09 08:00", "4", "", "", "", "", ""],
        ["c02", "7", "", "Child 2 of Parent 2", "", QDateTime.fromString("2024-01-01 08:00", "yyyy-MM-dd HH:mm"), "2024-01-01 08:00", "0", "", "", "", "", ""],
        ["c21", "8", "", "Child 2.2.1", "c12", QDateTime.fromString("2024-01-01 08:00", "yyyy-MM-dd HH:mm"),
         "2024-01-07 08:00", "6", "", "", "", "", ""],
        ["c22", "9", "", "Child 2.2.2", "c21", QDateTime.fromString("2024-01-05 08:00", "yyyy-MM-dd HH:mm"),
         "2024-01-20 08:00", "15", "", "", "", "", ""],                  
    ]
    model.indentation_levels = [0, 1, 1, 0, 1, 2, 1, 2, 2]
    model.expanded_states = [True, True, True, True, True, True, True, True, True]
    model.parent_child_map = {0: [1, 2], 3: [4, 6], 4: [5], 6: [7, 8]}


# -------------------------------------------------------------------
# BASIC MODEL SHAPE
# -------------------------------------------------------------------

def test_row_and_column_count(model):
    assert len(model.headers) == 13
    assert model.headers == [
            'ID', 'Activity No', 'WBS ID', 'Name', 'Predecessor', 'Start Date', 'End Date', 'Duration',
            'Successors', 'Early Start', 'Early Finish', 'Late Start', 'Late Finish'
        ]
    assert model.rowCount() == 0
    assert model.columnCount() == len(model.headers)

    populate_basic_data(model)
    assert model.rowCount() == 9
    assert model.columnCount() == len(model.headers)


def test_insert_and_remove_rows(model):
    populate_basic_data(model)
    assert model.rowCount() == 9
    assert model.insertRows(2, 2) is True
    assert model.rowCount() == 11
    assert model._data[0][0] == "p1"
    assert model._data[1][0] == "c1"
    assert len(model._data[2][0]) > 0  # new empty row with new UUID
    assert len(model._data[3][0]) > 0  # new empty row with new UUID
    assert model._data[4][0] == "c2"
    assert model._data[8][0] == "c02"
    assert model._data[9][0] == "c21"
    assert model._data[10][0] == "c22"

    assert model.removeRows(9, 1) is True
    assert model.rowCount() == 10
    assert model._data[8][0] == "c02"
    assert model._data[9][0] == "c22"


# -------------------------------------------------------------------
# DATA()
# -------------------------------------------------------------------

def test_data_invalid_index(model):
    assert model.data(QModelIndex()) is None

def test_parent_row_has_green_background(model):
    populate_basic_data(model)

    index = model.index(0, 0)
    result = model.data(index, Qt.BackgroundRole)
    assert isinstance(result, QBrush)
    assert result.color() == QColor("#4e9745")

    index = model.index(3, 0)
    result = model.data(index, Qt.BackgroundRole)
    assert isinstance(result, QBrush)
    assert result.color() == QColor("#4e9745")

    index = model.index(4, 0)
    result = model.data(index, Qt.BackgroundRole)
    assert isinstance(result, QBrush)
    assert result.color() == QColor("#4e9745")

    index = model.index(6, 0)
    result = model.data(index, Qt.BackgroundRole)
    assert isinstance(result, QBrush)
    assert result.color() == QColor("#4e9745")


def test_child_row_has_no_background(model):
    populate_basic_data(model)

    index = model.index(1, 0)   # row 1 is a child, not a parent
    result = model.data(index, Qt.BackgroundRole)
    assert isinstance(result, QBrush)
    assert result.color() == QColor("#b9bd76")

    index = model.index(2, 0)   # row 2 is a child, not a parent
    result = model.data(index, Qt.BackgroundRole)
    assert isinstance(result, QBrush)
    assert result.color() == QColor("#b9bd76")

    index = model.index(5, 0)   # row 5 is a child, not a parent
    result = model.data(index, Qt.BackgroundRole)
    assert isinstance(result, QBrush)
    assert result.color() == QColor("#b9bd76")

    index = model.index(7, 0)   # row 7 is a child, not a parent
    result = model.data(index, Qt.BackgroundRole)
    assert isinstance(result, QBrush)
    assert result.color() == QColor("#b9bd76")
    
    index = model.index(8, 0)   # row 8 is a child, not a parent
    result = model.data(index, Qt.BackgroundRole)
    assert isinstance(result, QBrush)
    assert result.color() == QColor("#b9bd76")


def test_Name_Indentation(model):
    populate_basic_data(model)

    index = model.index(0, 3)   # row 0 is not indented
    result = model.data(index, Qt.DisplayRole)
    assert result == "Parent 1"

    index = model.index(1, 3)   # row 1 is a child, so 1 indentation level = 2 spaces
    result = model.data(index, Qt.DisplayRole)
    assert result == "  Child 1"

    index = model.index(5, 3)   # row 5 is a child, so 2 indentation levels = 4 spaces
    result = model.data(index, Qt.DisplayRole)
    assert result == "    Child 2.1.1"


def test_date_formatting(model):
    populate_basic_data(model)

    index = model.index(1, 5)   # Start Date column
    result = model.data(index, Qt.DisplayRole)
    assert result == "2024-01-01 08:00"

    index = model.index(1, 6)   # End Date column
    result = model.data(index, Qt.DisplayRole)
    assert result == "2024-01-03 08:00"

    index = model.index(2, 6)   # End Date column
    result = model.data(index, Qt.DisplayRole)
    assert result == "2024-01-10 08:00"


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
    assert brush.color() == QColor("#4e9745")

    # Non-parent background
    brush = model.data(model.index(1, 0), Qt.BackgroundRole)
    assert isinstance(brush, QBrush)
    assert brush.color() == QColor("#b9bd76")


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

    original_dt = model._data[1][5]
    assert model.setData(QModelIndex(), "x") is False           # Qt.EditRole is default, but index is invalid
    assert model.setData(index, "x", Qt.DisplayRole) is False
    assert model.setData(index_dt, "x") is False                # "x" is not a valid QDateTime, so it should reject the edit and keep the original QDateTime
    assert model._data[1][5] == original_dt                     # QDateTime should remain unchanged

    index_dt = model.index(1, 6)    # End Date column is read-only
    original_dt = model._data[1][6]
    assert model.setData(index_dt, dt, Qt.EditRole) is True     # should not allow editing End Date directly, but that is handled in flags, not setData, 
                                                                # so it will still accept the data but not update the model
    assert model.setData(index_dt, "x") is True                 # only column 5 is validated as a date, so column 6 will accept any string, 
                                                                # but it should not update the model because it's read-only according to flags
    assert model._data[1][6] == "x"
    assert model.setData(index_dt, dt.toString("yyyy-MM-dd HH:mm"), Qt.EditRole) is True
    assert model._data[1][6] == dt.toString("yyyy-MM-dd HH:mm")


# -------------------------------------------------------------------
# headerData
# -------------------------------------------------------------------

def test_header_data(model):
    assert model.headerData(0, Qt.Horizontal) == "ID"
    assert model.headerData(0, Qt.Vertical) is None
    assert model.headerData(1, Qt.Horizontal) == 'Activity No'
    assert model.headerData(2, Qt.Horizontal) == 'WBS ID'
    assert model.headerData(3, Qt.Horizontal) == 'Name'
    assert model.headerData(4, Qt.Horizontal) == 'Predecessor'


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
    assert model.flags(model.index(0, 6)) != Qt.ItemIsEditable  # End is read-only
    assert model.flags(model.index(1, 8)) != Qt.ItemIsEditable  # Succerssors is read-only
    assert model.flags(model.index(2, 9)) != Qt.ItemIsEditable  # CPM field: ES is read-only
    assert model.flags(model.index(3, 10)) != Qt.ItemIsEditable # CPM field: EF is read-only
    assert model.flags(model.index(4, 11)) != Qt.ItemIsEditable # CPM field: LS is read-only
    assert model.flags(model.index(5, 12)) != Qt.ItemIsEditable # CPM field: LF is read-only

    # Duration of parent is read-only
    assert model.flags(model.index(0, 7)) != Qt.ItemIsEditable  # root parent
    assert model.flags(model.index(3, 7)) != Qt.ItemIsEditable  # second parent on top level
    assert model.flags(model.index(4, 7)) != Qt.ItemIsEditable  # both child and parent
    assert model.flags(model.index(6, 7)) != Qt.ItemIsEditable  # last parent

    # Duration of children is not read-only
    assert model.flags(model.index(1, 7)) == Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable  # first child
    assert model.flags(model.index(5, 7)) == Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable  # second level child
    assert model.flags(model.index(7, 7)) == Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable  # first child of last parent
    assert model.flags(model.index(8, 7)) == Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable  # last child

    # Editable column
    assert model.flags(model.index(1, 3)) == Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
    assert model.flags(model.index(2, 4)) == Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
    assert model.flags(model.index(3, 5)) == Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable


# -------------------------------------------------------------------
# getters/setters
# -------------------------------------------------------------------

def test_get_and_set_all_data(model):
    data = [["1"] * len(model.headers)]
    model.set_all_data(data)
    assert model.get_all_data() == data

    populate_basic_data(model)
    result = model.get_all_data()
    assert result[0] == ['p1', '1', '', 'Parent 1', '', QDateTime.fromString("2024-01-01 08:00", "yyyy-MM-dd HH:mm"), '2024-01-01 08:00', '0', '', '', '', '', '']
    assert result[1] == ['c1', '2', '', 'Child 1', '', QDateTime.fromString("2024-01-01 08:00", "yyyy-MM-dd HH:mm"), '2024-01-03 08:00', '2', '', '', '', '', '']
    assert result[2] == ['c2', '3', '', 'Child 2', 'c1', QDateTime.fromString("2024-01-05 08:00", "yyyy-MM-dd HH:mm"), '2024-01-10 08:00', '5', '', '', '', '', '']
    assert result[3] == ['p2', '4', '', 'Parent 2', 'p1', QDateTime.fromString("2024-01-01 08:00", "yyyy-MM-dd HH:mm"), '2024-01-01 08:00', '0', '', '', '', '', '']
    assert result[4] == ['c01', '5', '', 'Child 1 of Parent 2', '', QDateTime.fromString("2024-01-01 08:00", "yyyy-MM-dd HH:mm"), '2024-01-01 08:00', '0', '', '', '', '', '']
    assert result[5] == ['c12', '6', '', 'Child 2.1.1', 'c2', QDateTime.fromString("2024-01-05 08:00", "yyyy-MM-dd HH:mm"), '2024-01-09 08:00', '4', '', '', '', '', '']
    assert result[6] == ['c02', '7', '', 'Child 2 of Parent 2', '', QDateTime.fromString("2024-01-01 08:00", "yyyy-MM-dd HH:mm"), '2024-01-01 08:00', '0', '', '', '', '', '']
    assert result[7] == ['c21', '8', '', 'Child 2.2.1', 'c12', QDateTime.fromString("2024-01-01 08:00", "yyyy-MM-dd HH:mm"), '2024-01-07 08:00', '6', '', '', '', '', '']
    assert result[8] == ['c22', '9', '', 'Child 2.2.2', 'c21', QDateTime.fromString("2024-01-05 08:00", "yyyy-MM-dd HH:mm"), '2024-01-20 08:00', '15', '', '', '', '', '']

    print(result)


# -------------------------------------------------------------------
# recalc_parent_activities
# -------------------------------------------------------------------

def test_recalc_parent_activities(model):
    populate_basic_data(model)
    model.recalc_parent_activities()

    parent = model._data[0]
    assert isinstance(parent[5], QDateTime)
    assert parent[5].toString("yyyy-MM-dd HH:mm") == "2024-01-01 08:00"
    assert parent[6] == "2024-01-10 08:00"
    assert float(parent[7]) == 9.0

    parent = model._data[3]
    assert isinstance(parent[5], QDateTime)
    assert parent[5].toString("yyyy-MM-dd HH:mm") == "2024-01-01 08:00"
    assert parent[6] == "2024-01-20 08:00"
    assert float(parent[7]) == 19.0 

    parent = model._data[4]
    assert isinstance(parent[5], QDateTime)
    assert parent[5].toString("yyyy-MM-dd HH:mm") == "2024-01-05 08:00"
    assert parent[6] == "2024-01-09 08:00"
    assert float(parent[7]) == 4.0

    parent = model._data[6]
    assert isinstance(parent[5], QDateTime)
    assert parent[5].toString("yyyy-MM-dd HH:mm") == "2024-01-01 08:00"
    assert parent[6] == "2024-01-20 08:00"
    assert float(parent[7]) == 19.0 


# -------------------------------------------------------------------
# recalculate_activity_numbers + WBS
# -------------------------------------------------------------------

def test_recalculate_activity_numbers_and_wbs(model):
    populate_basic_data(model)
    model.recalculate_activity_numbers()

    # Activity No
    assert model._data[0][1] == "1"
    assert model._data[1][1] == "2"
    assert model._data[7][1] == "8"
    assert model._data[8][1] == "9"

    # WBS
    assert model._data[0][2] == "1"
    assert model._data[1][2] == "1.1"
    assert model._data[2][2] == "1.2"
    assert model._data[3][2] == "2"
    assert model._data[4][2] == "2.1"
    assert model._data[5][2] == "2.1.1"
    assert model._data[6][2] == "2.2"
    assert model._data[7][2] == "2.2.1"
    assert model._data[8][2] == "2.2.2"


# -------------------------------------------------------------------
# get_parent_row
# -------------------------------------------------------------------

def test_get_parent_row(model):
    populate_basic_data(model)

    assert model.get_parent_row(1) == 0
    assert model.get_parent_row(2) == 0
    assert model.get_parent_row(4) == 3
    assert model.get_parent_row(6) == 3
    assert model.get_parent_row(5) == 4
    assert model.get_parent_row(7) == 6
    assert model.get_parent_row(8) == 6
    assert model.get_parent_row(0) is None
    assert model.get_parent_row(3) is None
    assert model.get_parent_row(999) is None


# -------------------------------------------------------------------
# recalc_ancestors
# -------------------------------------------------------------------

def test_recalc_ancestors(model):
    populate_basic_data(model)

    # Trigger recalculation from child
    model.recalc_ancestors(2)

    parent = model._data[0]
    assert parent[1] == "1"  # Activity No should not change
    assert parent[2] == ""  # WBS should not change
    assert isinstance(parent[5], QDateTime)
    assert parent[5].toString("yyyy-MM-dd HH:mm") == "2024-01-01 08:00"
    assert parent[6].startswith("2024-01-10")
    assert isinstance(parent[7], (int, float))
    assert float(parent[7]) == 9.0

    # Trigger recalculation again
    model.recalc_ancestors(5)

    parent = model._data[4]
    assert parent[1] == "5"  # Activity No should not change
    assert parent[2] == ""  # WBS should not change
    assert isinstance(parent[5], QDateTime)
    assert parent[5].toString("yyyy-MM-dd HH:mm") == "2024-01-05 08:00"
    assert parent[6].startswith("2024-01-09")
    assert isinstance(parent[7], (int, float))
    assert float(parent[7]) == 4.0


def test_recalc_ancestors_breaks(model):
    populate_basic_data(model)

    # no parent
    model.recalc_ancestors(0)

    # parent with empty children
    model.parent_child_map = {0: []}
    model.recalc_ancestors(1)