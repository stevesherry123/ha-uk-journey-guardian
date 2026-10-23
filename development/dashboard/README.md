# Travel Dashboard Development

Branch: `development/travel-dashboard`. Not merged to main or stable. The owner
authorised a live-data HA review on 23 October: v0.3.0-beta.9 is an opt-in
prerelease from this branch. This does not authorise merging it into main.

## First Slice

- A read-only `dashboard` attribute on the status sensor, schema version 1.
- One HA custom card consuming that attribute, not recalculating travel times.
- Shared-scale travel stages, current-time marker, selected routing evidence,
  conditional preparation/leave notifications and other independently booked legs.
- Explicit disabled, cancelled, unavailable, empty and stale-snapshot handling.
- Latest recorded HA notification only. No full history or receipt confirmation.
- No network requests, service calls, refresh buttons or notification delivery
  inside the card. Its clock refreshes once per minute and stops when detached.
- Actual next rail/routing checks from the coordinator, labelled as data checks,
  not promised notifications. Missing schedule timestamps stay absent.
- Explicit suppression reasons and planned delivery route without target IDs.
- Date-aware overnight labels and BST/GMT distinctions across repeated hours.

The backend projection uses existing engine timestamps, scheduler reminder
offsets and wake settings. Calendar text is rendered through `textContent`, never
as HTML. It does not call the development notification catalogue, whose proposed
events are not all implemented. Rail checks are not promised notifications;
station arrival and booked train arrival are milestones, not notification events.
Future legs remain calendar-only and do not receive invented access times.

## Preview

Serve the repository root on localhost with a static HTTP server. Open
`/development/dashboard/index.html`
and select a fictional scenario. It never connects to the owner's HA instance.
Run `node --test card.test.js` for the browser-independent contract tests and
`pytest tests/test_dashboard.py` for the server projection tests.

## Beta HA Review Installation

The release ZIP includes the canonical card in the integration's `frontend`
directory. The preview module re-exports it, so preview and installed code match.
Select v0.3.0-beta.9 in HACS (beta versions may need to be shown) and restart HA
only outside active journeys/alarms and executing scripts/automations.
Add `/journey_guardian/journey-guardian-card.js?v=0.3.0-beta.9` as a JavaScript
module resource. Create a separate review dashboard using `dashboard.yaml`,
replacing the fictional sensor ID with the actual status entity. Do not replace
existing dashboards. Only the JavaScript asset is public; entity data continues
to use the user's authenticated HA session. No additional provider API calls
are made by the card. Resource/dashboard creation is explicit, not automatic.

Rollback: use HACS to select stable v0.2.13 and restart outside active work. Remove
the beta dashboard and its resource when no longer needed. Existing settings and
credentials are not changed. On stable the beta projection is absent, so the
card shows unavailable data rather than guessing a plan.

## Review Decisions Before Merge

1. Confirm the single-journey Gantt layout and notification-detail density on
   desktop and mobile, including service disruption and long station names.
2. Decide whether to add a bounded, persisted delivery ledger. Current data only
   proves the latest recorded action, not every hand-off or physical receipt.
3. Review the beta's packaged single-file static-resource registration and
   explicit dashboard installation. No stable frontend support is implied.
4. Extend beyond the next scheduled check only when the full shared scheduler
   contract can be exposed without inventing alerts or quota reservations.
5. Complete retained journey validation and a real disposable-HA acceptance run
   before calling this production-ready. Clock-change and overnight formatting
   have automated coverage, but real device notification receipt remains unknown.

The projection contains private itinerary information for the local dashboard,
as existing status attributes already do. Do not attach its contents to issues.
Integration diagnostics use an explicit safe allowlist and do not export it.
