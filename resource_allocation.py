"""
resource_allocation.py

Pure-Python management of relationships between project activities
and resources.

Activities and resources are identified by stable UUID/string IDs.
Display names and other mutable properties are deliberately not stored
in this class.

The class has no PyQt dependency and can therefore be unit-tested
without constructing a QApplication.
"""

from __future__ import annotations

from collections.abc import Iterable


class ResourceAllocationManager:
    """Maintain resource-to-activity allocations."""

    def __init__(self) -> None:
        self._allocations: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def get_resource_ids(self, activity_id: str) -> list[str]:
        """Return the resource IDs assigned to an activity."""
        return sorted(
            self._allocations.get(activity_id, set())
        )

    def is_assigned(
        self,
        activity_id: str,
        resource_id: str,
    ) -> bool:
        """Return True when the resource is assigned to the activity."""
        return resource_id in self._allocations.get(
            activity_id,
            set(),
        )

    def count(self, activity_id: str) -> int:
        """Return the number of resources assigned to an activity."""
        return len(
            self._allocations.get(activity_id, set())
        )

    # ------------------------------------------------------------------
    # Mutation operations
    # ------------------------------------------------------------------

    def assign(
        self,
        activity_id: str,
        resource_id: str,
    ) -> bool:
        """
        Assign a resource to an activity.

        Returns True if a new allocation was created.
        Returns False if it already existed.
        """
        self._validate_id(activity_id, "activity_id")
        self._validate_id(resource_id, "resource_id")

        resources = self._allocations.setdefault(
            activity_id,
            set(),
        )

        if resource_id in resources:
            return False

        resources.add(resource_id)
        return True

    def unassign(
        self,
        activity_id: str,
        resource_id: str,
    ) -> bool:
        """
        Remove an allocation.

        Returns True if an allocation was removed.
        """
        resources = self._allocations.get(activity_id)

        if not resources or resource_id not in resources:
            return False

        resources.remove(resource_id)

        if not resources:
            self._allocations.pop(activity_id, None)

        return True

    def replace(
        self,
        activity_id: str,
        resource_ids: Iterable[str],
    ) -> None:
        """Replace all resource assignments for one activity."""
        self._validate_id(activity_id, "activity_id")

        validated = set()

        for resource_id in resource_ids:
            self._validate_id(resource_id, "resource_id")
            validated.add(resource_id)

        if validated:
            self._allocations[activity_id] = validated
        else:
            self._allocations.pop(activity_id, None)

    # ------------------------------------------------------------------
    # Synchronisation / cleanup
    # ------------------------------------------------------------------

    def remove_activity(self, activity_id: str) -> None:
        """Remove all allocations belonging to an activity."""
        self._allocations.pop(activity_id, None)

    def remove_resource(self, resource_id: str) -> None:
        """Remove a resource from every activity."""
        empty_activities = []

        for activity_id, resource_ids in self._allocations.items():
            resource_ids.discard(resource_id)

            if not resource_ids:
                empty_activities.append(activity_id)

        for activity_id in empty_activities:
            del self._allocations[activity_id]

    def synchronize(
        self,
        valid_activity_ids: Iterable[str],
        valid_resource_ids: Iterable[str],
    ) -> None:
        """
        Remove orphaned references without destroying valid allocations.

        This is intentionally different from clearing/rebuilding the
        relationship dictionary.
        """
        activities = set(valid_activity_ids)
        resources = set(valid_resource_ids)

        new_allocations: dict[str, set[str]] = {}

        for activity_id, assigned_ids in self._allocations.items():

            if activity_id not in activities:
                continue

            valid_assignments = assigned_ids & resources

            if valid_assignments:
                new_allocations[activity_id] = valid_assignments

        self._allocations = new_allocations

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, list[str]]:
        """Return JSON-serializable allocation data."""
        return {
            activity_id: sorted(resource_ids)
            for activity_id, resource_ids
            in sorted(self._allocations.items())
        }

    def load_dict(
        self,
        data: dict[str, Iterable[str]] | None,
    ) -> None:
        """Restore allocations from persisted data."""
        self._allocations.clear()

        if not data:
            return

        for activity_id, resource_ids in data.items():
            self.replace(activity_id, resource_ids)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_id(value: str, field_name: str) -> None:

        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{field_name} must be a non-empty string"
            )