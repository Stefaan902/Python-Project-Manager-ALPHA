"""
Unit tests for ResourceAllocationManager.

These tests deliberately have no Qt dependency. Integration between
ResourceAllocationManager and IntegrationTableModel is tested separately.
"""

import pytest

from resource_allocation import ResourceAllocationManager


# ---------------------------------------------------------------------------
# Local lightweight fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def allocation_manager():
    return ResourceAllocationManager()


@pytest.fixture()
def activity_ids():
    return {
        "foundation": "activity-001",
        "structure": "activity-002",
        "electrical": "activity-003",
    }


@pytest.fixture()
def resource_ids():
    return {
        "john": "resource-001",
        "excavator": "resource-002",
        "crane": "resource-003",
    }


# ---------------------------------------------------------------------------
# Basic allocation
# ---------------------------------------------------------------------------

def test_new_manager_has_no_allocations(
    allocation_manager,
    activity_ids,
):
    assert allocation_manager.get_resource_ids(
        activity_ids["foundation"]
    ) == []


def test_assign_resource(
    allocation_manager,
    activity_ids,
    resource_ids,
):
    created = allocation_manager.assign(
        activity_ids["foundation"],
        resource_ids["john"],
    )

    assert created is True

    assert allocation_manager.is_assigned(
        activity_ids["foundation"],
        resource_ids["john"],
    )


def test_assigned_resource_can_be_retrieved(
    allocation_manager,
    activity_ids,
    resource_ids,
):
    allocation_manager.assign(
        activity_ids["foundation"],
        resource_ids["john"],
    )

    assert allocation_manager.get_resource_ids(
        activity_ids["foundation"]
    ) == [
        resource_ids["john"]
    ]


# ---------------------------------------------------------------------------
# Duplicate protection
# ---------------------------------------------------------------------------

def test_duplicate_assignment_is_not_created(
    allocation_manager,
    activity_ids,
    resource_ids,
):
    first = allocation_manager.assign(
        activity_ids["foundation"],
        resource_ids["john"],
    )

    second = allocation_manager.assign(
        activity_ids["foundation"],
        resource_ids["john"],
    )

    assert first is True
    assert second is False

    assert allocation_manager.count(
        activity_ids["foundation"]
    ) == 1


# ---------------------------------------------------------------------------
# Multiple resources / activities
# ---------------------------------------------------------------------------

def test_multiple_resources_can_be_assigned_to_activity(
    allocation_manager,
    activity_ids,
    resource_ids,
):
    activity_id = activity_ids["foundation"]

    allocation_manager.assign(
        activity_id,
        resource_ids["john"],
    )

    allocation_manager.assign(
        activity_id,
        resource_ids["excavator"],
    )

    assert set(
        allocation_manager.get_resource_ids(activity_id)
    ) == {
        resource_ids["john"],
        resource_ids["excavator"],
    }


def test_same_resource_can_be_assigned_to_multiple_activities(
    allocation_manager,
    activity_ids,
    resource_ids,
):
    allocation_manager.assign(
        activity_ids["foundation"],
        resource_ids["john"],
    )

    allocation_manager.assign(
        activity_ids["structure"],
        resource_ids["john"],
    )

    assert allocation_manager.is_assigned(
        activity_ids["foundation"],
        resource_ids["john"],
    )

    assert allocation_manager.is_assigned(
        activity_ids["structure"],
        resource_ids["john"],
    )


# ---------------------------------------------------------------------------
# Unassign
# ---------------------------------------------------------------------------

def test_unassign_existing_resource(
    allocation_manager,
    activity_ids,
    resource_ids,
):
    activity_id = activity_ids["foundation"]
    resource_id = resource_ids["john"]

    allocation_manager.assign(
        activity_id,
        resource_id,
    )

    removed = allocation_manager.unassign(
        activity_id,
        resource_id,
    )

    assert removed is True

    assert not allocation_manager.is_assigned(
        activity_id,
        resource_id,
    )


def test_unassign_nonexistent_resource_returns_false(
    allocation_manager,
    activity_ids,
    resource_ids,
):
    result = allocation_manager.unassign(
        activity_ids["foundation"],
        resource_ids["john"],
    )

    assert result is False


# ---------------------------------------------------------------------------
# Replace assignment
# ---------------------------------------------------------------------------

def test_replace_resources_for_activity(
    allocation_manager,
    activity_ids,
    resource_ids,
):
    activity_id = activity_ids["foundation"]

    allocation_manager.assign(
        activity_id,
        resource_ids["john"],
    )

    allocation_manager.replace(
        activity_id,
        [
            resource_ids["excavator"],
            resource_ids["crane"],
        ],
    )

    assert set(
        allocation_manager.get_resource_ids(activity_id)
    ) == {
        resource_ids["excavator"],
        resource_ids["crane"],
    }

    assert not allocation_manager.is_assigned(
        activity_id,
        resource_ids["john"],
    )


# ---------------------------------------------------------------------------
# Delete handling
# ---------------------------------------------------------------------------

def test_remove_activity_removes_its_allocations_only(
    allocation_manager,
    activity_ids,
    resource_ids,
):
    allocation_manager.assign(
        activity_ids["foundation"],
        resource_ids["john"],
    )

    allocation_manager.assign(
        activity_ids["structure"],
        resource_ids["john"],
    )

    allocation_manager.remove_activity(
        activity_ids["foundation"]
    )

    assert allocation_manager.get_resource_ids(
        activity_ids["foundation"]
    ) == []

    assert allocation_manager.is_assigned(
        activity_ids["structure"],
        resource_ids["john"],
    )


def test_remove_resource_removes_it_from_all_activities(
    allocation_manager,
    activity_ids,
    resource_ids,
):
    resource_id = resource_ids["john"]

    allocation_manager.assign(
        activity_ids["foundation"],
        resource_id,
    )

    allocation_manager.assign(
        activity_ids["structure"],
        resource_id,
    )

    allocation_manager.remove_resource(resource_id)

    assert not allocation_manager.is_assigned(
        activity_ids["foundation"],
        resource_id,
    )

    assert not allocation_manager.is_assigned(
        activity_ids["structure"],
        resource_id,
    )


# ---------------------------------------------------------------------------
# Regression: refresh must NOT destroy valid allocations
# ---------------------------------------------------------------------------

def test_synchronize_preserves_valid_allocation(
    allocation_manager,
    activity_ids,
    resource_ids,
):
    allocation_manager.assign(
        activity_ids["foundation"],
        resource_ids["john"],
    )

    allocation_manager.synchronize(
        valid_activity_ids=[
            activity_ids["foundation"],
            activity_ids["structure"],
        ],
        valid_resource_ids=[
            resource_ids["john"],
            resource_ids["excavator"],
        ],
    )

    assert allocation_manager.is_assigned(
        activity_ids["foundation"],
        resource_ids["john"],
    )


def test_synchronize_removes_deleted_resource(
    allocation_manager,
    activity_ids,
    resource_ids,
):
    allocation_manager.assign(
        activity_ids["foundation"],
        resource_ids["john"],
    )

    allocation_manager.assign(
        activity_ids["foundation"],
        resource_ids["excavator"],
    )

    allocation_manager.synchronize(
        valid_activity_ids=[
            activity_ids["foundation"],
        ],
        valid_resource_ids=[
            resource_ids["excavator"],
        ],
    )

    assert allocation_manager.get_resource_ids(
        activity_ids["foundation"]
    ) == [
        resource_ids["excavator"]
    ]


def test_synchronize_removes_deleted_activity(
    allocation_manager,
    activity_ids,
    resource_ids,
):
    allocation_manager.assign(
        activity_ids["foundation"],
        resource_ids["john"],
    )

    allocation_manager.synchronize(
        valid_activity_ids=[
            activity_ids["structure"],
        ],
        valid_resource_ids=[
            resource_ids["john"],
        ],
    )

    assert allocation_manager.get_resource_ids(
        activity_ids["foundation"]
    ) == []


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_allocation_round_trip(
    allocation_manager,
    activity_ids,
    resource_ids,
):
    allocation_manager.assign(
        activity_ids["foundation"],
        resource_ids["john"],
    )

    allocation_manager.assign(
        activity_ids["foundation"],
        resource_ids["excavator"],
    )

    saved = allocation_manager.to_dict()

    restored = ResourceAllocationManager()
    restored.load_dict(saved)

    assert restored.to_dict() == saved


def test_load_none_creates_empty_manager(
    allocation_manager,
):
    allocation_manager.load_dict(None)

    assert allocation_manager.to_dict() == {}


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "activity_id, resource_id",
    [
        ("", "resource-001"),
        ("   ", "resource-001"),
        ("activity-001", ""),
        ("activity-001", "   "),
    ],
)
def test_invalid_ids_are_rejected(
    allocation_manager,
    activity_id,
    resource_id,
):
    with pytest.raises(ValueError):
        allocation_manager.assign(
            activity_id,
            resource_id,
        )