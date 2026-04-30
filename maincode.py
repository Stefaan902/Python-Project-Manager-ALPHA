import sys
import plotly.graph_objects as go   
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QDateTimeEdit, QMenu, QVBoxLayout, QWidget, 
    QAction, QPushButton, QHBoxLayout, QMessageBox, QTableView, QHeaderView,
    QAbstractScrollArea, QTabWidget, QStyledItemDelegate, QComboBox, QDialog, QDialogButtonBox 
)
from PyQt5.QtWidgets import QAbstractItemView, QListWidgetItem, QListWidget
from PyQt5.QtCore import Qt, QDateTime, QAbstractTableModel, QModelIndex, QVariant, QPointF, QLineF
from PyQt5.QtGui import QPainter, QBrush, QColor, QPen, QFont, QKeySequence, QPolygonF
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGraphicsScene, QGraphicsView, QGraphicsRectItem, QGraphicsTextItem, QGraphicsLineItem
from PyQt5.QtWidgets import QLineEdit, QLabel
from PyQt5.QtWidgets import QGraphicsItem
from datetime import datetime, timedelta
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import math
import numpy as np
import networkx as nx

import json
from PyQt5.QtWidgets import QFileDialog
import uuid


class ActivityTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.headers = [
            'ID', 'Activity No', 'WBS ID', 'Name', 'Predecessor', 'Start Date', 'End Date', 'Duration',
            'Successors', 'Early Start', 'Early Finish', 'Late Start', 'Late Finish'
        ]
        self._data = []
        self.datetime_column = 5  
        self.indentation_levels = [] 
        self.expanded_states = []
        self.parent_child_map = {}
    
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
                
        row = index.row()
        column = index.column()
        value = self._data[row][column]
                
        # ✅ Background color for summary (parent) tasks
        if role == Qt.BackgroundRole:
            if row in self.parent_child_map:
                # Light blue background for summary tasks
                return QBrush(QColor("#E3F2FD"))

        if role == Qt.DisplayRole:
            if column == 3:  
                indent_level = self.indentation_levels[row] if row < len(self.indentation_levels) else 0
                return "  " * indent_level + str(value)
            elif column == 5 and isinstance(value, QDateTime):      # Start Date
                return value.toString("yyyy-MM-dd HH:mm")
            return str(value)
        elif role == Qt.EditRole:
            return str(value)
        return None
    
    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self.headers)

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False
            
        row = index.row()
        column = index.column()

        if role == Qt.EditRole:
            if column == self.datetime_column and isinstance(value, QDateTime):
                self._data[row][column] = value
            else:
                self._data[row][column] = value
            self.dataChanged.emit(index, index, [role])
            return True
            
        return False

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        
        row = index.row()
        column = index.column()

        # System / read-only columns
        if column in [0, 1, 2]:   # UUID, Activity No, WBS ID — all auto-managed
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
            
        # Make certain columns read-only
        if column in [6, 8, 9, 10, 11, 12]:  # End Date, Successors, and CPM columns (aka ES, EF, LS, LF)
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        
        # ⛔ Duration of summary (parent) tasks must be read-only
        if column == 7 and row in self.parent_child_map:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable


        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def insertRows(self, position, rows, parent=QModelIndex()):
        self.beginInsertRows(parent, position, position + rows - 1)
        for _ in range(rows):
            activity_id = str(uuid.uuid4())
            empty_row = [activity_id] + [""] * (len(self.headers) - 1)
            empty_row[5] = QDateTime.currentDateTime()
            self._data.insert(position, empty_row)
            self.indentation_levels.insert(position, 0)
            self.expanded_states.insert(position, True)
        self.endInsertRows()
        return True

    def removeRows(self, position, rows, parent=QModelIndex()):
        self.beginRemoveRows(parent, position, position + rows - 1)
        del self._data[position:position + rows]
        del self.indentation_levels[position:position + rows]
        del self.expanded_states[position:position + rows]
        self.endRemoveRows()
        return True

    def get_all_data(self):
        return self._data

    def set_all_data(self, data):
        self.beginResetModel()
        self._data = data
        self.endResetModel()

    def recalc_parent_activities(self):
        """
        Recalculate parent's start date, end date, and duration based on its subactivities.
        - Parent Start Date = minimum of child start dates (column 3, stored as QDateTime)
        - Parent End Date = maximum of child end dates (column 4, stored as string formatted as "yyyy-MM-dd HH:mm")
        - Parent Duration (column 5) = sum of children durations
        """
        from PyQt5.QtCore import QDateTime  # ensure QDateTime is imported

        for parent_row, children in self.parent_child_map.items():
            if not children:
                continue
            child_starts = []
            child_ends = []
            total_duration = 0.0

            for child_row in children:
                child_data = self._data[child_row]
                # Get child's start date (assumed stored as a QDateTime object in column 5)
                start = child_data[5]
                child_starts.append(start)
                # End date is stored as a string in column 6; convert it back to QDateTime for comparison
                end = QDateTime.fromString(child_data[6], "yyyy-MM-dd HH:mm")
                child_ends.append(end)

                # Sum up durations from column 7 (if they can be converted to float, otherwise skip)
                try:
                    child_duration = float(child_data[7])
                    total_duration += child_duration
                except (ValueError, TypeError):
                    pass

            if child_starts and child_ends:
                new_start = min(child_starts)
                new_end = max(child_ends)
                # Update parent's start date (column 3), end date (column 4) and duration (column 5)
                self._data[parent_row][5] = new_start
                self._data[parent_row][6] = new_end.toString("yyyy-MM-dd HH:mm")
                self._data[parent_row][7] = total_duration
                # Emit a dataChanged signal so the view refreshes the parent's row
                top_index = self.index(parent_row, 5)
                bottom_index = self.index(parent_row, 7)
                self.dataChanged.emit(top_index, bottom_index, [Qt.DisplayRole])
    
    def recalculate_activity_numbers(self):
        """
        Assign a sequential Activity Number (column 1) to every row.
        The number is simply the 1-based position in the visible list,
        matching what the user sees in the table.
        Also triggers WBS ID recalculation.
        """
        for row in range(len(self._data)):
            self._data[row][1] = str(row + 1)
        self.recalculate_wbs_ids()
        if self._data:
            top = self.index(0, 1)
            bottom = self.index(len(self._data) - 1, 2)
            self.dataChanged.emit(top, bottom, [Qt.DisplayRole])

    def recalculate_wbs_ids(self):
        """
        Derive a dotted WBS ID (column 2) for every row from the
        parent_child_map and indentation_levels.

        Algorithm:
        - Top-level rows (indentation == 0, no parent) get a single
            counter: 1, 2, 3, …
        - Each time a row becomes a child its counter resets within
            its parent scope: parent "2" → children "2.1", "2.2", …
        - Deeper nesting appends another segment: "2.1.1", "2.1.2", …

        The implementation walks rows top-to-bottom, which is the same
        order they appear in the table, so counters always reflect
        display order.
        """
        n = len(self._data)
        if n == 0:
            return

        # Build a child→parent lookup for fast traversal
        child_to_parent = {}
        for parent_row, children in self.parent_child_map.items():
            for child_row in children:
                child_to_parent[child_row] = parent_row

        # sibling_counter[row] = how many siblings at the same parent
        # have already been numbered before this row.
        # We track per-parent counters as we walk top-to-bottom.
        parent_child_counter = {}   # parent_row → next child counter

        wbs_ids = [""] * n
        topLevelCounter = 0
        for row in range(n):
            if row in child_to_parent:
                parent_row = child_to_parent[row]
                # Increment this parent's child counter
                count = parent_child_counter.get(parent_row, 0) + 1
                parent_child_counter[parent_row] = count
                parent_wbs = wbs_ids[parent_row]
                wbs_ids[row] = f"{parent_wbs}.{count}" if parent_wbs else str(count)
            else:
                # Top-level row — increment the top-level counter and assign that value
                topLevelCounter += 1
                wbs_ids[row] = str(topLevelCounter)

        for row in range(n):
            self._data[row][2] = wbs_ids[row]

    def get_parent_row(self, child_row):
        for parent_row, children in self.parent_child_map.items():
            if child_row in children:
                return parent_row
        return None

    def recalc_ancestors(self, start_row):
        current = start_row
        while True:
            parent = self.get_parent_row(current)
            if parent is None:
                break

            # Recalculate THIS parent based on its children
            children = self.parent_child_map.get(parent, [])
            if not children:
                break

            child_starts = []
            child_ends = []
            total_duration = 0.0

            for child in children:
                start = self._data[child][5]          # Start Date
                end_str = self._data[child][6]        # End Date
                dur = self._data[child][7]            # Duration

                if isinstance(start, QDateTime):
                    child_starts.append(start)

                end_dt = QDateTime.fromString(end_str, "yyyy-MM-dd HH:mm")
                if end_dt.isValid():
                    child_ends.append(end_dt)

                try:
                    total_duration += float(dur)
                except (ValueError, TypeError):
                    pass

            if child_starts and child_ends:
                self._data[parent][5] = min(child_starts)
                self._data[parent][6] = max(child_ends).toString("yyyy-MM-dd HH:mm")
                self._data[parent][7] = days_between(self._data[parent][5], self._data[parent][6])  # duration is not the sum of child durations, but the number of days between the earliest start and latest end

                top = self.index(parent, 5)
                bottom = self.index(parent, 7)
                self.dataChanged.emit(top, bottom, [Qt.DisplayRole])

            current = parent


class ResourceTableModel(QAbstractTableModel):
    def __init__(self, activity_model, parent=None):
        super().__init__(parent)
        self.headers = [
            'Name of Resource', 'Type of Resource', 'Email', 'Phone',
            'Standard Rate per Day', 'Overtime Rate per Day', 'Cost per Use',
            'Assigned Activity'
        ]
        self._data = []
        self.type_column = 1
        self.activity_model = activity_model
        self.indentation_levels = []
        self.expanded_states = []
        self.parent_child_map = {}

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
                
        row = index.row()
        column = index.column()
        value = self._data[row][column]
        
        if role == Qt.DisplayRole:
            if column == 0:  # Name column with indentation
                indent_level = self.indentation_levels[row] if row < len(self.indentation_levels) else 0
                return "  " * indent_level + str(value)
            return str(value)
        elif role == Qt.EditRole:
            return str(value)
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False
            
        row = index.row()
        column = index.column()

        if role == Qt.EditRole:
            self._data[row][column] = value
            self.dataChanged.emit(index, index, [role])
            
            # If this is a parent resource, recalculate its values
            if row in self.parent_child_map:
                self.recalc_parent_resources()
            
            return True
            
        return False

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def insertRows(self, position, rows, parent=QModelIndex()):
        self.beginInsertRows(parent, position, position + rows - 1)
        for _ in range(rows):
            empty_row = [""] * len(self.headers)
            self._data.insert(position, empty_row)
            
            # Ensure indentation_levels and expanded_states are properly initialized
            if position > len(self.indentation_levels):
                self.indentation_levels.extend([0] * (position - len(self.indentation_levels)))
            self.indentation_levels.insert(position, 0)
            
            if position > len(self.expanded_states):
                self.expanded_states.extend([True] * (position - len(self.expanded_states)))
            self.expanded_states.insert(position, True)
        self.endInsertRows()
        return True

    def removeRows(self, position, rows, parent=QModelIndex()):
        self.beginRemoveRows(parent, position, position + rows - 1)
        
        # Remove the rows and their corresponding indentation/expansion states
        del self._data[position:position + rows]
        del self.indentation_levels[position:position + rows]
        del self.expanded_states[position:position + rows]
        
        # Update parent-child relationships
        # Remove any relationships involving deleted rows
        for parent_row, children in list(self.parent_child_map.items()):
            if parent_row >= position and parent_row < position + rows:
                del self.parent_child_map[parent_row]
            else:
                # Update children list to remove deleted rows and adjust remaining indices
                new_children = []
                for child_row in children:
                    if child_row < position:
                        new_children.append(child_row)
                    elif child_row >= position + rows:
                        new_children.append(child_row - rows)
                if new_children:
                    self.parent_child_map[parent_row] = new_children
                else:
                    del self.parent_child_map[parent_row]
        
        self.endRemoveRows()
        return True

    def get_all_data(self):
        return self._data

    def set_all_data(self, data):
        self.beginResetModel()
        self._data = data
        self.endResetModel()

    def recalc_parent_resources(self):
        """
        Recalculate parent resource's rates and costs based on its sub-resources.
        """
        for parent_row, children in self.parent_child_map.items():
            if not children:
                continue

            # Initialize aggregation variables
            total_standard_rate = 0.0
            total_overtime_rate = 0.0
            total_cost_per_use = 0.0

            # Sum up rates and costs from children
            for child_row in children:
                try:
                    # Standard Rate (column 4)
                    std_rate = float(self._data[child_row][4]) if self._data[child_row][4] else 0
                    total_standard_rate += std_rate

                    # Overtime Rate (column 5)
                    ot_rate = float(self._data[child_row][5]) if self._data[child_row][5] else 0
                    total_overtime_rate += ot_rate

                    # Cost per Use (column 6)
                    cpu = float(self._data[child_row][6]) if self._data[child_row][6] else 0
                    total_cost_per_use += cpu
                except (ValueError, TypeError):
                    continue

            # Update parent's rates and costs
            self._data[parent_row][4] = str(total_standard_rate)
            self._data[parent_row][5] = str(total_overtime_rate)
            self._data[parent_row][6] = str(total_cost_per_use)

            # Emit signals for the updated cells
            self.dataChanged.emit(
                self.index(parent_row, 4),
                self.index(parent_row, 6),
                [Qt.DisplayRole]
            )

    def toggle_group(self, row):
        """
        Toggle the expanded/collapsed state of a group
        """
        if row in self.parent_child_map:
            self.expanded_states[row] = not self.expanded_states[row]
            self.update_visible_rows()

    def update_visible_rows(self):
        """
        Update which rows should be visible based on expanded/collapsed states
        """
        visible_rows = set()
        for row in range(len(self._data)):
            should_show = True
            current_row = row
            while current_row > 0:
                parent_row = None
                for potential_parent, children in self.parent_child_map.items():
                    if current_row in children:
                        parent_row = potential_parent
                        break
                
                if parent_row is None:
                    break
                
                if not self.expanded_states[parent_row]:
                    should_show = False
                    break
                
                current_row = parent_row
            
            if should_show:
                visible_rows.add(row)
        
        return visible_rows

    def is_group(self, row):
        """
        Check if a row is a group (has children)
        """
        return row in self.parent_child_map

    def get_indent_level(self, row):
        """
        Get the indentation level for a row
        """
        if row < len(self.indentation_levels):
            return self.indentation_levels[row]
        return 0


class RBSWidget(QWidget):
    def __init__(self, resource_model, parent=None):
        super().__init__(parent)
        self.resource_model = resource_model

        # Create a graphics scene and view
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Add zoom controls
        self.zoom_layout = QHBoxLayout()
        self.zoom_in_btn = QPushButton("Zoom In")
        self.zoom_out_btn = QPushButton("Zoom Out")
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.zoom_layout.addWidget(self.zoom_in_btn)
        self.zoom_layout.addWidget(self.zoom_out_btn)

        # Main layout
        layout = QVBoxLayout(self)
        layout.addLayout(self.zoom_layout)
        layout.addWidget(self.view)
        self.setLayout(layout)

        # Initial scale factor
        self.scale_factor = 1.0
        
        # Build the initial diagram
        self.refresh()

    def zoom_in(self):
        self.scale_factor *= 1.2
        self.view.scale(1.2, 1.2)

    def zoom_out(self):
        self.scale_factor /= 1.2
        self.view.scale(1/1.2, 1/1.2)

    def refresh(self):
        self.scene.clear()
        num_rows = self.resource_model.rowCount()
        cell_width = 160
        cell_height = 50
        horizontal_offset = 180
        vertical_spacing = 20

        cell_items = {}

        # Create cells for each resource
        for row in range(num_rows):
            resource_name = self.resource_model._data[row][0]
            resource_type = self.resource_model._data[row][1]
            if not resource_name:  # Skip empty rows
                continue

            indent_level = 0
            if row < len(self.resource_model.indentation_levels):
                indent_level = self.resource_model.indentation_levels[row]

            cell_text = f"{resource_name}\n({resource_type})"
            x_pos = indent_level * horizontal_offset
            y_pos = row * (cell_height + vertical_spacing)

            # Create the box with rounded corners
            rect_item = QGraphicsRectItem(0, 0, cell_width, cell_height)
            rect_item.setPos(x_pos, y_pos)
            
            # Style the box differently for parent resources
            if row in self.resource_model.parent_child_map:
                rect_item.setBrush(QBrush(QColor("#ADD8E6")))  # Light blue
                pen = QPen(QColor("#4682B4"), 2)  # Steel blue, thicker
            else:
                rect_item.setBrush(QBrush(QColor("#F0F8FF")))  # Alice blue
                pen = QPen(QColor("#4682B4"), 1)  # Steel blue, normal
            
            rect_item.setPen(pen)
            rect_item.setFlags(QGraphicsRectItem.ItemIsMovable | QGraphicsRectItem.ItemIsSelectable)
            self.scene.addItem(rect_item)

            # Add text with proper formatting
            text_item = QGraphicsTextItem(cell_text, rect_item)
            text_item.setDefaultTextColor(QColor("black"))
            # Center the text in the box
            text_bounds = text_item.boundingRect()
            text_x = (cell_width - text_bounds.width()) / 2
            text_y = (cell_height - text_bounds.height()) / 2
            text_item.setPos(text_x, text_y)

            cell_items[row] = rect_item

        # Draw arrows for parent-child relationships
        for parent_row, children in self.resource_model.parent_child_map.items():
            if parent_row not in cell_items:
                continue
            parent_rect = cell_items[parent_row]
            for child_row in children:
                if child_row not in cell_items:
                    continue
                child_rect = cell_items[child_row]
                arrow = DynamicArrow(parent_rect, child_rect, cell_width, cell_height)
                self.scene.addItem(arrow)

        # Fit the view to all items
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)


class RiskTableModel(QAbstractTableModel):
    def __init__(self, activity_model, parent=None):
        super().__init__(parent)
        self.activity_model = activity_model
        self.headers = [
            "ID", "Name of Activity", "Category of Risk", "Probability of Risk",
            "Impact on Project", "Rating of Risk"
        ]
        self._data = self.initialize_risk_data()

    def initialize_risk_data(self):
        data = []
        for row in range(self.activity_model.rowCount()):
            activity = self.activity_model._data[row]
            data.append([
                activity[0],  # ID
                activity[3],  # Name of Activity
                "",           # Category of Risk
                1,            # Default Probability
                1,            # Default Impact
                1 * 1         # Default Rating
            ])
        return data

    def refresh_from_activity_model(self):
        self.beginResetModel()
        self._data = [
            [
                activity[0],  # ID
                activity[3],  # Name of Activity
                "",           # Default Category of Risk
                1,            # Default Probability
                1,            # Default Impact
                1 * 1         # Default Rating
            ]
            for activity in self.activity_model._data
        ]
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.DisplayRole, Qt.EditRole):
            return self._data[index.row()][index.column()]
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or role != Qt.EditRole:
            return False

        row, column = index.row(), index.column()
        try:
            if column in [3, 4]:  # Probability/Impact
                numeric_value = int(value)
                if not (1 <= numeric_value <= 5):
                    raise ValueError("Value must be between 1 and 5")
                self._data[row][column] = numeric_value
                self._data[row][5] = self._data[row][3] * self._data[row][4]
                self.dataChanged.emit(self.index(row, 5), self.index(row, 5))
            elif column == 2:  # Category
                self._data[row][column] = value
        except ValueError as e:
            QMessageBox.warning(None, "Invalid Input", str(e))
            return False

        self.dataChanged.emit(index, index)
        return True


    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        column = index.column()
        if column in [2, 3, 4]:  # Editable columns
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable
    

class AssignedActivityDelegate(QStyledItemDelegate):
    def __init__(self, activity_model, parent=None):
        super().__init__(parent)
        self.activity_model = activity_model

    def createEditor(self, parent, option, index):
        if index.column() == 7:  # Assigned Activity column
            editor = QComboBox(parent)
            editor.addItem("")  # Allow unassigned resources
            for row in range(self.activity_model.rowCount()):
                activity_name = self.activity_model._data[row][3]  # Name column
                if activity_name.strip():
                    editor.addItem(activity_name)
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if index.column() == 7 and isinstance(editor, QComboBox):
            current_text = index.model().data(index, Qt.EditRole)
            idx = editor.findText(current_text)
            if idx >= 0:
                editor.setCurrentIndex(idx)
            else:
                editor.setCurrentIndex(0)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if index.column() == 7 and isinstance(editor, QComboBox):
            model.setData(index, editor.currentText(), Qt.EditRole)
        else:
            super().setModelData(editor, index)


class BillOfQuantityTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.headers = [
            "Number of Work", "Type of Work", "Unit of Measurement", 
            "Dimension 1", "Dimension 2", "Dimension 3", "Sum", 
            "Cost per Unit", "Total Cost", "NOTES"
        ]
        self._data = []

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        column = index.column()
        value = self._data[row][column]
        if role in (Qt.DisplayRole, Qt.EditRole):
            return str(value) if value is not None else ""
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid():
            return False

        row = index.row()
        column = index.column()

        if role == Qt.EditRole:
            self._data[row][column] = value
            # If one of the dimensions (columns 3, 4, 5) or cost per unit (column 7) changes,
            # recalc the computed columns (Sum in column6 and Total Cost in column8)
            if column in [3, 4, 5, 7]:
                self.recalculate_row(row)
                # Emit change signals for computed columns
                topLeft = self.index(row, 6)
                bottomRight = self.index(row, 8)
                self.dataChanged.emit(topLeft, bottomRight, [Qt.DisplayRole])
            self.dataChanged.emit(index, index, [Qt.DisplayRole])
            return True

        return False

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return self.headers[section]
            else:
                return str(section + 1)
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        column = index.column()
        # Make computed columns (Sum and Total Cost) read-only.
        if column in [6, 8]:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def insertRows(self, position, rows, parent=QModelIndex()):
        self.beginInsertRows(parent, position, position + rows - 1)
        for _ in range(rows):
            # Initialize a new row with empty values
            new_row = ["" for _ in range(len(self.headers))]
            self._data.insert(position, new_row)
        self.endInsertRows()
        return True

    def removeRows(self, position, rows, parent=QModelIndex()):
        self.beginRemoveRows(parent, position, position + rows - 1)
        del self._data[position:position+rows]
        self.endRemoveRows()
        return True

    def recalculate_row(self, row):
        # Recalculate the "Sum" (column 6) based on dimensions in columns 3, 4, 5.
        dims = []
        for col in [3, 4, 5]:
            try:
                val = float(self._data[row][col])
                dims.append(val)
            except (ValueError, TypeError):
                pass

        if dims:
            product = 1
            for d in dims:
                product *= d
            sum_val = product
        else:
            sum_val = ""
        self._data[row][6] = sum_val

        # Now recalc the "Total Cost" (column 8) = Cost per Unit (col 7) * Sum (col 6)
        try:
            cost_per_unit = float(self._data[row][7])
            if sum_val != "":
                total = cost_per_unit * float(sum_val)
            else:
                total = ""
        except (ValueError, TypeError):
            total = ""
        self._data[row][8] = total


class IntegrationTableModel(QAbstractTableModel):
    def __init__(self, activity_model, resource_model, risk_model, boq_model, parent=None):
        super().__init__(parent)
        self.activity_model = activity_model
        self.resource_model = resource_model 
        self.risk_model = risk_model
        self.boq_model = boq_model
        
        # Define the column headers
        self.headers = ["Activity ID", "Activity Name", "Duration", "Start Date", "End Date", 
                        "Assigned Resources", "Assigned Risks", "Assigned BOQ Items"]
        
        # Structure to store relationships between activities and other items
        # Format: {activity_id: {
        #            'resources': [resource_id1, resource_id2, ...],
        #            'risks': [risk_id1, risk_id2, ...],
        #            'boq': [boq_id1, boq_id2, ...]
        #          }}
        self.relationships = {}
        
        # Initialize relationships
        self.refresh_relationships()
        
        # Connect signals to update when underlying models change
        if self.activity_model:
            self.activity_model.dataChanged.connect(self.on_activity_data_changed)
        if self.resource_model:
            self.resource_model.dataChanged.connect(self.on_resource_data_changed)
        if self.risk_model:
            self.risk_model.dataChanged.connect(self.on_risk_data_changed)
        if self.boq_model:
            self.boq_model.dataChanged.connect(self.on_boq_data_changed)
            
        # Debug output to verify models are loaded
        print(f"Integration Model initialized with:")
        print(f"- {len(self.activity_model._data) if self.activity_model else 0} activities")
        print(f"- {len(self.resource_model._data) if self.resource_model else 0} resources")
        print(f"- {len(self.risk_model._data) if self.risk_model else 0} risks")
        print(f"- {len(self.boq_model._data) if self.boq_model else 0} BOQ items")
    
    def on_activity_data_changed(self, topLeft, bottomRight, roles):
        """Called when activity data changes"""
        self.layoutChanged.emit()
    
    def on_resource_data_changed(self, topLeft, bottomRight, roles):
        """Called when resource data changes"""
        self.refresh_relationships()
        self.layoutChanged.emit()
    
    def on_risk_data_changed(self, topLeft, bottomRight, roles):
        """Called when risk data changes"""
        self.refresh_relationships()
        self.layoutChanged.emit()
    
    def on_boq_data_changed(self, topLeft, bottomRight, roles):
        """Called when BOQ data changes"""
        self.refresh_relationships()
        self.layoutChanged.emit()
    
    def refresh_relationships(self):
        """Rebuild the relationships from the underlying models"""
        self.beginResetModel()
        
        # Clear existing relationships
        self.relationships = {}
        
        # Initialize relationships for each activity
        if self.activity_model and hasattr(self.activity_model, '_data'):
            for activity in self.activity_model._data:
                if activity and len(activity) > 0:
                    activity_id = activity[0]
                    self.relationships[activity_id] = {
                        'resources': [],
                        'risks': [],
                        'boq': []
                    }
        
        # Load risk assignments - assuming risk model has activity IDs in column 1
        if self.risk_model and hasattr(self.risk_model, '_data'):
            for risk in self.risk_model._data:
                if risk and len(risk) > 1 and risk[1]:  # If risk has an assigned activity
                    activity_id = risk[1]
                    risk_id = risk[0]
                    if activity_id in self.relationships:
                        self.relationships[activity_id]['risks'].append(risk_id)
        
        # Load existing resource assignments if available
        # This depends on how resources are linked to activities in your model
        # You might need to adapt this based on your data structure
        
        # Load existing BOQ assignments if available
        # This depends on how BOQ items are linked to activities in your model
        
        self.endResetModel()
        
    def rowCount(self, parent=None):
        if self.activity_model and hasattr(self.activity_model, '_data'):
            return len(self.activity_model._data)
        return 0
        
    def columnCount(self, parent=None):
        return len(self.headers)
        
    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
            
        if not self.activity_model or not hasattr(self.activity_model, '_data'):
            return None
            
        if index.row() >= len(self.activity_model._data):
            return None
            
        row = index.row()
        col = index.column()
        
        activity = self.activity_model._data[row]
        
        if role == Qt.DisplayRole:
            # Activity ID column
            if col == 0:
                return activity[0]
            elif col == 1:
                return activity[3] if len(activity) > 3 else ""   # Name col 3
            elif col == 2:
                return activity[7] if len(activity) > 7 else ""   # Duration col 7
            elif col == 3:
                return activity[5] if len(activity) > 5 else ""   # Start Date col 5
            elif col == 4:
                return activity[6] if len(activity) > 6 else ""   # End Date col 6
            # Resources column
            elif col == 5:
                activity_id = activity[0]
                if activity_id in self.relationships:
                    resource_ids = self.relationships[activity_id]['resources']
                    return ", ".join([self.get_resource_name(r_id) for r_id in resource_ids])
                return ""
            # Risks column
            elif col == 6:
                activity_id = activity[0]
                if activity_id in self.relationships:
                    risk_ids = self.relationships[activity_id]['risks']
                    return ", ".join([self.get_risk_name(r_id) for r_id in risk_ids])
                return ""
            # BOQ Items column
            elif col == 7:
                activity_id = activity[0]
                if activity_id in self.relationships:
                    boq_ids = self.relationships[activity_id]['boq']
                    return ", ".join([self.get_boq_item_desc(b_id) for b_id in boq_ids])
                return ""
        
        return None
        
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None
        
    def flags(self, index):
        # Make all cells non-editable but selectable
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        
    def get_resource_name(self, resource_id):
        """Get the name of a resource by its ID"""
        if self.resource_model and hasattr(self.resource_model, '_data'):
            for resource in self.resource_model._data:
                if resource and len(resource) > 0 and resource[0] == resource_id:
                    return resource[1] if len(resource) > 1 else "Unnamed Resource"
        return f"Resource {resource_id}"
        
    def get_risk_name(self, risk_id):
        """Get the name/description of a risk by its ID"""
        if self.risk_model and hasattr(self.risk_model, '_data'):
            for risk in self.risk_model._data:
                if risk and len(risk) > 0 and risk[0] == risk_id:
                    # Assuming column 2 has risk description, adjust as needed
                    return risk[2] if len(risk) > 2 else f"Risk {risk_id}"
        return f"Risk {risk_id}"
        
    def get_boq_item_desc(self, boq_id):
        """Get the description of a BOQ item by its ID"""
        if self.boq_model and hasattr(self.boq_model, '_data'):
            for boq in self.boq_model._data:
                if boq and len(boq) > 0 and boq[0] == boq_id:
                    return boq[1] if len(boq) > 1 else f"BOQ Item {boq_id}"
        return f"BOQ Item {boq_id}"
        
    def assign_resource_to_activity(self, activity_row, resource_id):
        """Assign a resource to an activity"""
        if not self.activity_model or not hasattr(self.activity_model, '_data'):
            return False
            
        if activity_row >= len(self.activity_model._data):
            return False
            
        activity_id = self.activity_model._data[activity_row][0]
        
        # Ensure this activity has an entry in relationships
        if activity_id not in self.relationships:
            self.relationships[activity_id] = {
                'resources': [],
                'risks': [],
                'boq': []
            }
            
        # Check if already assigned
        if resource_id in self.relationships[activity_id]['resources']:
            return False
            
        # Add the resource assignment
        self.relationships[activity_id]['resources'].append(resource_id)
        
        # Update the view for this row
        self.dataChanged.emit(
            self.index(activity_row, 5),
            self.index(activity_row, 5)
        )
        
        return True
        
    def assign_risk_to_activity(self, activity_row, risk_id):
        """Assign a risk to an activity"""
        if not self.activity_model or not hasattr(self.activity_model, '_data'):
            return False
            
        if activity_row >= len(self.activity_model._data):
            return False
            
        activity_id = self.activity_model._data[activity_row][0]
        
        # Ensure this activity has an entry in relationships
        if activity_id not in self.relationships:
            self.relationships[activity_id] = {
                'resources': [],
                'risks': [],
                'boq': []
            }
            
        # Check if already assigned
        if risk_id in self.relationships[activity_id]['risks']:
            return False
            
        # Add the risk assignment
        self.relationships[activity_id]['risks'].append(risk_id)
        
        # Update the risk model (assuming column 1 stores activity ID)
        if self.risk_model and hasattr(self.risk_model, '_data'):
            for i, risk in enumerate(self.risk_model._data):
                if risk[0] == risk_id:
                    self.risk_model._data[i][1] = activity_id
                    if hasattr(self.risk_model, 'dataChanged'):
                        self.risk_model.dataChanged.emit(
                            self.risk_model.index(i, 1),
                            self.risk_model.index(i, 1)
                        )
                    break
        
        # Update the view for this row
        self.dataChanged.emit(
            self.index(activity_row, 6),
            self.index(activity_row, 6)
        )
        
        return True
        
    def assign_boq_to_activity(self, activity_row, boq_id):
        """Assign a BOQ item to an activity"""
        if not self.activity_model or not hasattr(self.activity_model, '_data'):
            return False
            
        if activity_row >= len(self.activity_model._data):
            return False
            
        activity_id = self.activity_model._data[activity_row][0]
        
        # Ensure this activity has an entry in relationships
        if activity_id not in self.relationships:
            self.relationships[activity_id] = {
                'resources': [],
                'risks': [],
                'boq': []
            }
            
        # Check if already assigned
        if boq_id in self.relationships[activity_id]['boq']:
            return False
            
        # Add the BOQ assignment
        self.relationships[activity_id]['boq'].append(boq_id)
        
        # Update the view for this row
        self.dataChanged.emit(
            self.index(activity_row, 7),
            self.index(activity_row, 7)
        )
        
        return True
        
    def remove_relationship(self, activity_row, item_id, rel_type):
        """Remove a relationship between an activity and a resource/risk/BOQ item"""
        if not self.activity_model or not hasattr(self.activity_model, '_data'):
            return False
            
        if activity_row >= len(self.activity_model._data):
            return False
            
        activity_id = self.activity_model._data[activity_row][0]
        
        if activity_id not in self.relationships:
            return False
            
        # Determine which relationship list to modify
        if rel_type == "resource":
            rel_list = 'resources'
            col = 5
        elif rel_type == "risk":
            rel_list = 'risks'
            col = 6
        elif rel_type == "boq":
            rel_list = 'boq'
            col = 7
        else:
            return False
            
        # Check if the item is in the relationship list
        if item_id not in self.relationships[activity_id][rel_list]:
            return False
            
        # Remove the item from the relationship
        self.relationships[activity_id][rel_list].remove(item_id)
        
        # If this is a risk, update the risk model
        if rel_type == "risk" and self.risk_model and hasattr(self.risk_model, '_data'):
            for i, risk in enumerate(self.risk_model._data):
                if risk[0] == item_id:
                    self.risk_model._data[i][1] = None  # Clear activity assignment
                    if hasattr(self.risk_model, 'dataChanged'):
                        self.risk_model.dataChanged.emit(
                            self.risk_model.index(i, 1),
                            self.risk_model.index(i, 1)
                        )
                    break
        
        # Update the view
        self.dataChanged.emit(
            self.index(activity_row, col),
            self.index(activity_row, col)
        )
        
        return True


class AssignmentDialog(QDialog):
    def __init__(self, parent=None, title="Assign Items", items=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # Create list widget for items
        self.list_widget = QListWidget()
        if items:
            for item_id, item_name in items:
                list_item = QListWidgetItem(f"{item_name} (ID: {item_id})")
                list_item.setData(Qt.UserRole, item_id)
                self.list_widget.addItem(list_item)
                
        # Create filter/search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search...")
        self.search_box.textChanged.connect(self.filter_items)
        
        # Create buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        
        layout.addWidget(QLabel("Search:"))
        layout.addWidget(self.search_box)
        layout.addWidget(QLabel("Select items to assign:"))
        layout.addWidget(self.list_widget)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
        
    def filter_items(self, text):
        """Filter the items based on search text"""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if text.lower() in item.text().lower():
                item.setHidden(False)
            else:
                item.setHidden(True)
                
    def get_selected_ids(self):
        """Get IDs of selected items"""
        selected_ids = []
        for item in self.list_widget.selectedItems():
            selected_ids.append(item.data(Qt.UserRole))
        return selected_ids


class IntegrationTab(QWidget):
    def __init__(self, integration_model, activity_model, resource_model, risk_model, boq_model, parent=None):
        super().__init__(parent)
        self.integration_model = integration_model
        self.activity_model = activity_model
        self.resource_model = resource_model
        self.risk_model = risk_model
        self.boq_model = boq_model
        
        # Create layout
        layout = QVBoxLayout(self)
        
        # Create table view for the integration model
        self.table_view = QTableView()
        self.table_view.setModel(self.integration_model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_context_menu)
        
        # Buttons for relationship management
        button_layout = QHBoxLayout()
        
        self.assign_resource_btn = QPushButton("Assign Resources")
        self.assign_resource_btn.clicked.connect(self.assign_resources)
        
        self.assign_risk_btn = QPushButton("Assign Risks")
        self.assign_risk_btn.clicked.connect(self.assign_risks)
        
        self.assign_boq_btn = QPushButton("Assign BOQ Items")
        self.assign_boq_btn.clicked.connect(self.assign_boq_items)
        
        self.refresh_btn = QPushButton("Refresh Connections")
        self.refresh_btn.clicked.connect(self.refresh_connections)
        
        button_layout.addWidget(self.assign_resource_btn)
        button_layout.addWidget(self.assign_risk_btn)
        button_layout.addWidget(self.assign_boq_btn)
        button_layout.addWidget(self.refresh_btn)
        
        layout.addWidget(self.table_view)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Resize columns
        self.table_view.resizeColumnsToContents()
        
    def show_context_menu(self, position):
        """Show context menu for table items"""
        index = self.table_view.indexAt(position)
        if not index.isValid():
            return
            
        menu = QMenu()
        assign_resource_action = menu.addAction("Assign Resources")
        assign_risk_action = menu.addAction("Assign Risks")
        assign_boq_action = menu.addAction("Assign BOQ Items")
        
        menu.addSeparator()
        
        manage_resources_action = menu.addAction("Manage Assigned Resources")
        manage_risks_action = menu.addAction("Manage Assigned Risks")
        manage_boq_action = menu.addAction("Manage Assigned BOQ Items")
        
        action = menu.exec_(self.table_view.mapToGlobal(position))
        
        row = index.row()
        if action == assign_resource_action:
            self.assign_resources(row)
        elif action == assign_risk_action:
            self.assign_risks(row)
        elif action == assign_boq_action:
            self.assign_boq_items(row)
        elif action == manage_resources_action:
            self.manage_assigned_resources(row)
        elif action == manage_risks_action:
            self.manage_assigned_risks(row)
        elif action == manage_boq_action:
            self.manage_assigned_boq_items(row)
            
    def assign_resources(self, specific_row=None):
        """Open dialog to assign resources to the selected activity"""
        if specific_row is None:
            indexes = self.table_view.selectedIndexes()
            if not indexes:
                QMessageBox.warning(self, "No Selection", "Please select an activity first.")
                return
            row = indexes[0].row()
        else:
            row = specific_row
            
        # Prepare resource list (ID, Name)
        resources = [(r[0], r[1]) for r in self.resource_model._data 
                     if r[1] and not r[1].startswith("Group:")]
        
        dialog = AssignmentDialog(self, "Assign Resources", resources)
        if dialog.exec_() == QDialog.Accepted:
            resource_ids = dialog.get_selected_ids()
            for resource_id in resource_ids:
                self.integration_model.assign_resource_to_activity(row, resource_id)
                
    def assign_risks(self, specific_row=None):
        """Open dialog to assign risks to the selected activity"""
        if specific_row is None:
            indexes = self.table_view.selectedIndexes()
            if not indexes:
                QMessageBox.warning(self, "No Selection", "Please select an activity first.")
                return
            row = indexes[0].row()
        else:
            row = specific_row
            
        # Prepare risk list (ID, Description)
        risks = [(r[0], r[2]) for r in self.risk_model._data if r[2]]
        
        dialog = AssignmentDialog(self, "Assign Risks", risks)
        if dialog.exec_() == QDialog.Accepted:
            risk_ids = dialog.get_selected_ids()
            for risk_id in risk_ids:
                self.integration_model.assign_risk_to_activity(row, risk_id)
                
    def assign_boq_items(self, specific_row=None):
        """Open dialog to assign BOQ items to the selected activity"""
        if specific_row is None:
            indexes = self.table_view.selectedIndexes()
            if not indexes:
                QMessageBox.warning(self, "No Selection", "Please select an activity first.")
                return
            row = indexes[0].row()
        else:
            row = specific_row
            
        # Prepare BOQ list (ID, Description)
        boq_items = [(b[0], b[1]) for b in self.boq_model._data if b[1]]
        
        dialog = AssignmentDialog(self, "Assign BOQ Items", boq_items)
        if dialog.exec_() == QDialog.Accepted:
            boq_ids = dialog.get_selected_ids()
            for boq_id in boq_ids:
                self.integration_model.assign_boq_to_activity(row, boq_id)
                
    def manage_assigned_resources(self, row):
        """Open dialog to manage already assigned resources"""
        activity_id = self.activity_model._data[row][0]
        assigned_resources = [r for r in self.integration_model.relationships 
                             if r[0] == activity_id and r[2] == "resource"]
        
        if not assigned_resources:
            QMessageBox.information(self, "No Resources", "No resources assigned to this activity.")
            return
            
        resource_list = [(r[1], self.integration_model.get_resource_name(r[1])) 
                        for r in assigned_resources]
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Assigned Resources")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        
        for resource_id, resource_name in resource_list:
            item = QListWidgetItem(f"{resource_name} (ID: {resource_id})")
            item.setData(Qt.UserRole, resource_id)
            list_widget.addItem(item)
            
        remove_btn = QPushButton("Remove Selected")
        
        def remove_selected():
            for item in list_widget.selectedItems():
                resource_id = item.data(Qt.UserRole)
                if self.integration_model.remove_relationship(row, resource_id, "resource"):
                    # Remove from list widget too
                    list_widget.takeItem(list_widget.row(item))
                    
        remove_btn.clicked.connect(remove_selected)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(remove_btn)
        button_layout.addWidget(close_btn)
        
        layout.addWidget(QLabel("Currently assigned resources:"))
        layout.addWidget(list_widget)
        layout.addLayout(button_layout)
        
        dialog.exec_()
        
    def manage_assigned_risks(self, row):
        """Open dialog to manage already assigned risks"""
        activity_id = self.activity_model._data[row][0]
        assigned_risks = [r for r in self.integration_model.relationships 
                         if r[0] == activity_id and r[2] == "risk"]
        
        if not assigned_risks:
            QMessageBox.information(self, "No Risks", "No risks assigned to this activity.")
            return
            
        risk_list = [(r[1], self.integration_model.get_risk_name(r[1])) 
                    for r in assigned_risks]
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Assigned Risks")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        
        for risk_id, risk_name in risk_list:
            item = QListWidgetItem(f"{risk_name} (ID: {risk_id})")
            item.setData(Qt.UserRole, risk_id)
            list_widget.addItem(item)
            
        remove_btn = QPushButton("Remove Selected")
        
        def remove_selected():
            for item in list_widget.selectedItems():
                risk_id = item.data(Qt.UserRole)
                if self.integration_model.remove_relationship(row, risk_id, "risk"):
                    # Remove from list widget too
                    list_widget.takeItem(list_widget.row(item))
                    
        remove_btn.clicked.connect(remove_selected)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(remove_btn)
        button_layout.addWidget(close_btn)
        
        layout.addWidget(QLabel("Currently assigned risks:"))
        layout.addWidget(list_widget)
        layout.addLayout(button_layout)
        
        dialog.exec_()
        
    def manage_assigned_boq_items(self, row):
        """Open dialog to manage already assigned BOQ items"""
        activity_id = self.activity_model._data[row][0]
        assigned_boq = [r for r in self.integration_model.relationships 
                       if r[0] == activity_id and r[2] == "boq"]
        
        if not assigned_boq:
            QMessageBox.information(self, "No BOQ Items", "No BOQ items assigned to this activity.")
            return
            
        boq_list = [(b[1], self.integration_model.get_boq_item_desc(b[1])) 
                   for b in assigned_boq]
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Manage Assigned BOQ Items")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        list_widget = QListWidget()
        
        for boq_id, boq_desc in boq_list:
            item = QListWidgetItem(f"{boq_desc} (ID: {boq_id})")
            item.setData(Qt.UserRole, boq_id)
            list_widget.addItem(item)
            
        remove_btn = QPushButton("Remove Selected")
        
        def remove_selected():
            for item in list_widget.selectedItems():
                boq_id = item.data(Qt.UserRole)
                if self.integration_model.remove_relationship(row, boq_id, "boq"):
                    # Remove from list widget too
                    list_widget.takeItem(list_widget.row(item))
                    
        remove_btn.clicked.connect(remove_selected)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(remove_btn)
        button_layout.addWidget(close_btn)
        
        layout.addWidget(QLabel("Currently assigned BOQ items:"))
        layout.addWidget(list_widget)
        layout.addLayout(button_layout)
        
        dialog.exec_()
        
    def refresh_connections(self):
        """Refresh all connections from the underlying models"""
        self.integration_model.refresh_relationships()


class UnitDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        if index.column() == 2:  # Unit of Measurement column
            editor = QComboBox(parent)
            editor.addItems(["m2", "m3", "kg"])
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if index.column() == 2 and isinstance(editor, QComboBox):
            current_text = index.model().data(index, Qt.EditRole)
            idx = editor.findText(current_text)
            if idx >= 0:
                editor.setCurrentIndex(idx)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if index.column() == 2 and isinstance(editor, QComboBox):
            model.setData(index, editor.currentText(), Qt.EditRole)
        else:
            super().setModelData(editor, model, index)


class DynamicArrow(QGraphicsLineItem):

    def __init__(self, parent_item, child_item, cell_width, cell_height, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_item = parent_item    # QGraphicsRectItem of the parent
        self.child_item = child_item      # QGraphicsRectItem of the child
        self.cell_width = cell_width
        self.cell_height = cell_height
        self.pen = QPen(Qt.black, 2)
        self.setPen(self.pen)
        self.setZValue(-1)  # Ensure arrows are drawn behind cells

    def updatePosition(self):
        """
        Updates the line endpoints based on the current positions of the parent and child cells.
        """
        parent_pos = self.parent_item.pos()
        child_pos = self.child_item.pos()
        # Start at the right center of the parent's rectangle
        start_point = QPointF(parent_pos.x() + self.cell_width, parent_pos.y() + self.cell_height / 2)
        # End at the left center of the child's rectangle
        end_point = QPointF(child_pos.x(), child_pos.y() + self.cell_height / 2)
        self.setLine(QLineF(start_point, end_point))

    def paint(self, painter, option, widget):
        # Always update the line based on current positions
        self.updatePosition()
        # Draw the line
        painter.setPen(self.pen)
        line = self.line()
        painter.drawLine(line)
        # Draw the arrow head at the end of the line
        arrow_size = 10
        angle = math.atan2(-line.dy(), line.dx())
        dest = line.p2()
        arrow_p1 = dest + QPointF(math.sin(angle + math.pi / 3) * arrow_size,
                                  math.cos(angle + math.pi / 3) * arrow_size)
        arrow_p2 = dest + QPointF(math.sin(angle + math.pi - math.pi / 3) * arrow_size,
                                  math.cos(angle + math.pi - math.pi / 3) * arrow_size)
        arrow_head = QPolygonF([dest, arrow_p1, arrow_p2])
        painter.setBrush(Qt.black)
        painter.drawPolygon(arrow_head)


class WBSWidget(QWidget):
    def __init__(self, activity_model, parent=None):
        super().__init__(parent)
        self.activity_model = activity_model

        # Create a graphics scene and view
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Add zoom controls
        self.zoom_layout = QHBoxLayout()
        self.zoom_in_btn = QPushButton("Zoom In")
        self.zoom_out_btn = QPushButton("Zoom Out")
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        self.zoom_layout.addWidget(self.zoom_in_btn)
        self.zoom_layout.addWidget(self.zoom_out_btn)

        # Main layout
        layout = QVBoxLayout(self)
        layout.addLayout(self.zoom_layout)
        layout.addWidget(self.view)
        self.setLayout(layout)

        # Initial scale factor
        self.scale_factor = 1.0
        
        # Build the initial diagram
        self.refresh()

    def zoom_in(self):
        self.scale_factor *= 1.2
        self.view.scale(1.2, 1.2)

    def zoom_out(self):
        self.scale_factor /= 1.2
        self.view.scale(1/1.2, 1/1.2)

    def refresh(self):
        self.scene.clear()
        num_rows = self.activity_model.rowCount()
        cell_width = 160
        cell_height = 50
        horizontal_offset = 180
        vertical_spacing = 20

        cell_items = {}

        # Create cells for each activity
        for row in range(num_rows):
            activity_id = self.activity_model._data[row][0]
            activity_name = self.activity_model._data[row][3]
            if not activity_name:  # Skip empty rows
                continue

            indent_level = 0
            if row < len(self.activity_model.indentation_levels):
                indent_level = self.activity_model.indentation_levels[row]

            # Show Activity No and Name for a cleaner label
            act_no = self.activity_model._data[row][1]
            wbs_id = self.activity_model._data[row][2]
            cell_text = f"{wbs_id} {activity_name}" if wbs_id else f"{act_no} {activity_name}"
            x_pos = indent_level * horizontal_offset
            y_pos = row * (cell_height + vertical_spacing)

            # Create the box with rounded corners
            rect_item = QGraphicsRectItem(0, 0, cell_width, cell_height)
            rect_item.setPos(x_pos, y_pos)
            
            # Style the box differently for parent activities
            if row in self.activity_model.parent_child_map:
                rect_item.setBrush(QBrush(QColor("#ADD8E6")))  # Light blue
                pen = QPen(QColor("#4682B4"), 2)  # Steel blue, thicker
            else:
                rect_item.setBrush(QBrush(QColor("#F0F8FF")))  # Alice blue
                pen = QPen(QColor("#4682B4"), 1)  # Steel blue, normal
            
            rect_item.setPen(pen)
            rect_item.setFlags(QGraphicsRectItem.ItemIsMovable | QGraphicsRectItem.ItemIsSelectable)
            self.scene.addItem(rect_item)

            # Add text with proper formatting
            text_item = QGraphicsTextItem(cell_text, rect_item)
            text_item.setDefaultTextColor(QColor("black"))
            # Center the text in the box
            text_bounds = text_item.boundingRect()
            text_x = (cell_width - text_bounds.width()) / 2
            text_y = (cell_height - text_bounds.height()) / 2
            text_item.setPos(text_x, text_y)

            cell_items[row] = rect_item

        # Draw arrows for parent-child relationships
        for parent_row, children in self.activity_model.parent_child_map.items():
            if parent_row not in cell_items:
                continue
            parent_rect = cell_items[parent_row]
            for child_row in children:
                if child_row not in cell_items:
                    continue
                child_rect = cell_items[child_row]
                arrow = DynamicArrow(parent_rect, child_rect, cell_width, cell_height)
                self.scene.addItem(arrow)

        # Fit the view to all items
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)


class ActivityTableApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Window setup
        self.setWindowTitle("Project Manager with CPM and Resources")
        self.setGeometry(100, 100, 1600, 800)
        self.setWindowFlags(Qt.Window)
        
        # Create models
        self.activity_model = ActivityTableModel()
        self.resource_model = ResourceTableModel(self.activity_model)

        # Create central widget and main layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Create QTabWidget
        self.tabs = QTabWidget()
        self.main_layout.addWidget(self.tabs)

        # Create Table Tab
        self.table_tab = QWidget()
        self.table_layout = QVBoxLayout(self.table_tab)
        
        # Create the table view
        self.table_view = QTableView(self)
        self.table_view.setModel(self.activity_model)
        
        # Hide internal UUID column only; Activity No (1) and WBS ID (2) are visible
        self.table_view.hideColumn(0)

        # Make headers resize properly
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_view.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        
        # Make table resize with window
        self.table_view.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.table_layout.addWidget(self.table_view)

        # Set delegate for Start Date to use QDateTimeEdit
        self.date_delegate = DateTimeDelegate()
        self.table_view.setItemDelegateForColumn(5, self.date_delegate)

        # Add the group delegate
        self.group_delegate = GroupDelegate()
        self.table_view.setItemDelegateForColumn(1, self.group_delegate)

        # Create button layout
        self.button_layout = QHBoxLayout()
        
        # Add control buttons
        self.add_row_button = QPushButton("Add Row")
        self.add_row_button.clicked.connect(self.add_row)
        self.remove_row_button = QPushButton("Remove Row")
        self.remove_row_button.clicked.connect(self.remove_row)
        
        # Add indent/outdent buttons
        self.indent_button = QPushButton("Indent")
        self.indent_button.clicked.connect(self.indent_selected)
        self.outdent_button = QPushButton("Outdent")
        self.outdent_button.clicked.connect(self.outdent_selected)
        
        # Add expand/collapse button
        self.toggle_group_button = QPushButton("Toggle Group")
        self.toggle_group_button.clicked.connect(self.toggle_selected_group)

        # Add all buttons to layout
        self.button_layout.addWidget(self.add_row_button)
        self.button_layout.addWidget(self.remove_row_button)
        self.button_layout.addWidget(self.indent_button)
        self.button_layout.addWidget(self.outdent_button)
        self.button_layout.addWidget(self.toggle_group_button)
        
        # Add button layout to table layout
        self.table_layout.addLayout(self.button_layout)

        # Add Table Tab to QTabWidget
        self.tabs.addTab(self.table_tab, "Table View")

        # Create Resources Tab
        self.resources_tab = QWidget()
        self.resources_layout = QVBoxLayout(self.resources_tab)
        
        # Create the resources table view
        self.resources_view = QTableView(self)
        self.resources_view.setModel(self.resource_model)
        
        # Make headers resize properly
        self.resources_view.horizontalHeader().setStretchLastSection(True)
        self.resources_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.resources_view.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        
        # Make table resize with window
        self.resources_view.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.resources_layout.addWidget(self.resources_view)

        # Set delegates for resources
        self.type_delegate = ResourceTypeDelegate()
        self.resources_view.setItemDelegateForColumn(1, self.type_delegate)
        
        self.assigned_activity_delegate = AssignedActivityDelegate(self.activity_model)
        self.resources_view.setItemDelegateForColumn(7, self.assigned_activity_delegate)

        # Add control buttons to Resources Tab
        self.resources_button_layout = QHBoxLayout()
        self.add_resource_button = QPushButton("Add Resource")
        self.add_resource_button.clicked.connect(self.add_resource)
        self.remove_resource_button = QPushButton("Remove Resource")
        self.remove_resource_button.clicked.connect(self.remove_resource)
        self.indent_resource_button = QPushButton("Indent Resource")
        self.indent_resource_button.clicked.connect(self.indent_resource)
        self.outdent_resource_button = QPushButton("Outdent Resource")
        self.outdent_resource_button.clicked.connect(self.outdent_resource)
        
        self.resources_button_layout.addWidget(self.add_resource_button)
        self.resources_button_layout.addWidget(self.remove_resource_button)
        self.resources_button_layout.addWidget(self.indent_resource_button)
        self.resources_button_layout.addWidget(self.outdent_resource_button)
        self.resources_layout.addLayout(self.resources_button_layout)

        # Add Resources Tab to QTabWidget
        self.tabs.addTab(self.resources_tab, "Resources")

        # Create Gantt Chart Tab
        self.gantt_tab = QWidget()
        self.gantt_layout = QVBoxLayout(self.gantt_tab)
        
        # Setup Gantt chart
        self.setup_gantt_chart()
        self.gantt_layout.addWidget(self.canvas)
        self.gantt_layout.addWidget(self.toolbar)

        # Add Gantt Chart Tab to QTabWidget
        self.tabs.addTab(self.gantt_tab, "Gantt Chart")

        # Create PERT Chart Tab
        self.pert_tab = QWidget()
        self.pert_layout = QVBoxLayout(self.pert_tab)
        
        # Setup PERT chart
        self.setup_pert_chart()
        self.pert_layout.addWidget(self.pert_canvas)
        self.pert_layout.addWidget(self.pert_toolbar)

        # Add PERT Chart Tab to QTabWidget
        self.tabs.addTab(self.pert_tab, "PERT Diagram")

        self.use_fruchterman = True
        self.layout_toggle = QPushButton("Toggle Layout")
        self.layout_toggle.clicked.connect(self.toggle_layout)
        # Add to your control panel


        # Create Risk Management Tab
        self.risk_tab = QWidget()
        self.risk_layout = QVBoxLayout(self.risk_tab)

        # Create the risk table view
        self.risk_view = QTableView(self)
        self.risk_model = RiskTableModel(self.activity_model)  # Link with activity model
        self.risk_model.refresh_from_activity_model()
        self.risk_view.setModel(self.risk_model)

        # Connect signals to refresh Risk Management table
        self.activity_model.dataChanged.connect(self.risk_model.refresh_from_activity_model)
        self.activity_model.rowsInserted.connect(self.risk_model.refresh_from_activity_model)
        self.activity_model.rowsRemoved.connect(self.risk_model.refresh_from_activity_model)

        # Make headers resize properly
        self.risk_view.horizontalHeader().setStretchLastSection(True)
        self.risk_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.risk_view.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)

        self.risk_layout.addWidget(self.risk_view)

        # Replace the matplotlib risk matrix with a Plotly view using QWebEngineView
        self.risk_web_view = QWebEngineView()
        self.risk_layout.addWidget(self.risk_web_view)

        refresh_risk_btn = QPushButton("Refresh Risk Matrix")
        refresh_risk_btn.clicked.connect(self.update_risk_matrix)
        self.risk_layout.addWidget(refresh_risk_btn)

        # Initially load the risk matrix
        self.update_risk_matrix()

        # Add Risk Management Tab to QTabWidget
        self.tabs.addTab(self.risk_tab, "Risk Management")

        # Create Bill of Quantity Tab
        self.bill_tab = QWidget()
        self.bill_layout = QVBoxLayout(self.bill_tab)

        # Instantiate the Bill of Quantity model and table view
        self.bill_model = BillOfQuantityTableModel()
        self.bill_view = QTableView(self)
        self.bill_view.setModel(self.bill_model)

        # Create RBS (Resource Breakdown Structure) Tab
        self.rbs_tab = QWidget()
        self.rbs_layout = QVBoxLayout(self.rbs_tab)

        # Create RBS widget
        self.rbs_widget = RBSWidget(self.resource_model)
        self.rbs_layout.addWidget(self.rbs_widget)

        # Add refresh button
        refresh_rbs_btn = QPushButton("Refresh RBS Diagram")
        refresh_rbs_btn.clicked.connect(self.rbs_widget.refresh)
        self.rbs_layout.addWidget(refresh_rbs_btn)

        # Add zoom controls
        zoom_controls = QHBoxLayout()
        zoom_in_btn = QPushButton("Zoom In")
        zoom_out_btn = QPushButton("Zoom Out")
        zoom_in_btn.clicked.connect(lambda: self.rbs_widget.zoom_in())
        zoom_out_btn.clicked.connect(lambda: self.rbs_widget.zoom_out())
        zoom_controls.addWidget(zoom_in_btn)
        zoom_controls.addWidget(zoom_out_btn)

        # Add the RBS tab to the tab widget
        self.tabs.addTab(self.rbs_tab, "RBS Diagram")

        # Configure table view headers and resize behavior
        self.bill_view.horizontalHeader().setStretchLastSection(True)
        self.bill_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.bill_view.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.bill_view.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        self.bill_layout.addWidget(self.bill_view)

        # Set the delegate for the Unit of Measurement column (Column 2)
        self.unit_delegate = UnitDelegate()
        self.bill_view.setItemDelegateForColumn(2, self.unit_delegate)

        # Add control buttons (Add Row / Remove Row) for the Bill of Quantity tab.
        bill_button_layout = QHBoxLayout()
        self.add_bill_row_button = QPushButton("Add Row")
        self.add_bill_row_button.clicked.connect(self.add_bill_row)
        self.remove_bill_row_button = QPushButton("Remove Row")
        self.remove_bill_row_button.clicked.connect(self.remove_bill_row)
        bill_button_layout.addWidget(self.add_bill_row_button)
        bill_button_layout.addWidget(self.remove_bill_row_button)
        self.bill_layout.addLayout(bill_button_layout)

        # Add the Bill of Quantity tab to the healthy QTabWidget
        self.tabs.addTab(self.bill_tab, "Bill of Quantity")
                
        # Create Work Breakdown Structure (WBS) Tab
        self.wbs_tab = QWidget()
        self.wbs_layout = QVBoxLayout(self.wbs_tab)

        # Instantiate the WBSWidget with the activity model
        self.wbs_widget = WBSWidget(self.activity_model)
        self.wbs_layout.addWidget(self.wbs_widget)

        # Add a refresh button (optional) on the WBS page
        refresh_wbs_btn = QPushButton("Refresh WBS Diagram")
        refresh_wbs_btn.clicked.connect(self.wbs_widget.refresh)
        self.wbs_layout.addWidget(refresh_wbs_btn)

        # Add the WBS tab to your tab widget
        self.tabs.addTab(self.wbs_tab, "WBS Diagram")


        # Create Integration Tab
        self.integration_model = IntegrationTableModel(
            self.activity_model, 
            self.resource_model, 
            self.risk_model, 
            self.bill_model
        )
        self.integration_tab = IntegrationTab(
            self.integration_model,
            self.activity_model,
            self.resource_model,
            self.risk_model, 
            self.bill_model
        )
        self.tabs.addTab(self.integration_tab, "Integration View")

        # Create menu bar
        self.create_menu_bar()

        # Add shortcuts for copy, paste, delete
        self.copy_shortcut = QAction('Copy', self)
        self.copy_shortcut.setShortcut(QKeySequence.Copy)
        self.copy_shortcut.triggered.connect(self.copy_cells)
        self.addAction(self.copy_shortcut)

        self.paste_shortcut = QAction('Paste', self)
        self.paste_shortcut.setShortcut(QKeySequence.Paste)
        self.paste_shortcut.triggered.connect(self.paste_cells)
        self.addAction(self.paste_shortcut)

        self.delete_shortcut = QAction('Delete', self)
        self.delete_shortcut.setShortcut(QKeySequence.Delete)
        self.delete_shortcut.triggered.connect(self.delete_cells)
        self.addAction(self.delete_shortcut)

        # Add context menu
        self.table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_context_menu)

        # Connect double-click signal
        self.table_view.doubleClicked.connect(self.handle_double_click)

        # Initialize indentation tracking
        self.indentation_levels = []
        self.original_names = []

        # Connect signals
        self.activity_model.dataChanged.connect(self.on_data_changed)
        self.activity_model.rowsInserted.connect(self.update_resource_assigned_activity_delegate)
        self.activity_model.rowsRemoved.connect(self.update_resource_assigned_activity_delegate)
        self.activity_model.headerDataChanged.connect(self.update_resource_assigned_activity_delegate)

        # Calculate initial activity numbers and WBS IDs
        self.activity_model.recalculate_activity_numbers()

    def toggle_layout(self):
        self.use_fruchterman = not self.use_fruchterman
        self.update_pert_chart()

    def indent_resource(self):
        selected_rows = sorted(set(index.row() for index in self.resources_view.selectedIndexes()))
        if not selected_rows or selected_rows[0] == 0:  # Can't indent first row
            return

        # Get the parent row (row above the first selected row)
        parent_row = selected_rows[0] - 1
        parent_indent = self.resource_model.indentation_levels[parent_row]

        # Remove any existing parent-child relationships for selected rows
        for row in selected_rows:
            for parent, children in list(self.resource_model.parent_child_map.items()):
                if row in children:
                    children.remove(row)
                    if not children:
                        del self.resource_model.parent_child_map[parent]

        # Add all selected rows as children of the parent row
        if parent_row not in self.resource_model.parent_child_map:
            self.resource_model.parent_child_map[parent_row] = []
    
        for row in selected_rows:
            # Set indentation level one more than parent
            self.resource_model.indentation_levels[row] = parent_indent + 1
            # Add to parent's children if not already there
            if row not in self.resource_model.parent_child_map[parent_row]:
                self.resource_model.parent_child_map[parent_row].append(row)

        # Recalculate parent's resource parameters
        self.resource_model.recalc_parent_resources()
        self.resource_model.layoutChanged.emit()
        
        # Refresh RBS diagram if it exists
        if hasattr(self, 'rbs_widget'):
            self.rbs_widget.refresh()

    def outdent_resource(self):
        selected_rows = sorted(set(index.row() for index in self.resources_view.selectedIndexes()))
        for row in selected_rows:
            if self.resource_model.indentation_levels[row] > 0:
                self.resource_model.indentation_levels[row] -= 1
                
                # Update parent-child relationships
                for parent, children in list(self.resource_model.parent_child_map.items()):
                    if row in children:
                        children.remove(row)
                        if not children:
                            del self.resource_model.parent_child_map[parent]
                        break

        # Recalculate affected parent resources
        self.resource_model.recalc_parent_resources()
        self.resource_model.layoutChanged.emit()
        
        # Refresh RBS diagram if it exists
        if hasattr(self, 'rbs_widget'):
            self.rbs_widget.refresh()

    def indent_selected(self):
        selected_rows = sorted(set(index.row() for index in self.table_view.selectedIndexes()))
        if not selected_rows or selected_rows[0] == 0:  # Can't indent first row
            return

        # Get the parent row (row above the first selected row)
        parent_row = selected_rows[0] - 1
        parent_indent = self.activity_model.indentation_levels[parent_row]

        # Remove any existing parent-child relationships for selected rows
        for row in selected_rows:
            for parent, children in list(self.activity_model.parent_child_map.items()):
                if row in children:
                    children.remove(row)
                    if not children:
                        del self.activity_model.parent_child_map[parent]

        # Add all selected rows as children of the parent row
        if parent_row not in self.activity_model.parent_child_map:
            self.activity_model.parent_child_map[parent_row] = []
    
        for row in selected_rows:
            # Set indentation level one more than parent
            self.activity_model.indentation_levels[row] = parent_indent + 1
            # Add to parent's children if not already there
            if row not in self.activity_model.parent_child_map[parent_row]:
                self.activity_model.parent_child_map[parent_row].append(row)

        self.update_gantt_chart()
        self.activity_model.layoutChanged.emit()

    def outdent_selected(self):
        selected_rows = sorted(set(index.row() for index in self.table_view.selectedIndexes()))
        for row in selected_rows:
            if self.activity_model.indentation_levels[row] > 0:
                self.activity_model.indentation_levels[row] -= 1
                
                # Update parent-child relationships
                for parent, children in self.activity_model.parent_child_map.items():
                    if row in children:
                        children.remove(row)
                        if not children:
                            del self.activity_model.parent_child_map[parent]
                        break

        self.update_gantt_chart()
        self.activity_model.layoutChanged.emit()

    def toggle_selected_group(self):
        selected_rows = sorted(set(index.row() for index in self.table_view.selectedIndexes()))
        for row in selected_rows:
            if row in self.activity_model.parent_child_map:
                self.activity_model.expanded_states[row] = not self.activity_model.expanded_states[row]
                self.update_visible_rows()

    def handle_double_click(self, index):
        row = index.row()
        if row in self.activity_model.parent_child_map:
            self.activity_model.expanded_states[row] = not self.activity_model.expanded_states[row]
            self.update_visible_rows()

    def update_visible_rows(self):
        for parent_row, children in self.activity_model.parent_child_map.items():
            is_expanded = self.activity_model.expanded_states[parent_row]
            for child_row in children:
                self.table_view.setRowHidden(child_row, not is_expanded)

    def indent_selected(self):
        selected_rows = sorted(set(index.row() for index in self.table_view.selectedIndexes()))
        if not selected_rows or selected_rows[0] == 0:  # Can't indent first row
            return

        # Get the parent row (row above the first selected row)
        parent_row = selected_rows[0] - 1
        parent_indent = self.activity_model.indentation_levels[parent_row]

        # Remove any existing parent-child relationships for selected rows
        for row in selected_rows:
            for parent, children in list(self.activity_model.parent_child_map.items()):
                if row in children:
                    children.remove(row)
                    if not children:
                        del self.activity_model.parent_child_map[parent]

        # Add all selected rows as children of the parent row
        if parent_row not in self.activity_model.parent_child_map:
            self.activity_model.parent_child_map[parent_row] = []
    
        for row in selected_rows:
            # Set indentation level one more than parent
            self.activity_model.indentation_levels[row] = parent_indent + 1
            if row not in self.activity_model.parent_child_map[parent_row]:
                self.activity_model.parent_child_map[parent_row].append(row)

        # Recalculate parent's activity parameters based on its new children.
        self.activity_model.recalc_parent_activities()
        self.activity_model.recalculate_activity_numbers()

        self.update_gantt_chart()
        self.activity_model.layoutChanged.emit()

    def outdent_selected(self):
        selected_rows = sorted(set(index.row() for index in self.table_view.selectedIndexes()))
        for row in selected_rows:
            if self.activity_model.indentation_levels[row] > 0:
                self.activity_model.indentation_levels[row] -= 1
                
                # Update parent-child relationships
                for parent, children in self.activity_model.parent_child_map.items():
                    if row in children:
                        children.remove(row)
                        if not children:
                            del self.activity_model.parent_child_map[parent]
                        break

        # Recalculate any parent activities that might be affected by this change.
        self.activity_model.recalc_parent_activities()
        self.activity_model.recalculate_activity_numbers()

        self.update_gantt_chart()
        self.activity_model.layoutChanged.emit()

###### PART 2 CORRECTED CONTINUE TO PART 3 FROM HERE AND DOWN
    def create_menu_bar(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("File")

        save_action = QAction("Save Project", self)
        save_action.triggered.connect(self.save_project_to_json)
        file_menu.addAction(save_action)

        load_action = QAction("Load Project", self)
        load_action.triggered.connect(self.load_project_from_json)
        file_menu.addAction(load_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)


        view_menu = menubar.addMenu('View')

        table_action = QAction('Table View', self)
        table_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.table_tab))
        view_menu.addAction(table_action)

        resources_action = QAction('Resources', self)
        resources_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.resources_tab))
        view_menu.addAction(resources_action)

        gantt_action = QAction('Gantt Chart', self)
        gantt_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.gantt_tab))
        view_menu.addAction(gantt_action)

        pert_action = QAction('PERT Diagram', self)
        pert_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.pert_tab))
        view_menu.addAction(pert_action)

    def setup_gantt_chart(self):
        self.gantt_figure = Figure(figsize=(12, 6))
        self.canvas = FigureCanvas(self.gantt_figure)

        from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
        self.toolbar = NavigationToolbar(self.canvas, self)

        refresh_btn = QPushButton("Refresh Gantt Chart")
        refresh_btn.clicked.connect(self.update_gantt_chart)
        self.gantt_layout.addWidget(refresh_btn)

        self.add_custom_zoom_buttons_gantt()

    def add_custom_zoom_buttons_gantt(self):
        zoom_controls_layout = QHBoxLayout()
        
        zoom_in_btn = QPushButton("Zoom In")
        zoom_in_btn.clicked.connect(self.zoom_in_gantt)
        zoom_controls_layout.addWidget(zoom_in_btn)

        zoom_out_btn = QPushButton("Zoom Out")
        zoom_out_btn.clicked.connect(self.zoom_out_gantt)
        zoom_controls_layout.addWidget(zoom_out_btn)

        self.gantt_layout.addLayout(zoom_controls_layout)

    def setup_pert_chart(self):
        self.pert_figure = Figure(figsize=(12, 6))
        self.pert_canvas = FigureCanvas(self.pert_figure)

        from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
        self.pert_toolbar = NavigationToolbar(self.pert_canvas, self)

        refresh_pert_btn = QPushButton("Refresh PERT Diagram")
        refresh_pert_btn.clicked.connect(self.update_pert_chart)
        self.pert_layout.addWidget(refresh_pert_btn)

        self.add_custom_zoom_buttons_pert()

    def add_custom_zoom_buttons_pert(self):
        zoom_controls_layout = QHBoxLayout()
        
        zoom_in_btn = QPushButton("Zoom In")
        zoom_in_btn.clicked.connect(self.zoom_in_pert)
        zoom_controls_layout.addWidget(zoom_in_btn)

        zoom_out_btn = QPushButton("Zoom Out")
        zoom_out_btn.clicked.connect(self.zoom_out_pert)
        zoom_controls_layout.addWidget(zoom_out_btn)

        self.pert_layout.addLayout(zoom_controls_layout)

    def add_row(self):
        row_count = self.activity_model.rowCount()
        self.activity_model.insertRows(row_count, 1)
        self.indentation_levels.append(0)
        self.original_names.append("")
        self.activity_model.recalculate_activity_numbers()
        self.calculate_cpm()
        self.update_gantt_chart()
        self.update_pert_chart()

    def remove_row(self):
        selected_indexes = self.table_view.selectedIndexes()
        if not selected_indexes:
            QMessageBox.information(self, "Remove Row", "Please select one or more rows to remove.")
            return

        rows_to_remove = sorted(set(index.row() for index in selected_indexes), reverse=True)
        for row in rows_to_remove:
            self.activity_model.removeRows(row, 1)
            if row < len(self.indentation_levels):
                del self.indentation_levels[row]
                del self.original_names[row]
        
        self.activity_model.recalculate_activity_numbers()
        self.calculate_cpm()
        self.update_gantt_chart()
        self.update_pert_chart()

    def add_resource(self):
        row_count = self.resource_model.rowCount()
        self.resource_model.insertRows(row_count, 1)
        self.update_resource_assigned_activity_delegate()

    def remove_resource(self):
        selected_indexes = self.resources_view.selectedIndexes()
        if not selected_indexes:
            QMessageBox.information(self, "Remove Resource", "Please select one or more resources to remove.")
            return

        rows_to_remove = sorted(set(index.row() for index in selected_indexes), reverse=True)
        for row in rows_to_remove:
            self.resource_model.removeRows(row, 1)

    def on_data_changed(self, topLeft, bottomRight, roles):
        if not roles or Qt.EditRole in roles:
            row = topLeft.row()
            column = topLeft.column()
            
            if column in [4, 7]:  # Predecessor (col 4) or Duration (col 7) changed
                self.calculate_end_date(row)
                
                # ✅ propagate upwards
                self.activity_model.recalc_ancestors(row)

                self.calculate_cpm()
                self.update_gantt_chart()
                self.update_pert_chart()
            elif column == 5:  # Start Date changed
                self.calculate_end_date(row)
                self.update_dependent_start_dates()
                self.calculate_cpm()
                self.update_gantt_chart()
                self.update_pert_chart()
        
        self.update_resource_assigned_activity_delegate()

    def calculate_end_date(self, row):
        try:
            start_date = self.activity_model._data[row][5]  # Start Date
            duration_str = self.activity_model._data[row][7]  # Duration
            if isinstance(start_date, QDateTime) and duration_str:
                try:
                    duration = int(duration_str)
                except Exception as e:
                    print(f"Invalid duration value at row {row}: {duration_str} ({e})")
                    duration = 0  # or simply return if duration is invalid

                # Only calculate if duration is positive
                if duration > 0:
                    start_datetime = start_date.toPyDateTime()
                    end_datetime = start_datetime + timedelta(days=duration)
                    self.activity_model._data[row][6] = end_datetime.strftime("%Y-%m-%d %H:%M")  # End Date col 6
                    end_date_index = self.activity_model.index(row, 6)
                    self.activity_model.dataChanged.emit(end_date_index, end_date_index, [Qt.DisplayRole])

                # Update successor start dates safely.
                task_id = str(row + 1)
                self.update_successor_start_dates(task_id, end_datetime)
        except Exception as e:
            print(f"Error in calculate_end_date (row {row}): {e}")

    def update_successor_start_dates(self, task_id, end_date):
        for row in range(self.activity_model.rowCount()):
            predecessor_str = str(self.activity_model._data[row][4])  # Predecessor column
            if predecessor_str and task_id in predecessor_str.split(';'):
                predecessors = predecessor_str.split(';')
                latest_end_date = end_date

                # Find the latest end date among all predecessors
                for pred_id in predecessors:
                    if pred_id.strip():
                        try:
                            pred_row = int(pred_id.strip()) - 1
                            pred_end_date_str = self.activity_model._data[pred_row][6]  # End Date
                            if pred_end_date_str:
                                pred_end_date = datetime.strptime(pred_end_date_str, "%Y-%m-%d %H:%M")
                                if pred_end_date > latest_end_date:
                                    latest_end_date = pred_end_date
                        except (ValueError, IndexError):
                            continue

                # Update the start date
                current_start = self.activity_model._data[row][5]  # Start Date
                if isinstance(current_start, QDateTime):
                    current_start_py = current_start.toPyDateTime()
                    if latest_end_date > current_start_py:
                        new_start = QDateTime.fromString(
                            latest_end_date.strftime("%Y-%m-%d %H:%M"),
                            "yyyy-MM-dd HH:mm"
                        )
                        self.activity_model._data[row][5] = new_start
                        start_index = self.activity_model.index(row, 5)
                        self.activity_model.dataChanged.emit(start_index, start_index, [Qt.DisplayRole])
                        self.calculate_end_date(row)

    def update_dependent_start_dates(self):
        for row in range(self.activity_model.rowCount()):
            predecessor_str = str(self.activity_model._data[row][4])  # Predecessor column
            if predecessor_str:
                predecessors = predecessor_str.split(';')
                latest_end_date = None

                for pred_id in predecessors:
                    if pred_id.strip():
                        try:
                            pred_row = int(pred_id.strip()) - 1
                            pred_end_date_str = self.activity_model._data[pred_row][6]  # End Date
                            if pred_end_date_str:
                                pred_end_date = datetime.strptime(pred_end_date_str, "%Y-%m-%d %H:%M")
                                if latest_end_date is None or pred_end_date > latest_end_date:
                                    latest_end_date = pred_end_date
                        except (ValueError, IndexError):
                            continue

                if latest_end_date:
                    current_start = self.activity_model._data[row][5]  # Start Date
                    if isinstance(current_start, QDateTime):
                        current_start_py = current_start.toPyDateTime()
                        if latest_end_date > current_start_py:
                            new_start = QDateTime.fromString(
                                latest_end_date.strftime("%Y-%m-%d %H:%M"),
                                "yyyy-MM-dd HH:mm"
                            )
                            self.activity_model._data[row][5] = new_start
                            start_index = self.activity_model.index(row, 5)
                            self.activity_model.dataChanged.emit(start_index, start_index, [Qt.DisplayRole])
                            self.calculate_end_date(row)

    def calculate_successors(self):
        for row in range(self.activity_model.rowCount()):
            current_id = str(row + 1)
            successors = []
            
            # Find all tasks that have this task as a predecessor
            for other_row in range(self.activity_model.rowCount()):
                if other_row != row:
                    predecessor_str = str(self.activity_model._data[other_row][4])
                    if predecessor_str and current_id in predecessor_str.split(';'):
                        successors.append(str(other_row + 1))

            # Update Successors column
            successors_text = ';'.join(successors)
            self.activity_model._data[row][6] = successors_text
            successor_index = self.activity_model.index(row, 8)
            self.activity_model.dataChanged.emit(successor_index, successor_index, [Qt.DisplayRole])

    def calculate_cpm(self):
        activities = {}
        id_to_row = {}

        # ---- Build activity map ----
        for row in range(self.activity_model.rowCount()):
            row_data = self.activity_model._data[row]
            activity_id = row_data[0]
            id_to_row[activity_id] = row

            try:
                duration = float(row_data[7]) if row_data[7] else 0.0
            except ValueError:
                duration = 0.0

            predecessors = [
                p.strip() for p in str(row_data[4]).split(";") if p.strip()
            ]

            activities[activity_id] = {
                "duration": duration,
                "predecessors": predecessors,
                "successors": [],
            }

        # ---- Build successor lists ----
        for aid, data in activities.items():
            for pid in data["predecessors"]:
                if pid in activities:
                    activities[pid]["successors"].append(aid)

        # ---- Topological sort with cycle detection ----
        sorted_ids = []
        temp = set()
        perm = set()

        def visit(aid):
            if aid in perm:
                return
            if aid in temp:
                raise Exception("Cycle detected in activity dependencies.")
            temp.add(aid)
            for p in activities[aid]["predecessors"]:
                if p in activities:
                    visit(p)
            temp.remove(aid)
            perm.add(aid)
            sorted_ids.append(aid)

        try:
            for aid in activities:
                if aid not in perm:
                    visit(aid)
        except Exception as e:
            QMessageBox.critical(self, "CPM Error", str(e))
            return

        # ---- Forward pass (ES / EF) ----
        ES, EF = {}, {}

        for aid in sorted_ids:
            preds = activities[aid]["predecessors"]
            ES[aid] = max((EF[p] for p in preds if p in EF), default=0)
            EF[aid] = ES[aid] + activities[aid]["duration"]

        # ---- Backward pass (LS / LF) ----
        project_duration = max(EF.values(), default=0)
        LS, LF = {}, {}

        for aid in reversed(sorted_ids):
            succs = activities[aid]["successors"]
            LF[aid] = (
                min(LS[s] for s in succs if s in LS)
                if succs else project_duration
            )
            LS[aid] = LF[aid] - activities[aid]["duration"]

        # ---- Write results back to model ----
        for aid in activities:
            row = id_to_row[aid]
            self.activity_model._data[row][9] = ES.get(aid, 0)
            self.activity_model._data[row][10] = EF.get(aid, 0)
            self.activity_model._data[row][11] = LS.get(aid, 0)
            self.activity_model._data[row][12] = LF.get(aid, 0)

            # Update successors column for display
            self.activity_model._data[row][8] = ";".join(
                activities[aid]["successors"]
            )

            top = self.activity_model.index(row, 9)
            bottom = self.activity_model.index(row, 12)
            self.activity_model.dataChanged.emit(top, bottom, [Qt.DisplayRole])

    def update_risk_matrix(self):
        # Define axis categories for the matrix
        likelihood = ['Very Likely', 'Likely', 'Possible', 'Unlikely', 'Very Unlikely']
        severity = ['Negligible', 'Minor', 'Moderate', 'Significant', 'Severe']

        # Create an empty risk_text_matrix (5x5) for holding risk ID and name per cell
        risk_text_matrix = [['' for _ in range(5)] for _ in range(5)]

        # Iterate through each risk entry from the RiskTableModel
        # Each risk entry is assumed to have the following structure:
        # [ID, Name, Category, Probability, Impact, Rating]
        for risk in self.risk_model._data:
            risk_id = risk[0]
            risk_name = risk[1]
            try:
                prob = int(risk[3])
            except Exception:
                prob = 1
            try:
                impact = int(risk[4])
            except Exception:
                impact = 1

            # Map probability to row index (with 5 = top row "Very Likely")
            row_index = 5 - prob  # e.g., if prob=5 then row_index=0; if prob=1 then row_index=4
            # Map impact to column index (1-based to 0-based)
            col_index = impact - 1

            # Build the risk detail text for this cell ("ID: Name")
            entry_text = f"{risk_id}: {risk_name}"
            if risk_text_matrix[row_index][col_index]:
                risk_text_matrix[row_index][col_index] += "\n" + entry_text
            else:
                risk_text_matrix[row_index][col_index] = entry_text

        # Create a dummy z matrix to define the cells
        # We use fixed values so the color mapping appears as before.
        z_matrix = []
        for i in range(5):
            z_matrix.append([1, 2, 3, 4, 5])

        # Create the heatmap with risk_text_matrix as the cell text
        fig = go.Figure(data=go.Heatmap(
            z=z_matrix,
            x=severity,
            y=likelihood,
            text=risk_text_matrix,
            texttemplate="%{text}",
            textfont={"size": 12},
            colorscale=[[0, '#008000'], [0.25, '#90EE90'],
                        [0.5, '#FFFF00'], [0.75, '#FFA500'],
                        [1, '#FF0000']],
            showscale=False
        ))

        fig.update_layout(
            title={
                'text': 'Risk Assessment Matrix',
                'font': {'size': 24},
                'y': 0.95,
                'x': 0.5,
                'xanchor': 'center',
                'yanchor': 'top'
            },
            xaxis_title="Severity",
            yaxis_title="Likelihood",
            xaxis={'side': 'top'},
            width=800,
            height=600,
            font=dict(size=12)
        )

        # Convert the Plotly figure to HTML and display it in the QWebEngineView
        html = fig.to_html(include_plotlyjs='cdn')
        self.risk_web_view.setHtml(html)

    def show_context_menu(self, position):
        menu = QMenu()

        copy_action = menu.addAction("Copy")
        paste_action = menu.addAction("Paste")
        delete_action = menu.addAction("Delete")

        action = menu.exec_(self.table_view.viewport().mapToGlobal(position))
        if action == copy_action:
            self.copy_cells()
        elif action == paste_action:
            self.paste_cells()
        elif action == delete_action:
            self.delete_cells()

    def copy_cells(self):
        selected_indexes = self.table_view.selectionModel().selectedIndexes()
        if not selected_indexes:
            return

        # Sort selected indexes
        selected_indexes = sorted(selected_indexes, key=lambda x: (x.row(), x.column()))
        
        # Determine the range
        start_row = selected_indexes[0].row()
        start_col = selected_indexes[0].column()
        end_row = selected_indexes[-1].row()
        end_col = selected_indexes[-1].column()

        # Extract data
        clipboard_text = ""
        for row in range(start_row, end_row + 1):
            row_data = []
            for col in range(start_col, end_col + 1):
                index = self.activity_model.index(row, col)
                data = self.activity_model.data(index, Qt.DisplayRole)
                row_data.append(data if data else "")
            clipboard_text += '\t'.join(row_data) + '\n'

        # Set clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(clipboard_text.strip())

    def paste_cells(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if not text:
            return

        selected_indexes = self.table_view.selectionModel().selectedIndexes()
        if not selected_indexes:
            return

        # Block model signals during bulk paste to avoid repeated recalculations.
        from PyQt5.QtCore import QSignalBlocker
        with QSignalBlocker(self.activity_model):
            start_row = selected_indexes[0].row()
            start_col = selected_indexes[0].column()

            # Split clipboard text into rows and columns
            rows = text.split('\n')
            for i, row_text in enumerate(rows):
                columns = row_text.split('\t')
                for j, cell_text in enumerate(columns):
                    row = start_row + i
                    col = start_col + j

                    if row >= self.activity_model.rowCount() or col >= self.activity_model.columnCount():
                        continue  # Skip if out of bounds

                    if col in [0, 1, 2, 6, 8, 9, 10, 11, 12]:
                        continue  # Skip read-only columns

                    index = self.activity_model.index(row, col)
                    if col == 5:  # Start Date column
                        # Try to convert cell_text to QDateTime
                        date = QDateTime.fromString(cell_text, "yyyy-MM-dd HH:mm")
                        if date.isValid():
                            self.activity_model.setData(index, date, Qt.EditRole)
                    else:
                        self.activity_model.setData(index, cell_text, Qt.EditRole)

        # Now trigger recalculations only once after pasting
        self.calculate_cpm()
        self.update_gantt_chart()
        self.update_pert_chart()

    def delete_cells(self):
        selected_indexes = self.table_view.selectionModel().selectedIndexes()
        if not selected_indexes:
            return

        for index in selected_indexes:
            col = index.column()
            if col in [0, 1, 2, 6, 8, 9, 10, 11, 12]:
                continue  # Skip read-only columns
            if col == 5:  # Start Date column
                self.activity_model.setData(index, QDateTime.currentDateTime(), Qt.EditRole)
            else:
                self.activity_model.setData(index, "", Qt.EditRole)

    def update_gantt_chart(self):
        self.gantt_figure.clear()
        
        # Set professional style (using built-in matplotlib style)
        plt.style.use('ggplot')  # Professional alternative style
        
        # Style parameters
        task_height = 0.4
        parent_color = '#2c5f8a'  # Dark blue for parent tasks
        child_color = '#5ab1ef'   # Light blue for child tasks
        edge_color = '#1a2f40'    # Dark border color
        grid_alpha = 0.2
        font_size = 9

        # Prepare data
        display_rows = []
        tasks = []
        start_dates = []
        end_dates = []
        
        for row in range(self.activity_model.rowCount()):
            name = str(self.activity_model._data[row][3])
            if not name.strip():
                continue
            start_date = self.activity_model._data[row][5]
            if not isinstance(start_date, QDateTime):
                continue
            end_date_str = str(self.activity_model._data[row][6])
            if not end_date_str:
                continue
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            
            display_rows.append(row)
            tasks.append(name)
            start_dates.append(mdates.date2num(start_date.toPyDateTime()))
            end_dates.append(mdates.date2num(end_date))

        if not tasks:
            ax = self.gantt_figure.add_subplot(111)
            ax.text(0.5, 0.5, 'No tasks available to display.',
                    horizontalalignment='center', verticalalignment='center')
            ax.axis('off')
            self.canvas.draw()
            return

        ax = self.gantt_figure.add_subplot(111)
        y_positions = np.arange(len(tasks))
        
        # Draw tasks with professional styling
        for i, model_row in enumerate(display_rows):
            start = start_dates[i]
            end_ = end_dates[i]
            duration = end_ - start
            
            if model_row in self.activity_model.parent_child_map:
                # Parent tasks - thicker bars with outline
                ax.barh(y=i, width=duration, left=start, 
                        height=task_height*1.5, color=parent_color,
                        edgecolor=edge_color, linewidth=0.7)
            else:
                # Child tasks - standard bars
                ax.barh(y=i, width=duration, left=start,
                        height=task_height, color=child_color,
                        edgecolor=edge_color, linewidth=0.5)

        # Format axes
        ax.set_yticks(y_positions)
        ax.set_yticklabels(tasks, fontsize=font_size, fontfamily='sans-serif')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b\n%Y'))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
        ax.tick_params(axis='x', labelsize=font_size-1)
        ax.set_xlabel('Timeline', fontsize=font_size+1, labelpad=10)
        
        # Grid styling
        ax.xaxis.grid(True, linestyle='--', alpha=grid_alpha)
        ax.yaxis.grid(False)
        ax.set_axisbelow(True)  # Grid behind bars
        
        # Clean up chart borders
        for spine in ['top', 'right', 'left']:
            ax.spines[spine].set_visible(False)
        ax.spines['bottom'].set_color('#d0d0d0')

        # Set date range limits
        if start_dates and end_dates:
            buffer_days = 2
            min_date = mdates.num2date(min(start_dates)) - timedelta(days=buffer_days)
            max_date = mdates.num2date(max(end_dates)) + timedelta(days=buffer_days)
            ax.set_xlim(min_date, max_date)

        # Chart title
        ax.set_title('Project Schedule', 
                    pad=15, 
                    fontsize=font_size+3,
                    fontweight='semibold',
                    color='#2a3b4d')

        # Layout adjustments
        self.gantt_figure.tight_layout()
        plt.subplots_adjust(left=0.35)  # Space for task labels
        
        # Invert y-axis for top-down hierarchy
        ax.invert_yaxis()
        
        self.canvas.draw()

    def add_custom_zoom_buttons_gantt(self):
        zoom_controls_layout = QHBoxLayout()
        
        zoom_in_btn = QPushButton("Zoom In")
        zoom_in_btn.clicked.connect(self.zoom_in_gantt)
        zoom_controls_layout.addWidget(zoom_in_btn)

        zoom_out_btn = QPushButton("Zoom Out")
        zoom_out_btn.clicked.connect(self.zoom_out_gantt)
        zoom_controls_layout.addWidget(zoom_out_btn)

        self.gantt_layout.addLayout(zoom_controls_layout)

    def update_resource_assigned_activity_delegate(self):
        # Update the Assigned Activity delegate to reflect current activities
        self.assigned_activity_delegate = AssignedActivityDelegate(self.activity_model)
        self.resources_view.setItemDelegateForColumn(7, self.assigned_activity_delegate)

    def update_pert_chart(self):
        self.pert_figure.clear()
        ax = self.pert_figure.add_subplot(111)
        
        try:
            G = nx.DiGraph()
            node_data = {}
            valid_nodes = []
            critical_path_nodes = []

            # Build graph with data validation
            for row in range(self.activity_model.rowCount()):
                activity_id = str(row + 1)
                try:
                    es = int(self.activity_model._data[row][9])     # ES
                    ef = int(self.activity_model._data[row][10])    # EF
                    ls = int(self.activity_model._data[row][11])    # LS
                    lf = int(self.activity_model._data[row][12])    # LF
                    name = str(self.activity_model._data[row][3])
                    
                    if not name.strip():
                        continue
                        
                    node_data[activity_id] = {'es': es, 'ef': ef, 'ls': ls, 'lf': lf, 'name': name}
                    valid_nodes.append(activity_id)
                    G.add_node(activity_id)
                    
                    # Check if node is on critical path
                    if es == ls and ef == lf:
                        critical_path_nodes.append(activity_id)
                    
                    predecessors = str(self.activity_model._data[row][4]).split(';')
                    for pred in predecessors:
                        if pred.strip() and pred.strip() in valid_nodes:
                            G.add_edge(pred.strip(), activity_id)

                except (ValueError, IndexError):
                    continue

            if not valid_nodes:
                ax.text(0.5, 0.5, 'No valid activities to display', 
                        ha='center', va='center')
                ax.axis('off')
                self.pert_canvas.draw()
                return

            # Identify critical path edges
            critical_edges = []
            for u, v in G.edges():
                u_data = node_data[u]
                v_data = node_data[v]
                if (u in critical_path_nodes and v in critical_path_nodes and 
                    u_data['ef'] == v_data['es']):
                    critical_edges.append((u, v))

            # Calculate positions using a layered approach
            # Group nodes by their early start time
            nodes_by_es = {}
            for node in valid_nodes:
                es = node_data[node]['es']
                if es not in nodes_by_es:
                    nodes_by_es[es] = []
                nodes_by_es[es].append(node)
            
            # Sort early start times
            sorted_es_times = sorted(nodes_by_es.keys())
            
            # Calculate positions
            pos = {}
            max_nodes_per_layer = max(len(nodes) for nodes in nodes_by_es.values())
            
            # Set figure size based on number of nodes
            fig_width = max(8, len(sorted_es_times) * 1.5)
            fig_height = max(6, max_nodes_per_layer * 1.2)
            self.pert_figure.set_size_inches(fig_width, fig_height)
            
            # Calculate positions with more spacing
            for i, es_time in enumerate(sorted_es_times):
                nodes = nodes_by_es[es_time]
                
                # Sort nodes within same ES by their EF
                nodes.sort(key=lambda n: node_data[n]['ef'])
                
                # Further sort to prioritize critical path nodes
                nodes.sort(key=lambda n: n not in critical_path_nodes)
                
                # Position nodes with the same early start time in a column
                # Critical path nodes are positioned in the middle
                for j, node in enumerate(nodes):
                    # Normalize position to [0,1] range
                    x = i / max(len(sorted_es_times) - 1, 1)
                    
                    # Calculate y position
                    if node in critical_path_nodes:
                        # Place critical nodes in the middle
                        y = 0.5
                    else:
                        # Distribute non-critical nodes above and below
                        offset = (j + 1) / (len(nodes) + 1) - 0.5
                        y = 0.5 + offset * 0.8  # Scale to avoid edges
                    
                    pos[node] = (x, y)
            
            # Adjust positions to avoid overlaps
            # Simple jitter for nodes with same position
            for node in valid_nodes:
                if node in pos:
                    x, y = pos[node]
                    # Add small random jitter to non-critical nodes
                    if node not in critical_path_nodes:
                        pos[node] = (x, y + np.random.uniform(-0.05, 0.05))
            
            # Draw nodes - make critical path nodes larger
            for node, (x, y) in pos.items():
                data = node_data[node]
                
                # Determine if node is on critical path
                is_critical = node in critical_path_nodes
                
                # Set node properties based on critical path
                if is_critical:
                    node_color = 'lightcoral'
                    node_width = 0.06
                    node_height = 0.04
                    edge_width = 2
                    font_size = 7
                else:
                    node_color = 'lightblue'
                    node_width = 0.04
                    node_height = 0.03
                    edge_width = 1
                    font_size = 6
                
                # Draw node as an ellipse (oval)
                ellipse = patches.Ellipse((x, y), node_width*2, node_height*2, 
                                        color=node_color, ec='black', lw=edge_width)
                ax.add_patch(ellipse)
                
                # Add activity ID and name above the node
                ax.text(x, y + node_height + 0.01, f"{node}: {data['name']}", 
                        ha='center', va='bottom', fontsize=font_size, 
                        fontweight='bold' if is_critical else 'normal')
                
                # Add ES, EF, LS, LF values inside the node
                ax.text(x, y, 
                        f"ES:{data['es']} EF:{data['ef']}\nLS:{data['ls']} LF:{data['lf']}",
                        ha='center', va='center', fontsize=font_size-1)

            # Draw edges with arrowheads
            for u, v in G.edges():
                u_pos = pos[u]
                v_pos = pos[v]
                
                # Calculate edge path
                dx = v_pos[0] - u_pos[0]
                dy = v_pos[1] - u_pos[1]
                dist = math.hypot(dx, dy)
                if dist == 0:
                    continue
                
                # Determine if edge is on critical path
                is_critical_edge = (u, v) in critical_edges
                
                # Set edge properties based on critical path
                if is_critical_edge:
                    edge_color = 'red'
                    edge_width = 2
                    edge_style = '-'
                    arrow_style = '->'
                    connection_style = "arc3,rad=0"  # Straight line for critical path
                else:
                    edge_color = 'gray'
                    edge_width = 1
                    edge_style = '--'
                    arrow_style = '->'
                    connection_style = "arc3,rad=0.2"  # Curved for non-critical
                
                # Adjust start and end points to account for oval shape
                node_width = 0.06 if u in critical_path_nodes else 0.04
                node_height = 0.04 if u in critical_path_nodes else 0.03
                
                start_x = u_pos[0] + (dx/dist)*node_width
                start_y = u_pos[1] + (dy/dist)*node_height
                
                node_width = 0.06 if v in critical_path_nodes else 0.04
                node_height = 0.04 if v in critical_path_nodes else 0.03
                
                end_x = v_pos[0] - (dx/dist)*node_width
                end_y = v_pos[1] - (dy/dist)*node_height
                
                # Draw the edge
                ax.annotate("",
                    xy=(end_x, end_y),
                    xytext=(start_x, start_y),
                    arrowprops=dict(arrowstyle=arrow_style, color=edge_color, 
                                    lw=edge_width, linestyle=edge_style,
                                    connectionstyle=connection_style))

            # Add legend for critical path
            critical_patch = patches.Patch(color='lightcoral', label='Critical Path Node')
            normal_patch = patches.Patch(color='lightblue', label='Normal Node')
            ax.legend(handles=[critical_patch, normal_patch], loc='upper right')

            # Add title
            ax.set_title("PERT Network Diagram (Critical Path Highlighted)")
            
            # Set axis limits with some padding
            ax.set_xlim(-0.05, 1.05)
            ax.set_ylim(-0.05, 1.05)
            ax.set_axis_off()
            
            self.pert_canvas.draw()

        except Exception as e:
            import traceback
            error_msg = f'Error rendering PERT chart: {str(e)}\n{traceback.format_exc()}'
            print(error_msg)  # Print to console for debugging
            ax.text(0.5, 0.5, error_msg, 
                    ha='center', va='center', color='red', fontsize=8)
            ax.axis('off')
            self.pert_canvas.draw()

    def zoom_in_gantt(self):
        if not self.gantt_figure.axes:
            return
        ax = self.gantt_figure.axes[0]
        x_min, x_max = ax.get_xlim()
        zoom_factor = 0.8
        new_width = (x_max - x_min) * zoom_factor
        center = (x_max + x_min) / 2
        ax.set_xlim(center - new_width / 2, center + new_width / 2)
        self.canvas.draw()

    def zoom_out_gantt(self):
        if not self.gantt_figure.axes:
            return
        ax = self.gantt_figure.axes[0]
        x_min, x_max = ax.get_xlim()
        zoom_factor = 1.25
        new_width = (x_max - x_min) * zoom_factor
        center = (x_max + x_min) / 2
        ax.set_xlim(center - new_width / 2, center + new_width / 2)
        self.canvas.draw()

    def zoom_in_pert(self):
        if not self.pert_figure.axes:
            return
        ax = self.pert_figure.axes[0]
        x_min, x_max = ax.get_xlim()
        y_min, y_max = ax.get_ylim()
        zoom_factor = 0.8
        new_width = (x_max - x_min) * zoom_factor
        new_height = (y_max - y_min) * zoom_factor
        center_x = (x_max + x_min) / 2
        center_y = (y_max + y_min) / 2
        ax.set_xlim(center_x - new_width / 2, center_x + new_width / 2)
        ax.set_ylim(center_y - new_height / 2, center_y + new_height / 2)
        self.pert_canvas.draw()

    def zoom_out_pert(self):
        if not self.pert_figure.axes:
            return
        ax = self.pert_figure.axes[0]
        x_min, x_max = ax.get_xlim()
        y_min, y_max = ax.get_ylim()
        zoom_factor = 1.25
        new_width = (x_max - x_min) * zoom_factor
        new_height = (y_max - y_min) * zoom_factor
        center_x = (x_max + x_min) / 2
        center_y = (y_max + y_min) / 2
        ax.set_xlim(center_x - new_width / 2, center_x + new_width / 2)
        ax.set_ylim(center_y - new_height / 2, center_y + new_height / 2)
        self.pert_canvas.draw()

    def add_bill_row(self):
        row_count = self.bill_model.rowCount()
        self.bill_model.insertRows(row_count, 1)

    def remove_bill_row(self):
        selected_indexes = self.bill_view.selectedIndexes()
        if not selected_indexes:
            QMessageBox.information(self, "Remove Row", "Please select one or more rows to remove.")
            return
        rows_to_remove = sorted(set(index.row() for index in selected_indexes), reverse=True)
        for row in rows_to_remove:
            self.bill_model.removeRows(row, 1)    

    def save_project_to_json(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Project", "", "Project Files (*.json)"
        )
        if not filename:
            return

        data = {
            # ---------- FILE FORMAT VERSION ----------
            # v1: row-based IDs (legacy)
            # v2: GUID-based IDs (current)
            "version": 3,

            # ---------- ACTIVITIES ----------
            # Column 0 contains the GUID (authoritative ID)
            "activities": [
                [qdatetime_to_str(v) for v in row]
                for row in self.activity_model._data
            ],

            # UI hierarchy (row-based, NOT identity)
            "activity_hierarchy": {
                str(k): v for k, v in self.activity_model.parent_child_map.items()
            },
            "activity_indent": list(self.activity_model.indentation_levels),

            # ---------- RESOURCES ----------
            "resources": self.resource_model._data,
            "resource_hierarchy": {
                str(k): v for k, v in self.resource_model.parent_child_map.items()
            },
            "resource_indent": list(self.resource_model.indentation_levels),

            # ---------- RISKS ----------
            "risks": self.risk_model._data,

            # ---------- BILL OF QUANTITY ----------
            "boq": self.bill_model._data,

            # ---------- INTEGRATION (GUID-based references) ----------
            "integration": self.integration_model.relationships,
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        QMessageBox.information(self, "Saved", "Project saved successfully.")

    def recalculate_all_end_dates(self):
        for row in range(self.activity_model.rowCount()):
            self.calculate_end_date(row)

    def load_project_from_json(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Project", "", "Project Files (*.json)"
        )
        if not filename:
            return

        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        # ---- Activities ----
        self.activity_model.beginResetModel()

        # Restore activity data (GUIDs are in column 0 and must remain untouched)
        self.activity_model._data = []
        for row in data.get("activities", []):
            loaded_row = [str_to_qdatetime(v) for v in row]

            # Clear derived fields so they are always freshly computed on load.
            # Cols 1 & 2: Activity No and WBS ID (recalculated below)
            # Cols 9-12:  ES, EF, LS, LF (recalculated by calculate_cpm)
            for col in (1, 2, 9, 10, 11, 12):
                if col < len(loaded_row):
                    loaded_row[col] = ""

            self.activity_model._data.append(loaded_row)


        row_count = len(self.activity_model._data)

        # Restore indentation safely
        self.activity_model.indentation_levels = data.get(
            "activity_indent", [0] * row_count
        )[:row_count]

        # Restore hierarchy (row-based, UI concern)
        raw_hierarchy = data.get("activity_hierarchy", {})
        self.activity_model.parent_child_map = {}

        for parent_str, children in raw_hierarchy.items():
            try:
                parent = int(parent_str)
            except ValueError:
                continue

            if 0 <= parent < row_count:
                valid_children = [
                    c for c in children
                    if isinstance(c, int) and 0 <= c < row_count
                ]
                if valid_children:
                    self.activity_model.parent_child_map[parent] = valid_children

        self.activity_model.expanded_states = [True] * row_count
        self.activity_model.endResetModel()

        # ---- Resources ----
        self.resource_model.beginResetModel()
        self.resource_model._data = data.get("resources", [])

        res_row_count = len(self.resource_model._data)
        self.resource_model.indentation_levels = data.get(
            "resource_indent", [0] * res_row_count
        )[:res_row_count]

        raw_res_hierarchy = data.get("resource_hierarchy", {})
        self.resource_model.parent_child_map = {}

        for parent_str, children in raw_res_hierarchy.items():
            try:
                parent = int(parent_str)
            except ValueError:
                continue

            if 0 <= parent < res_row_count:
                valid_children = [
                    c for c in children
                    if isinstance(c, int) and 0 <= c < res_row_count
                ]
                if valid_children:
                    self.resource_model.parent_child_map[parent] = valid_children

        self.resource_model.expanded_states = [True] * res_row_count
        self.resource_model.endResetModel()

        # ---- Risks ----
        self.risk_model.beginResetModel()
        self.risk_model._data = data.get("risks", [])
        self.risk_model.endResetModel()

        # ---- BOQ ----
        self.bill_model.beginResetModel()
        self.bill_model._data = data.get("boq", [])
        self.bill_model.endResetModel()

        # ---- Integration (GUID-based, no remapping needed) ----
        self.integration_model.relationships = data.get("integration", {})
        self.integration_model.layoutChanged.emit()

        # ---- Recalculate derived values (CRITICAL ORDER) ----
        self.recalculate_all_end_dates()
        self.activity_model.recalc_parent_activities()
        self.activity_model.recalculate_activity_numbers()   # Must run before CPM display
        self.calculate_cpm()

        # ---- Refresh visuals ----
        self.update_gantt_chart()
        self.update_pert_chart()
        self.update_risk_matrix()

        QMessageBox.information(self, "Loaded", "Project loaded successfully.")


class GroupDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.column() == 1:  # Name column
            row = index.row()
            model = index.model()
            
            # Draw expand/collapse icon if row is a parent
            if row in model.parent_child_map:
                icon_rect = option.rect.adjusted(0, 0, 20, 0)
                if model.expanded_states[row]:
                    painter.drawText(icon_rect, Qt.AlignLeft | Qt.AlignVCenter, "▼")
                else:
                    painter.drawText(icon_rect, Qt.AlignLeft | Qt.AlignVCenter, "▶")
                
                # Adjust the rest of the text
                option.rect.adjust(20, 0, 0, 0)
                
        super().paint(painter, option, index)


class DateTimeDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        if index.column() == 5:  # Start Date column
            editor = QDateTimeEdit(parent)
            editor.setDisplayFormat("yyyy-MM-dd HH:mm")
            editor.setCalendarPopup(True)
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if index.column() == 5 and isinstance(editor, QDateTimeEdit):
            date_str = index.model().data(index, Qt.EditRole)
            date = QDateTime.fromString(date_str, "yyyy-MM-dd HH:mm")
            editor.setDateTime(date)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if index.column() == 5 and isinstance(editor, QDateTimeEdit):
            model.setData(index, editor.dateTime(), Qt.EditRole)
        else:
            super().setModelData(editor, index)


class ResourceTypeDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        if index.column() == 1:  # Type of Resource column
            editor = QComboBox(parent)
            editor.addItems(["Physical Resource", "Human Resource", "Financial Resource"])
            return editor
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor, index):
        if index.column() == 1 and isinstance(editor, QComboBox):
            current_text = index.model().data(index, Qt.EditRole)
            idx = editor.findText(current_text)
            if idx >= 0:
                editor.setCurrentIndex(idx)
        else:
            super().setEditorData(editor, index)

    def setModelData(self, editor, model, index):
        if index.column() == 1 and isinstance(editor, QComboBox):
            model.setData(index, editor.currentText(), Qt.EditRole)
        else:
            super().setModelData(editor, index)


def qdatetime_to_str(value):
    if isinstance(value, QDateTime):
        return value.toString("yyyy-MM-dd HH:mm")
    return value


def str_to_qdatetime(value):
    if isinstance(value, str):
        dt = QDateTime.fromString(value, "yyyy-MM-dd HH:mm")
        if dt.isValid():
            return dt
    return value


def days_between(start: str, end: str) -> int | None:
    FMT = "%Y-%m-%d %H:%M"

    try:
        return (datetime.strptime(end, FMT) - datetime.strptime(start, FMT)).days
    except (ValueError, TypeError):
        return None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ActivityTableApp()
    window.show()
    sys.exit(app.exec_())
