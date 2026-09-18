from __future__ import annotations

from typing import Set, Tuple
from app.schemas.ink import PhysicalState
from app.schemas.planner import ExecutionState


# Directed legal transitions in Physical Twin State Space
LEGAL_PHYSICAL_TRANSITIONS: Set[Tuple[PhysicalState | None, PhysicalState]] = {
    # From None (untracked / pristine surface)
    (None, PhysicalState.UNKNOWN),
    (None, PhysicalState.NEW_INK),
    (None, PhysicalState.STABLE_INK),

    # From UNKNOWN
    (PhysicalState.UNKNOWN, PhysicalState.NEW_INK),
    (PhysicalState.UNKNOWN, PhysicalState.STABLE_INK),
    (PhysicalState.UNKNOWN, PhysicalState.CLEANED),
    (PhysicalState.UNKNOWN, PhysicalState.UNKNOWN),

    # From NEW_INK
    (PhysicalState.NEW_INK, PhysicalState.STABLE_INK),
    (PhysicalState.NEW_INK, PhysicalState.OCCLUDED),
    (PhysicalState.NEW_INK, PhysicalState.CLEANED),
    (PhysicalState.NEW_INK, PhysicalState.PARTIALLY_CLEANED),

    # From STABLE_INK
    (PhysicalState.STABLE_INK, PhysicalState.STABLE_INK),
    (PhysicalState.STABLE_INK, PhysicalState.OCCLUDED),
    (PhysicalState.STABLE_INK, PhysicalState.PARTIALLY_CLEANED),
    (PhysicalState.STABLE_INK, PhysicalState.CLEANED),
    (PhysicalState.STABLE_INK, PhysicalState.UNKNOWN),

    # From OCCLUDED
    (PhysicalState.OCCLUDED, PhysicalState.OCCLUDED),
    (PhysicalState.OCCLUDED, PhysicalState.STABLE_INK),
    (PhysicalState.OCCLUDED, PhysicalState.UNKNOWN),

    # From PARTIALLY_CLEANED
    (PhysicalState.PARTIALLY_CLEANED, PhysicalState.PARTIALLY_CLEANED),
    (PhysicalState.PARTIALLY_CLEANED, PhysicalState.CLEANED),
    (PhysicalState.PARTIALLY_CLEANED, PhysicalState.PERMANENT_DEFECT),

    # From CLEANED
    (PhysicalState.CLEANED, PhysicalState.CLEANED),
    (PhysicalState.CLEANED, PhysicalState.NEW_INK),
    (PhysicalState.CLEANED, PhysicalState.STABLE_INK),

    # From PERMANENT_DEFECT
    (PhysicalState.PERMANENT_DEFECT, PhysicalState.PERMANENT_DEFECT),
}


class PhysicalStateMachine:
    """Validates physical twin state transitions according to digital twin laws."""

    @staticmethod
    def is_valid_transition(from_state: PhysicalState | None, to_state: PhysicalState) -> bool:
        """Check if transition between physical states is legal."""
        return (from_state, to_state) in LEGAL_PHYSICAL_TRANSITIONS

    @staticmethod
    def assert_physical_purity() -> None:
        """Assert that RESIDUAL_DETECTED is strictly excluded from physical state values."""
        physical_names = [s.value for s in PhysicalState]
        if "RESIDUAL_DETECTED" in physical_names:
            raise AssertionError("RESIDUAL_DETECTED cannot be a PhysicalState! It is an ExecutionStore flag.")
