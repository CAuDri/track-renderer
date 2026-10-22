"""Find placed objects and zone visits without repeatedly scanning the whole track.

Ownership and route visits are indexed separately: a global zone has no owning
section, but can still affect several roads or visit the same junction twice.
The index keeps the model's order so drawing IDs and diagnostics stay stable.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..description.types import Instance, RouteLeg


class InstanceIndex:
    """@brief Read-only lookup tables built once for each rendering."""

    def __init__(self, instances: Iterable[Instance]):
        self._owned: dict[str | None, list[Instance]] = defaultdict(list)
        self._visits: dict[str, list[tuple[Instance, RouteLeg]]] = defaultdict(list)
        self._kinds: dict[str, list[tuple[int, Instance]]] = defaultdict(list)

        for order, instance in enumerate(instances):
            self._owned[instance.section].append(instance)
            self._kinds[instance.kind].append((order, instance))

            for leg in instance.route or ():
                self._visits[leg.section].append((instance, leg))

    def owned(self, section_id: str, *kinds: str) -> tuple[Instance, ...]:
        """@return Objects owned by a section, optionally restricted to given kinds."""
        return tuple(
            instance
            for instance in self._owned.get(section_id, ())
            if not kinds or instance.kind in kinds
        )

    def visits(self, section_id: str, *kinds: str) -> tuple[tuple[Instance, RouteLeg], ...]:
        """@return Every matching route visit, including repeated and global visits."""
        return tuple(
            (instance, leg)
            for instance, leg in self._visits.get(section_id, ())
            if not kinds or instance.kind in kinds
        )

    def kinds(self, *kinds: str) -> tuple[Instance, ...]:
        """@return Objects of the requested kinds in their original model order."""
        matches = [item for kind in set(kinds) for item in self._kinds.get(kind, ())]
        return tuple(instance for _, instance in sorted(matches, key=lambda item: item[0]))
