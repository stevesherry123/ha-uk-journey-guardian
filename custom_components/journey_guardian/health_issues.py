"""Debounced local Repairs notices, without extra provider requests."""

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

FAILURE_WINDOW = timedelta(minutes=30)
MIN_FAILURES = 3
KINDS = ("calendar", "routing", "rail")


class JourneyHealthIssues:
    """Require three distinct failed samples and a sustained failure window."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._first: dict[str, datetime] = {}
        self._counts: dict[str, int] = {}
        self._tokens: dict[str, tuple[str, bool]] = {}
        self._active: set[str] = set()

    @callback
    def observe(self, kind: str, *, failed: bool, now: datetime, token: str) -> None:
        if kind not in KINDS:
            raise ValueError("unknown_health_kind")
        if self._tokens.get(kind) != (token, failed):
            self._tokens[kind] = (token, failed)
            if not failed:
                self._first.pop(kind, None)
                self._counts.pop(kind, None)
                self._active.discard(kind)
                ir.async_delete_issue(self.hass, DOMAIN, f"sustained_{kind}")
                return
            self._first.setdefault(kind, now)
            self._counts[kind] = min(MIN_FAILURES, self._counts.get(kind, 0) + 1)
        if (
            failed
            and kind not in self._active
            and self._counts.get(kind, 0) >= MIN_FAILURES
            and now - self._first[kind] >= FAILURE_WINDOW
        ):
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"sustained_{kind}",
                is_fixable=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=f"sustained_{kind}",
                learn_more_url=(
                    "https://github.com/stevesherry123/ha-uk-journey-guardian/"
                    "blob/main/docs/TROUBLESHOOTING.md"
                ),
            )
            self._active.add(kind)

    @callback
    def stop(self) -> None:
        for kind in KINDS:
            ir.async_delete_issue(self.hass, DOMAIN, f"sustained_{kind}")
        self._first.clear()
        self._counts.clear()
        self._tokens.clear()
        self._active.clear()
