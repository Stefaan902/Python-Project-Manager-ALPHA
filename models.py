"""
models.py — Table model layer for the Project Manager application.

Hierarchy
─────────────────────────────────────────────────────────────────
QAbstractTableModel  (Qt)
    └── BaseTableModel                      shared Qt boilerplate + hierarchy support
            ├── ActivityTableModel          activities, CPM columns, WBS scheduling
            ├── ResourceTableModel          human / physical / financial resources
            └── BillOfQuantityTableModel    quantity take-off with auto-calc
RiskTableModel                              thin model (no hierarchy); derives from
                                            BaseTableModel for rowCount/columnCount/
                                            headerData only
IntegrationTableModel                       composite read-only view; no _data of its
                                            own, derives directly from
                                            QAbstractTableModel
─────────────────────────────────────────────────────────────────

Usage in maincode.py
─────────────────────────────────────────────────────────────────
Replace the five class definitions with a single import:

    from models import (
        ActivityTableModel,
        ResourceTableModel,
        RiskTableModel,
        BillOfQuantityTableModel,
        IntegrationTableModel,
    )
─────────────────────────────────────────────────────────────────
"""

import uuid

from PyQt5.QtCore import Qt, QDateTime, QAbstractTableModel, QModelIndex
from PyQt5.QtWidgets import QMessageBox


# ═══════════════════════════════════════════════════════════════════════════════
# BaseTableModel
# ═══════════════════════════════════════════════════════════════════════════════

class BaseTableModel(QAbstractTableModel):
    """
    Shared foundation for every table model in the application.

    Provides out-of-the-box:
      • rowCount / columnCount  backed by self._data and self.headers
      • headerData              horizontal labels from self.headers
      • data                    DisplayRole / EditRole with optional
                                per-subclass overrides via _format_display()
      • setData                 writes to _data, emits dataChanged
      • flags                   fully editable by default; subclasses
                                override _readonly_columns() to restrict
      • insertRows / removeRows with hierarchy bookkeeping
      • get_all_data / set_all_data  convenience helpers
      • Hierarchy support:
            self.indentation_levels  list[int]  — visual indent depth
            self.expanded_states     list[bool] — collapsed/expanded state
            self.parent_child_map    dict[int, list[int]]
            is_group() / get_indent_level() / toggle_group() /
            update_visible_rows()
    """

    # ── construction ─────────────────────────────────────────────────────────

    def __init__(self, parent=None):
        super().__init__(parent)
        self.headers: list[str] = []
        self._data:   list[list] = []

        # Hierarchy state — not every subclass uses all three, but keeping
        # them here avoids repetition across Activity and Resource models.
        self.indentation_levels: list[int]  = []
        self.expanded_states:    list[bool] = []
        self.parent_child_map:   dict[int, list[int]] = {}

    # ── mandatory Qt overrides ────────────────────────────────────────────────

    def rowCount(self, parent=None) -> int:
        return len(self._data)

    def columnCount(self, parent=None) -> int:
        return len(self.headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row    = index.row()
        column = index.column()
        value  = self._data[row][column]

        if role == Qt.DisplayRole:
            return self._format_display(row, column, value)
        if role == Qt.EditRole:
            return self._format_edit(row, column, value)
        return None

    def setData(self, index, value, role=Qt.EditRole) -> bool:
        if not index.isValid() or role != Qt.EditRole:
            return False

        row    = index.row()
        column = index.column()
        self._data[row][column] = value
        self.dataChanged.emit(index, index, [role])
        self._on_cell_changed(row, column)
        return True

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        if index.column() in self._readonly_columns():
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    # ── row insert / remove ───────────────────────────────────────────────────

    def insertRows(self, position, rows, parent=QModelIndex()) -> bool:
        self.beginInsertRows(parent, position, position + rows - 1)
        for _ in range(rows):
            new_row = self._make_empty_row()
            self._data.insert(position, new_row)
            self._insert_hierarchy_state(position)
        self.endInsertRows()
        return True

    def removeRows(self, position, rows, parent=QModelIndex()) -> bool:
        self.beginRemoveRows(parent, position, position + rows - 1)
        del self._data[position:position + rows]
        self._remove_hierarchy_state(position, rows)
        self.endRemoveRows()
        return True

    # ── convenience helpers ───────────────────────────────────────────────────

    def get_all_data(self) -> list:
        return self._data

    def set_all_data(self, data: list) -> None:
        self.beginResetModel()
        self._data = data
        self.endResetModel()

    # ── hierarchy helpers ─────────────────────────────────────────────────────

    def is_group(self, row: int) -> bool:
        """Return True if *row* has at least one child."""
        return row in self.parent_child_map

    def get_indent_level(self, row: int) -> int:
        if row < len(self.indentation_levels):
            return self.indentation_levels[row]
        return 0

    def toggle_group(self, row: int) -> None:
        if row in self.parent_child_map:
            self.expanded_states[row] = not self.expanded_states[row]
            self.update_visible_rows()

    def update_visible_rows(self) -> set:
        """
        Return the set of row indices that should be visible given current
        expanded/collapsed states.  The view is responsible for acting on
        this — the model itself does not hide rows.
        """
        visible = set()
        for row in range(len(self._data)):
            cur = row
            show = True
            while True:
                parent_row = next(
                    (p for p, children in self.parent_child_map.items()
                     if cur in children),
                    None
                )
                if parent_row is None:
                    break
                if not self.expanded_states[parent_row]:
                    show = False
                    break
                cur = parent_row
            if show:
                visible.add(row)
        return visible

    # ── protected extension points ────────────────────────────────────────────

    def _readonly_columns(self) -> set:
        """
        Return the set of column indices that must be read-only.
        Override in subclasses; default = column 0 only (UUID / primary key).
        """
        return {0}

    def _format_display(self, row: int, column: int, value) -> str:
        """
        Convert a cell value to its display string.
        Override to add indentation, datetime formatting, etc.
        Default: str(value).
        """
        return str(value) if value is not None else ""

    def _format_edit(self, row: int, column: int, value) -> str:
        """
        Convert a cell value for an editor widget.
        Default: same as _format_display.
        """
        return self._format_display(row, column, value)

    def _make_empty_row(self) -> list:
        """
        Return a new blank row list.
        Override when a column needs a non-empty default (e.g. UUID, QDateTime).
        """
        return [""] * len(self.headers)

    def _insert_hierarchy_state(self, position: int) -> None:
        """Extend hierarchy bookkeeping lists after a row insert."""
        if position > len(self.indentation_levels):
            self.indentation_levels.extend(
                [0] * (position - len(self.indentation_levels))
            )
        self.indentation_levels.insert(position, 0)

        if position > len(self.expanded_states):
            self.expanded_states.extend(
                [True] * (position - len(self.expanded_states))
            )
        self.expanded_states.insert(position, True)

    def _remove_hierarchy_state(self, position: int, rows: int) -> None:
        """
        Shrink hierarchy bookkeeping lists and remap parent_child_map
        after a row removal.
        """
        del self.indentation_levels[position:position + rows]
        del self.expanded_states[position:position + rows]

        new_map: dict[int, list[int]] = {}
        for parent_row, children in self.parent_child_map.items():
            # Drop parents that were deleted
            if position <= parent_row < position + rows:
                continue
            new_parent = parent_row - rows if parent_row >= position + rows else parent_row
            new_children = []
            for child in children:
                if position <= child < position + rows:
                    continue   # child was deleted
                new_child = child - rows if child >= position + rows else child
                new_children.append(new_child)
            if new_children:
                new_map[new_parent] = new_children
        self.parent_child_map = new_map

    def _on_cell_changed(self, row: int, column: int) -> None:
        """
        Hook called by setData after a cell is written.
        Override to trigger derived-value recalculation.
        """


# ═══════════════════════════════════════════════════════════════════════════════
# ActivityTableModel
# ═══════════════════════════════════════════════════════════════════════════════

class ActivityTableModel(BaseTableModel):
    """
    Stores the activity (task) list.

    Column layout:
      [0]  UUID           hidden; used internally as stable activity ID
      [1]  Name
      [2]  Predecessor    semicolon-separated UUIDs of predecessor activities
      [3]  Start Date     stored as QDateTime
      [4]  End Date       stored as formatted string "yyyy-MM-dd HH:mm"
      [5]  Duration       string representation of number of days
      [6]  Successors     auto-populated by calculate_cpm(); read-only
      [7]  Early Start    float; written by calculate_cpm()
      [8]  Early Finish   float; written by calculate_cpm()
      [9]  Late Start     float; written by calculate_cpm()
      [10] Late Finish    float; written by calculate_cpm()
    """

    # Column index constants — use these everywhere instead of bare integers
    # so that adding/renaming columns in one place is sufficient.
    COL_UUID      = 0
    COL_NAME      = 1
    COL_PRED      = 2
    COL_START     = 3
    COL_END       = 4
    COL_DUR       = 5
    COL_SUCC      = 6
    COL_ES        = 7
    COL_EF        = 8
    COL_LS        = 9
    COL_LF        = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.headers = [
            'ID', 'Name', 'Predecessor', 'Start Date', 'End Date', 'Duration',
            'Successors', 'Early Start', 'Early Finish', 'Late Start', 'Late Finish',
        ]

    # ── display / edit formatting ─────────────────────────────────────────────

    def _format_display(self, row: int, column: int, value) -> str:
        if column == self.COL_NAME:
            indent = self.indentation_levels[row] if row < len(self.indentation_levels) else 0
            return "  " * indent + str(value)
        if column == self.COL_START and isinstance(value, QDateTime):
            return value.toString("yyyy-MM-dd HH:mm")
        return str(value) if value is not None else ""

    def _format_edit(self, row: int, column: int, value) -> str:
        if column == self.COL_START and isinstance(value, QDateTime):
            return value.toString("yyyy-MM-dd HH:mm")
        return str(value) if value is not None else ""

    # ── read-only columns ─────────────────────────────────────────────────────

    def _readonly_columns(self) -> set:
        return {
            self.COL_UUID,
            self.COL_END,   # computed from Start + Duration
            self.COL_SUCC,  # computed by calculate_cpm()
            self.COL_ES, self.COL_EF, self.COL_LS, self.COL_LF,
        }

    # ── empty row factory ─────────────────────────────────────────────────────

    def _make_empty_row(self) -> list:
        row = [""] * len(self.headers)
        row[self.COL_UUID]  = str(uuid.uuid4())
        row[self.COL_START] = QDateTime.currentDateTime()
        return row

    # ── derived-value recalculation hook ──────────────────────────────────────

    def _on_cell_changed(self, row: int, column: int) -> None:
        """Trigger parent aggregation whenever a child's data changes."""
        if self.is_group(row):
            self.recalc_parent_activities()

    # ── business logic ────────────────────────────────────────────────────────

    def recalc_parent_activities(self) -> None:
        """
        For every parent row in parent_child_map:
          • Start Date = min(child start dates)
          • End Date   = max(child end dates)
          • Duration   = sum(child durations)
        """
        for parent_row, children in self.parent_child_map.items():
            if not children:
                continue

            child_starts = []
            child_ends   = []
            total_dur    = 0.0

            for child_row in children:
                child = self._data[child_row]

                start = child[self.COL_START]
                if isinstance(start, QDateTime):
                    child_starts.append(start)

                end = QDateTime.fromString(
                    str(child[self.COL_END]), "yyyy-MM-dd HH:mm"
                )
                if end.isValid():
                    child_ends.append(end)

                try:
                    total_dur += float(child[self.COL_DUR])
                except (ValueError, TypeError):
                    pass

            if child_starts and child_ends:
                self._data[parent_row][self.COL_START] = min(child_starts)
                self._data[parent_row][self.COL_END]   = max(child_ends).toString(
                    "yyyy-MM-dd HH:mm"
                )
                self._data[parent_row][self.COL_DUR]   = total_dur

                self.dataChanged.emit(
                    self.index(parent_row, self.COL_START),
                    self.index(parent_row, self.COL_DUR),
                    [Qt.DisplayRole],
                )


# ═══════════════════════════════════════════════════════════════════════════════
# ResourceTableModel
# ═══════════════════════════════════════════════════════════════════════════════

class ResourceTableModel(BaseTableModel):
    """
    Stores the resource registry.

    Column layout:
      [0]  Name of Resource
      [1]  Type of Resource     combo-box delegate in the view
      [2]  Email
      [3]  Phone
      [4]  Standard Rate per Day
      [5]  Overtime Rate per Day
      [6]  Cost per Use
      [7]  Assigned Activity

    All columns are user-editable.  When a child resource is edited,
    the parent's rate columns (4–6) are recalculated as column sums.
    """

    COL_NAME      = 0
    COL_TYPE      = 1
    COL_EMAIL     = 2
    COL_PHONE     = 3
    COL_STD_RATE  = 4
    COL_OT_RATE   = 5
    COL_CPU       = 6
    COL_ACTIVITY  = 7

    def __init__(self, activity_model, parent=None):
        super().__init__(parent)
        self.activity_model = activity_model
        self.headers = [
            'Name of Resource', 'Type of Resource', 'Email', 'Phone',
            'Standard Rate per Day', 'Overtime Rate per Day', 'Cost per Use',
            'Assigned Activity',
        ]

    # ── display / edit formatting ─────────────────────────────────────────────

    def _format_display(self, row: int, column: int, value) -> str:
        if column == self.COL_NAME:
            indent = self.indentation_levels[row] if row < len(self.indentation_levels) else 0
            return "  " * indent + str(value)
        return str(value) if value is not None else ""

    # ── read-only columns ─────────────────────────────────────────────────────

    def _readonly_columns(self) -> set:
        return set()  # all columns are user-editable

    # ── derived-value recalculation hook ──────────────────────────────────────

    def _on_cell_changed(self, row: int, column: int) -> None:
        """Recalculate parent resource totals whenever any child changes."""
        self.recalc_parent_resources()

    # ── business logic ────────────────────────────────────────────────────────

    def recalc_parent_resources(self) -> None:
        """
        For every parent row in parent_child_map, set the rate columns
        to the sum of the corresponding child columns.
        """
        for parent_row, children in self.parent_child_map.items():
            if not children:
                continue

            totals = {
                self.COL_STD_RATE: 0.0,
                self.COL_OT_RATE:  0.0,
                self.COL_CPU:      0.0,
            }

            for child_row in children:
                for col in totals:
                    try:
                        totals[col] += float(self._data[child_row][col] or 0)
                    except (ValueError, TypeError):
                        pass

            for col, total in totals.items():
                self._data[parent_row][col] = str(total)

            self.dataChanged.emit(
                self.index(parent_row, self.COL_STD_RATE),
                self.index(parent_row, self.COL_CPU),
                [Qt.DisplayRole],
            )


# ═══════════════════════════════════════════════════════════════════════════════
# RiskTableModel
# ═══════════════════════════════════════════════════════════════════════════════

class RiskTableModel(BaseTableModel):
    """
    Risk register — one row per activity.

    Column layout:
      [0]  ID              UUID from ActivityTableModel (read-only)
      [1]  Name            mirrored from ActivityTableModel (read-only)
      [2]  Category        user-editable free text
      [3]  Probability     integer 1–5 (user-editable)
      [4]  Impact          integer 1–5 (user-editable)
      [5]  Rating          computed = Probability × Impact (read-only)

    No hierarchy support needed; indentation/parent-child lists are
    inherited but remain empty.
    """

    COL_ID          = 0
    COL_NAME        = 1
    COL_CATEGORY    = 2
    COL_PROBABILITY = 3
    COL_IMPACT      = 4
    COL_RATING      = 5

    def __init__(self, activity_model, parent=None):
        super().__init__(parent)
        self.activity_model = activity_model
        self.headers = [
            "ID", "Name of Activity", "Category of Risk",
            "Probability of Risk", "Impact on Project", "Rating of Risk",
        ]
        self._data = self._build_from_activity_model()

    # ── read-only columns ─────────────────────────────────────────────────────

    def _readonly_columns(self) -> set:
        return {self.COL_ID, self.COL_NAME, self.COL_RATING}

    # ── custom setData: validate probability / impact, auto-compute rating ────

    def setData(self, index, value, role=Qt.EditRole) -> bool:
        if not index.isValid() or role != Qt.EditRole:
            return False

        row    = index.row()
        column = index.column()

        if column in (self.COL_PROBABILITY, self.COL_IMPACT):
            try:
                numeric = int(value)
                if not (1 <= numeric <= 5):
                    raise ValueError("Value must be between 1 and 5")
                self._data[row][column] = numeric
                self._data[row][self.COL_RATING] = (
                    self._data[row][self.COL_PROBABILITY]
                    * self._data[row][self.COL_IMPACT]
                )
                self.dataChanged.emit(index, index, [role])
                self.dataChanged.emit(
                    self.index(row, self.COL_RATING),
                    self.index(row, self.COL_RATING),
                )
                return True
            except ValueError as exc:
                QMessageBox.warning(None, "Invalid Input", str(exc))
                return False

        if column == self.COL_CATEGORY:
            self._data[row][column] = value
            self.dataChanged.emit(index, index, [role])
            return True

        return False

    # ── display formatting ────────────────────────────────────────────────────

    def _format_display(self, row: int, column: int, value) -> str:
        return str(value) if value is not None else ""

    # ── sync helpers ──────────────────────────────────────────────────────────

    def _build_from_activity_model(self) -> list:
        return [
            [
                activity[0],   # ID
                activity[1],   # Name of Activity
                "",            # Category — default blank
                1,             # Probability — default 1
                1,             # Impact — default 1
                1,             # Rating = 1 × 1
            ]
            for activity in self.activity_model._data
        ]

    def refresh_from_activity_model(self) -> None:
        """Rebuild the risk list from the current activity model."""
        self.beginResetModel()
        self._data = self._build_from_activity_model()
        self.endResetModel()


# ═══════════════════════════════════════════════════════════════════════════════
# BillOfQuantityTableModel
# ═══════════════════════════════════════════════════════════════════════════════

class BillOfQuantityTableModel(BaseTableModel):
    """
    Bill of Quantities — quantity take-off table.

    Column layout:
      [0]  Number of Work          user-editable
      [1]  Type of Work            user-editable
      [2]  Unit of Measurement     user-editable
      [3]  Dimension 1             user-editable numeric input
      [4]  Dimension 2             user-editable numeric input
      [5]  Dimension 3             user-editable numeric input
      [6]  Sum                     computed = D1 × D2 × D3   (read-only)
      [7]  Cost per Unit           user-editable numeric input
      [8]  Total Cost              computed = Sum × CPU       (read-only)
      [9]  NOTES                   user-editable free text

    Vertical header shows 1-based row numbers (overrides BaseTableModel default).
    """

    COL_NUMBER = 0
    COL_TYPE   = 1
    COL_UNIT   = 2
    COL_DIM1   = 3
    COL_DIM2   = 4
    COL_DIM3   = 5
    COL_SUM    = 6
    COL_CPU    = 7
    COL_TOTAL  = 8
    COL_NOTES  = 9

    _DIMENSION_COLS = (COL_DIM1, COL_DIM2, COL_DIM3)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.headers = [
            "Number of Work", "Type of Work", "Unit of Measurement",
            "Dimension 1", "Dimension 2", "Dimension 3", "Sum",
            "Cost per Unit", "Total Cost", "NOTES",
        ]

    # ── read-only columns ─────────────────────────────────────────────────────

    def _readonly_columns(self) -> set:
        return {self.COL_SUM, self.COL_TOTAL}

    # ── vertical header: 1-based row numbers ─────────────────────────────────

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Vertical:
            return str(section + 1)
        return super().headerData(section, orientation, role)

    # ── derived-value recalculation hook ──────────────────────────────────────

    def _on_cell_changed(self, row: int, column: int) -> None:
        if column in (*self._DIMENSION_COLS, self.COL_CPU):
            self.recalculate_row(row)
            self.dataChanged.emit(
                self.index(row, self.COL_SUM),
                self.index(row, self.COL_TOTAL),
                [Qt.DisplayRole],
            )

    # ── business logic ────────────────────────────────────────────────────────

    def recalculate_row(self, row: int) -> None:
        """
        Recompute Sum (col 6) and Total Cost (col 8) for the given row.

        Sum  = product of all dimension columns that contain a valid float.
               If no dimension is numeric, Sum is set to "" (not 0).
        Total = Sum × Cost per Unit.
               If either operand is non-numeric, Total is set to "".
        """
        dims = []
        for col in self._DIMENSION_COLS:
            try:
                dims.append(float(self._data[row][col]))
            except (ValueError, TypeError):
                pass

        if dims:
            product = 1.0
            for d in dims:
                product *= d
            sum_val = product
        else:
            sum_val = ""

        self._data[row][self.COL_SUM] = sum_val

        try:
            cpu = float(self._data[row][self.COL_CPU])
            total = cpu * float(sum_val) if sum_val != "" else ""
        except (ValueError, TypeError):
            total = ""

        self._data[row][self.COL_TOTAL] = total


# ═══════════════════════════════════════════════════════════════════════════════
# IntegrationTableModel
# ═══════════════════════════════════════════════════════════════════════════════

class IntegrationTableModel(QAbstractTableModel):
    """
    Read-only composite view that links activities to resources, risks,
    and BOQ items.

    This model does not own a _data list.  It derives its rows directly
    from activity_model and maintains a relationships dict for assignments.

    Column layout:
      [0]  Activity ID      UUID (from ActivityTableModel col 0)
      [1]  Activity Name    (from ActivityTableModel col 1)
      [2]  Duration         (from ActivityTableModel col 5)
      [3]  Start Date       (from ActivityTableModel col 3)
      [4]  End Date         (from ActivityTableModel col 4)
      [5]  Assigned Resources   comma-separated names
      [6]  Assigned Risks       comma-separated category strings
      [7]  Assigned BOQ Items   comma-separated descriptions

    IntegrationTableModel intentionally does NOT extend BaseTableModel
    because it has no _data list, no hierarchy bookkeeping, and
    completely custom row/column semantics.
    """

    # Maps relationship type → (relationship key, display column)
    _REL_TYPES = {
        "resource": ("resources", 5),
        "risk":     ("risks",     6),
        "boq":      ("boq",       7),
    }

    def __init__(self, activity_model, resource_model, risk_model, boq_model,
                 parent=None):
        super().__init__(parent)
        self.activity_model = activity_model
        self.resource_model = resource_model
        self.risk_model     = risk_model
        self.boq_model      = boq_model

        self.headers = [
            "Activity ID", "Activity Name", "Duration", "Start Date",
            "End Date", "Assigned Resources", "Assigned Risks",
            "Assigned BOQ Items",
        ]

        # {activity_uuid: {'resources': [...], 'risks': [...], 'boq': [...]}}
        self.relationships: dict = {}
        self.refresh_relationships()

        # Keep in sync with underlying models
        if self.activity_model:
            self.activity_model.dataChanged.connect(self._on_any_change)
        if self.resource_model:
            self.resource_model.dataChanged.connect(self._on_source_change)
        if self.risk_model:
            self.risk_model.dataChanged.connect(self._on_source_change)
        if self.boq_model:
            self.boq_model.dataChanged.connect(self._on_source_change)

    # ── Qt mandatory overrides ────────────────────────────────────────────────

    def rowCount(self, parent=None) -> int:
        if self.activity_model and hasattr(self.activity_model, '_data'):
            return len(self.activity_model._data)
        return 0

    def columnCount(self, parent=None) -> int:
        return len(self.headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        if not self.activity_model or not hasattr(self.activity_model, '_data'):
            return None
        if index.row() >= len(self.activity_model._data):
            return None

        row      = index.row()
        col      = index.column()
        activity = self.activity_model._data[row]

        # Columns sourced directly from ActivityTableModel
        _direct = {
            0: (0,),   # UUID
            1: (1,),   # Name
            2: (5,),   # Duration
            3: (3,),   # Start Date
            4: (4,),   # End Date
        }
        if col in _direct:
            src_col = _direct[col][0]
            val = activity[src_col] if src_col < len(activity) else ""
            if isinstance(val, QDateTime):
                return val.toString("yyyy-MM-dd HH:mm")
            return str(val) if val is not None else ""

        # Relationship columns (5, 6, 7)
        activity_id = activity[0]
        rels = self.relationships.get(activity_id, {})

        if col == 5:
            return ", ".join(
                self._resource_name(r) for r in rels.get("resources", [])
            )
        if col == 6:
            return ", ".join(
                self._risk_name(r) for r in rels.get("risks", [])
            )
        if col == 7:
            return ", ".join(
                self._boq_desc(b) for b in rels.get("boq", [])
            )

        return None

    # ── relationship management ───────────────────────────────────────────────

    def refresh_relationships(self) -> None:
        """Rebuild the relationships dict from all underlying models."""
        self.beginResetModel()
        self.relationships = {}

        if self.activity_model and hasattr(self.activity_model, '_data'):
            for activity in self.activity_model._data:
                if activity:
                    self.relationships[activity[0]] = {
                        "resources": [],
                        "risks":     [],
                        "boq":       [],
                    }

        # Mirror risk→activity assignments already stored in risk_model col 1
        if self.risk_model and hasattr(self.risk_model, '_data'):
            for risk in self.risk_model._data:
                if risk and len(risk) > 1 and risk[1]:
                    activity_id = risk[1]
                    risk_id     = risk[0]
                    if activity_id in self.relationships:
                        self.relationships[activity_id]["risks"].append(risk_id)

        self.endResetModel()

    def assign_resource_to_activity(self, activity_row: int, resource_id) -> bool:
        return self._assign(activity_row, resource_id, "resource")

    def assign_risk_to_activity(self, activity_row: int, risk_id) -> bool:
        """Assign a risk and update the risk model's back-reference."""
        if not self._assign(activity_row, risk_id, "risk"):
            return False

        activity_id = self.activity_model._data[activity_row][0]
        if self.risk_model and hasattr(self.risk_model, '_data'):
            for i, risk in enumerate(self.risk_model._data):
                if risk[0] == risk_id:
                    self.risk_model._data[i][1] = activity_id
                    self.risk_model.dataChanged.emit(
                        self.risk_model.index(i, 1),
                        self.risk_model.index(i, 1),
                    )
                    break
        return True

    def assign_boq_to_activity(self, activity_row: int, boq_id) -> bool:
        return self._assign(activity_row, boq_id, "boq")

    def remove_relationship(self, activity_row: int, item_id, rel_type: str) -> bool:
        """Remove an assignment and update back-references where applicable."""
        if not self.activity_model or activity_row >= len(self.activity_model._data):
            return False
        if rel_type not in self._REL_TYPES:
            return False

        rel_key, col = self._REL_TYPES[rel_type]
        activity_id  = self.activity_model._data[activity_row][0]
        rels         = self.relationships.get(activity_id, {})

        if item_id not in rels.get(rel_key, []):
            return False

        rels[rel_key].remove(item_id)

        # Clear back-reference in risk model
        if rel_type == "risk" and self.risk_model and hasattr(self.risk_model, '_data'):
            for i, risk in enumerate(self.risk_model._data):
                if risk[0] == item_id:
                    self.risk_model._data[i][1] = None
                    self.risk_model.dataChanged.emit(
                        self.risk_model.index(i, 1),
                        self.risk_model.index(i, 1),
                    )
                    break

        self.dataChanged.emit(
            self.index(activity_row, col),
            self.index(activity_row, col),
        )
        return True

    # ── name-lookup helpers ───────────────────────────────────────────────────

    def _resource_name(self, resource_id) -> str:
        if self.resource_model and hasattr(self.resource_model, '_data'):
            for r in self.resource_model._data:
                if r and r[0] == resource_id:
                    return r[1] if len(r) > 1 else "Unnamed Resource"
        return f"Resource {resource_id}"

    def _risk_name(self, risk_id) -> str:
        if self.risk_model and hasattr(self.risk_model, '_data'):
            for r in self.risk_model._data:
                if r and r[0] == risk_id:
                    return r[2] if len(r) > 2 else f"Risk {risk_id}"
        return f"Risk {risk_id}"

    def _boq_desc(self, boq_id) -> str:
        if self.boq_model and hasattr(self.boq_model, '_data'):
            for b in self.boq_model._data:
                if b and b[0] == boq_id:
                    return b[1] if len(b) > 1 else f"BOQ {boq_id}"
        return f"BOQ {boq_id}"

    # ── private helpers ───────────────────────────────────────────────────────

    def _assign(self, activity_row: int, item_id, rel_type: str) -> bool:
        """Generic assign helper. Returns False if already assigned."""
        if not self.activity_model or activity_row >= len(self.activity_model._data):
            return False

        rel_key, col = self._REL_TYPES[rel_type]
        activity_id  = self.activity_model._data[activity_row][0]

        rels = self.relationships.setdefault(
            activity_id, {"resources": [], "risks": [], "boq": []}
        )
        if item_id in rels[rel_key]:
            return False

        rels[rel_key].append(item_id)
        self.dataChanged.emit(
            self.index(activity_row, col),
            self.index(activity_row, col),
        )
        return True

    def _on_any_change(self, *_) -> None:
        self.layoutChanged.emit()

    def _on_source_change(self, *_) -> None:
        self.refresh_relationships()
        self.layoutChanged.emit()