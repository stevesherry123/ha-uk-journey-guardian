"""Repeated failures need elapsed time and genuinely new samples."""

from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.helpers import issue_registry as ir

from custom_components.journey_guardian.const import DOMAIN
from custom_components.journey_guardian.health_issues import JourneyHealthIssues

NOW = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize("error", ["permission_denied", "authentication_failed"])
async def test_google_access_repair_is_immediate_and_only_google_success_clears(
    hass, error
):
    issues = JourneyHealthIssues(hass)
    registry = ir.async_get(hass)
    key = (DOMAIN, "google_routes_access")
    issues.observe_google_access(
        error=f"google_routes_{error}", source="configured_fallback"
    )
    assert key in registry.issues
    assert registry.issues[key].translation_placeholders is None
    issues.observe_google_access(error=None, source="waze_sensor")
    assert key in registry.issues
    issues.stop()
    assert key in registry.issues
    issues.observe_google_access(error=None, source="google_routes")
    assert key not in registry.issues


async def test_transient_route_failure_does_not_raise_account_repair(hass):
    issues = JourneyHealthIssues(hass)
    issues.observe_google_access(
        error="google_routes_timeout", source="configured_fallback"
    )
    assert (DOMAIN, "google_routes_access") not in ir.async_get(hass).issues


@pytest.mark.parametrize("kind", ["calendar", "routing", "rail"])
async def test_repair_requires_samples_and_time_then_clears_on_success(hass, kind):
    issues = JourneyHealthIssues(hass)
    registry = ir.async_get(hass)
    key = (DOMAIN, f"sustained_{kind}")
    for minute in (0, 10, 20):
        issues.observe(
            kind, failed=True, now=NOW + timedelta(minutes=minute), token=str(minute)
        )
        assert key not in registry.issues
    issues.observe(kind, failed=True, now=NOW + timedelta(minutes=30), token="20")
    assert key in registry.issues
    assert registry.issues[key].translation_placeholders is None
    issues.observe(kind, failed=False, now=NOW + timedelta(minutes=31), token="31")
    assert key not in registry.issues


async def test_republishing_one_rail_error_never_counts_as_multiple_attempts(hass):
    issues = JourneyHealthIssues(hass)
    for minute in (0, 10, 20, 30, 60):
        issues.observe(
            "rail", failed=True, now=NOW + timedelta(minutes=minute), token="one-check"
        )
    assert (DOMAIN, "sustained_rail") not in ir.async_get(hass).issues


async def test_reload_cleanup_removes_notices_and_resets_failure_window(hass):
    issues = JourneyHealthIssues(hass)
    for minute in (0, 15, 30):
        issues.observe(
            "calendar",
            failed=True,
            now=NOW + timedelta(minutes=minute),
            token=str(minute),
        )
    assert (DOMAIN, "sustained_calendar") in ir.async_get(hass).issues
    issues.stop()
    assert (DOMAIN, "sustained_calendar") not in ir.async_get(hass).issues
    assert not issues._counts
