"""Load pure Journey Guardian modules without importing Home Assistant."""

import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).parents[1]
COMPONENTS = ROOT / "custom_components"
INTEGRATION = COMPONENTS / "journey_guardian"

custom_components = ModuleType("custom_components")
custom_components.__path__ = [str(COMPONENTS)]
sys.modules.setdefault("custom_components", custom_components)

journey_guardian = ModuleType("custom_components.journey_guardian")
journey_guardian.__path__ = [str(INTEGRATION)]
sys.modules.setdefault("custom_components.journey_guardian", journey_guardian)
