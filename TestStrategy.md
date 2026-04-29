# Test Strategy — Project Management UI (PyQt5)

## 1. Application Overview

The application is a PyQt5 desktop tool for managing construction/engineering projects. It is structured around a tabbed main window (`ActivityTableApp`) and exposes the following functional modules:

- **Activities** — WBS-based task list with hierarchy, predecessor/successor relationships, and CPM scheduling
- **Resources** — Resource registry (human, physical, financial) with rate aggregation for parent groups
- **Risks** — Risk register with probability/impact ratings
- **Bill of Quantities (BOQ)** — Quantity takeoff table with auto-calculated sums and costs
- **Integration** — Cross-module assignment of resources, risks, and BOQ items to activities
- **Visualisations** — Gantt chart (Matplotlib), PERT diagram (Matplotlib + NetworkX), WBS tree, RBS tree, Risk Matrix (Plotly/QWebEngineView)
- **Persistence** — Save/load project state as JSON

---

## 2. Test Objectives

- Verify the correctness of scheduling calculations (end-date derivation, CPM forward/backward pass)
- Verify data integrity across the table models (insert, edit, delete, parent-child aggregation)
- Verify cross-module integration (resource/risk/BOQ assignment, refresh on model change)
- Verify save/load round-trip fidelity
- Verify the UI responds correctly to user interactions (delegates, context menus, dialogs)
- Identify crashes, hangs, or silent data corruption

---

## 3. Test Levels

### 3.1 Unit Tests

Unit tests target pure-Python logic that has no hard dependency on a running `QApplication`. These are the fastest and most reliable tests to write.

**Tooling:** `pytest`, `pytest-qt` (provides `qtbot` and `qapp` fixtures)

**Priority targets:**

| Component | What to test |
|---|---|
| `calculate_end_date` | Start + duration → correct end date string; zero/negative duration is handled gracefully |
| `calculate_cpm` | Forward pass ES/EF, backward pass LS/LF on a known network; cycle detection raises the right error |
| `update_successor_start_dates` | Successor start is pushed forward when predecessor ends later |
| `ActivityTableModel.recalc_parent_activities` | Parent start = min(child starts), parent end = max(child ends), parent duration = sum |
| `ResourceTableModel.recalc_parent_resources` | Parent rates = sum of child rates |
| `BillOfQuantityTableModel.recalculate_row` | Sum = D1 × D2 × D3; Total = Sum × CostPerUnit; partial dimensions handled |
| `qdatetime_to_str` / `str_to_qdatetime` | Round-trip conversion; invalid strings return original value |
| `ActivityTableModel.removeRows` | Parent-child map indices are remapped after deletion |

**Example test skeleton:**

```python
# test_cpm.py
import pytest
from PyQt5.QtWidgets import QApplication
import sys

@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication(sys.argv)

def test_cpm_linear_chain(app):
    from maincode import ActivityTableApp
    window = ActivityTableApp()
    # Add 3 activities in a chain: 1 → 2 → 3, durations 2, 3, 4
    # ... set up model data directly ...
    window.calculate_cpm()
    data = window.activity_model._data
    # Activity 3: ES=5, EF=9, LS=5, LF=9 (no float)
    assert data[2][7] == 5   # ES
    assert data[2][8] == 9   # EF

def test_cpm_cycle_detection(app):
    from maincode import ActivityTableApp
    window = ActivityTableApp()
    # Activity 1 predecessor = 2, Activity 2 predecessor = 1 → cycle
    # calculate_cpm should call QMessageBox.critical and return without crashing
    # Patch QMessageBox.critical to capture the call
    ...
```

---

### 3.2 Integration Tests

Integration tests verify interactions between components, typically requiring a running `QApplication` and a partially populated model.

**Tooling:** `pytest-qt`

**Priority scenarios:**

**Scheduling chain**
- Set activity A (duration 5, start 2025-01-01). Add activity B with predecessor A. Verify B's start date propagates to 2025-01-06 after `calculate_end_date` runs.

**CPM on a fork-join network**
- Build activities with two parallel paths of different lengths. Verify that CPM correctly identifies the critical path (float = 0) vs. the non-critical path (float > 0).

**Parent-child aggregation**
- Promote a resource row to a parent of two children. Edit child rates. Verify parent totals update via `recalc_parent_resources`.

**Integration model refresh**
- Assign a resource to an activity. Change the activity name. Verify `IntegrationTableModel` reflects the new name after the `dataChanged` signal propagates.

**BOQ auto-calculation**
- Enter three dimension values and a unit cost. Verify that Sum and Total Cost columns update automatically and that the cells are read-only.

---

### 3.3 System / UI Tests

System tests drive the application through the GUI, simulating real user workflows. These are the slowest but catch regressions in the full stack.

**Tooling:** `pytest-qt` (`qtbot`), optionally `pyautogui` for pixel-level interaction

**Key workflows to automate:**

**Workflow 1 — Basic scheduling cycle**
1. Launch app
2. Add 3 activity rows
3. Enter names, durations, and predecessor IDs
4. Verify CPM columns (ES, EF, LS, LF) are populated
5. Verify Gantt chart renders without exception

**Workflow 2 — Hierarchical activities**
1. Add a parent activity with two children (using the indent/group mechanism)
2. Enter child start dates and durations
3. Trigger `recalc_parent_activities`
4. Verify parent row shows aggregated values

**Workflow 3 — Save and Load**
1. Create a project with activities, resources, risks, and BOQ items
2. Save to JSON
3. Close and reopen (or call `load_project_from_json` on a fresh window)
4. Verify all data is restored; verify CPM is recalculated on load; verify ES/EF/LS/LF fields are cleared then re-derived

**Workflow 4 — Integration assignments**
1. Create one activity, one resource, one risk, one BOQ item
2. Assign all three to the activity via the Integration tab context menu
3. Verify counts in the Integration table view

**Workflow 5 — Delete rows with dependencies**
1. Create activities A → B → C
2. Delete B
3. Verify predecessor references in C do not cause a crash
4. Verify CPM recalculates without a KeyError

---

### 3.4 Regression Tests for Known Fragile Areas

The code review identified several areas that are particularly prone to defects and should have dedicated regression tests:

**Duplicate `data()` method in `ActivityTableModel`** — Two `data()` methods are defined (lines 46 and 71). Python silently uses the second. The first (with indentation logic) is dead code. A test should confirm indentation is *not* reflected in DisplayRole output (since the dead method handled it) and that this behaviour is explicitly documented.

**`flags()` column duplication in `ActivityTableModel`** — `column = index.column()` is assigned twice (lines 114 and 117). This is harmless but signals copy-paste errors nearby. Verify that column 0 is non-editable and columns 4, 6–10 are non-editable.

**`update_visible_rows` not connected to the view** — The method computes a visibility set but the `QTableView` has no mechanism to actually hide rows. Test confirms all rows remain visible regardless of collapse state (current behaviour), so that any future fix does not inadvertently break the existing visible-by-default behaviour.

**Predecessor parsing** — Predecessors are stored as semicolon-separated row-number strings (1-based). Test edge cases: empty string, single predecessor, multiple predecessors, leading/trailing spaces, non-numeric values.

**`str_to_qdatetime` on load** — Test that loading a JSON file where a datetime column contains a non-date string (e.g., an activity name accidentally written to column 3) does not crash the application.

---

## 4. Test Data Strategy

**Minimal valid project** — 3 activities, 1 resource, 1 risk, 1 BOQ item with one assignment each. Used for smoke tests and save/load round-trip.

**Critical path project** — 6 activities forming a diamond network with a known critical path. Used to validate CPM results against hand-calculated values.

**Large project** — 50+ activities with multi-level hierarchy. Used for performance tests (chart rendering, CPM recalculation time).

**Corrupt JSON files** — Missing keys, invalid datetime strings, negative row indices in `parent_child_map`. Used for robustness tests of `load_project_from_json`.

Store all test fixtures as `.json` files under a `tests/fixtures/` directory so they can be version-controlled and reused across test levels.

---

## 5. Non-Functional Testing

**Performance**
- Measure time to `calculate_cpm()` with 100 activities. Target: under 500 ms on a mid-range machine.
- Measure time to render the Gantt chart with 100 activities. Target: under 2 seconds.

**Memory**
- Open and close 10 projects in sequence. Check for growing memory usage (QWebEngineView is a common leak source with Plotly HTML).

**Stability**
- Rapid repeated clicks on "Add Row" / "Remove Row" should not cause index errors.
- Switching tabs rapidly while a chart is rendering should not crash.

---

## 6. Test Environment

| Requirement | Recommended |
|---|---|
| Python | 3.9+ |
| PyQt5 | 5.15.x |
| pytest | 7.x |
| pytest-qt | 4.x |
| OS | Windows 10/11 (primary target); Ubuntu 22.04 (CI) |
| Display | Virtual framebuffer (`Xvfb`) for headless CI on Linux |

**CI setup (GitHub Actions example):**
```yaml
- name: Install Xvfb
  run: sudo apt-get install -y xvfb
- name: Run tests
  run: xvfb-run --auto-servernum pytest tests/ -v
```

---

## 7. Defect Priority Classification

| Severity | Examples |
|---|---|
| P1 — Crash | App exits or raises unhandled exception |
| P2 — Data loss | Save/load drops data; delete corrupts parent-child map |
| P3 — Wrong calculation | CPM values incorrect; BOQ totals wrong |
| P4 — UI glitch | Chart does not render; column non-editable when it should be |
| P5 — Cosmetic | Indentation not shown due to dead `data()` method |

---

## 8. Recommended First Steps

Given the size of the codebase and the number of fragile areas identified, the recommended order of implementation is:

1. Set up `pytest` + `pytest-qt` and write a smoke test that imports the module and instantiates `ActivityTableApp` without crashing.
2. Write unit tests for `calculate_cpm` using a hand-crafted model (does not require the full UI).
3. Write unit tests for `BillOfQuantityTableModel.recalculate_row` (pure logic, no Qt dependency at all).
4. Write the save/load round-trip integration test.
5. Progressively add workflow-level tests for each tab.