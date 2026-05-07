"""
test_smoke.py — Step 1: Verify the application can be imported and
instantiated without raising any exception.

These tests intentionally contain no assertions beyond the fact that the
relevant objects can be constructed.  They act as a quick health-check that
catches import errors, missing dependencies, and fatal __init__ bugs before
any deeper tests are run.
"""

import pytest


class TestImport:
    """The module and its classes must be importable."""

    def test_import_project_manager(self):
        """project_manager.py must be importable without side-effects."""
        import project_manager  # noqa: F401

    def test_import_activity_table_model(self):
        from project_manager import ActivityTableModel  # noqa: F401

    def test_import_resource_table_model(self):
        from project_manager import ResourceTableModel  # noqa: F401

    def test_import_risk_table_model(self):
        from project_manager import RiskTableModel  # noqa: F401

    def test_import_bill_of_quantity_model(self):
        from project_manager import BillOfQuantityTableModel  # noqa: F401

    def test_import_activity_table_app(self):
        from project_manager import ActivityTableApp  # noqa: F401


class TestModelInstantiation:
    """Individual models must be constructable without a full main window."""

    def test_activity_model_instantiates(self, app):
        from project_manager import ActivityTableModel
        model = ActivityTableModel()
        assert model is not None

    def test_activity_model_starts_empty(self, app):
        from project_manager import ActivityTableModel
        model = ActivityTableModel()
        assert model.rowCount() == 0
        assert model.columnCount() == 13  # 13 defined headers

    def test_resource_model_instantiates(self, app):
        from project_manager import ActivityTableModel, ResourceTableModel
        activity_model = ActivityTableModel()
        model = ResourceTableModel(activity_model)
        assert model is not None

    def test_resource_model_starts_empty(self, app):
        from project_manager import ActivityTableModel, ResourceTableModel
        activity_model = ActivityTableModel()
        model = ResourceTableModel(activity_model)
        assert model.rowCount() == 0
        assert model.columnCount() == 8  # 8 defined headers

    def test_boq_model_instantiates(self, app):
        from project_manager import BillOfQuantityTableModel
        model = BillOfQuantityTableModel()
        assert model is not None

    def test_boq_model_starts_empty(self, app):
        from project_manager import BillOfQuantityTableModel
        model = BillOfQuantityTableModel()
        assert model.rowCount() == 0
        assert model.columnCount() == 10  # 10 defined headers


class TestMainWindowInstantiation:
    """The full main window must construct and show without crashing."""

    def test_activity_table_app_instantiates(self, fresh_window):
        """ActivityTableApp.__init__ must complete without raising."""
        assert fresh_window is not None

    def test_main_window_has_tab_widget(self, fresh_window):
        """The main window must expose its QTabWidget."""
        assert fresh_window.tabs is not None
        assert fresh_window.tabs.count() > 0

    def test_main_window_activity_model_is_set(self, fresh_window):
        """activity_model must be attached to the main window."""
        assert fresh_window.activity_model is not None

    def test_main_window_resource_model_is_set(self, fresh_window):
        """resource_model must be attached to the main window."""
        assert fresh_window.resource_model is not None

    def test_main_window_shows_without_error(self, fresh_window, qtbot):
        """Calling show() must not raise any exception."""
        fresh_window.show()
        # qtbot.waitExposed is a stronger check available in pytest-qt >= 4.x
        assert fresh_window.isVisible()
