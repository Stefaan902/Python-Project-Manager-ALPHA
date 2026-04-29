"""
conftest.py — shared pytest fixtures for the Project Manager test suite.

Fixtures defined here are automatically available to every test module
without needing an explicit import.
"""

import sys
import os
import pytest

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

# Must be set before any QApplication is created
QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)

# ---------------------------------------------------------------------------
# Make sure the project root (where maincode.py lives) is on sys.path so
# that `import maincode` works regardless of how pytest is invoked.
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ---------------------------------------------------------------------------
# QApplication singleton
# ---------------------------------------------------------------------------
# pytest-qt provides a `qapp` fixture automatically, but we also expose a
# plain `app` alias so tests can use whichever name they prefer.

@pytest.fixture(scope="session")
def app(qapp):
    """Session-scoped QApplication.  Re-uses the instance created by pytest-qt."""
    return qapp


# ---------------------------------------------------------------------------
# Lightweight model factory — does NOT create the full main window
# ---------------------------------------------------------------------------

@pytest.fixture()
def activity_model(app):
    """Return a fresh, empty ActivityTableModel."""
    from maincode import ActivityTableModel
    return ActivityTableModel()


@pytest.fixture()
def fresh_window(app, qtbot):
    """
    Instantiate the full ActivityTableApp main window without displaying it.
    qtbot registers the widget so it is properly cleaned up after each test.
    """
    from maincode import ActivityTableApp
    window = ActivityTableApp()
    qtbot.addWidget(window)
    return window
