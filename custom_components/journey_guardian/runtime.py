"""Runtime container for Journey Guardian."""

from dataclasses import dataclass

from .budget import TransportAPIBudget
from .coordinator import JourneyGuardianCoordinator
from .notification import JourneyNotificationScheduler
from .simulation import JourneySimulation


@dataclass(slots=True)
class JourneyGuardianRuntimeData:
    """Objects owned by one Journey Guardian config entry."""

    coordinator: JourneyGuardianCoordinator
    budget: TransportAPIBudget
    simulation: JourneySimulation
    notification_scheduler: JourneyNotificationScheduler
