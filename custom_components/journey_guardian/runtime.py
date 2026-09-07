"""Runtime container for Journey Guardian."""

from dataclasses import dataclass

from .budget import TransportAPIBudget
from .check_history import CheckHistory
from .coordinator import JourneyGuardianCoordinator
from .notification import JourneyNotificationScheduler
from .provider_broker import ProviderRequestBroker
from .rail_monitor import AutomaticRailMonitor
from .simulation import JourneySimulation


@dataclass(slots=True)
class JourneyGuardianRuntimeData:
    """Objects owned by one Journey Guardian config entry."""

    coordinator: JourneyGuardianCoordinator
    budget: TransportAPIBudget
    simulation: JourneySimulation
    notification_scheduler: JourneyNotificationScheduler
    provider_broker: ProviderRequestBroker
    automatic_rail_monitor: AutomaticRailMonitor
    check_history: CheckHistory
