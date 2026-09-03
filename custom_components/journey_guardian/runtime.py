"""Runtime container for Journey Guardian."""

from dataclasses import dataclass

from .budget import TransportAPIBudget
from .coordinator import JourneyGuardianCoordinator
from .simulation import JourneySimulation


@dataclass(slots=True)
class JourneyGuardianRuntimeData:
    """Objects owned by one Journey Guardian config entry."""

    coordinator: JourneyGuardianCoordinator
    budget: TransportAPIBudget
    simulation: JourneySimulation
