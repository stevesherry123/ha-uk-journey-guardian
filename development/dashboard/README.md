# Travel Dashboard Development

Branch: `development/travel-dashboard`. Draft, not a stable release. Do not merge,
tag, install into the live HA instance, or change live Lovelace resources until
the owner approves. The existing stable-update activation is unrelated.

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

Serve this directory on localhost with a static HTTP server. Open `index.html`
and select a fictional scenario. It never connects to the owner's HA instance.
Run `node --test card.test.js` for the browser-independent contract tests and
`pytest tests/test_dashboard.py` for the server projection tests.

## Test HA Installation Later

Use a disposable HA instance running this branch, not the live stable instance.
Copy `journey-guardian-card.js` into that test instance's `www` directory. Add
`/local/journey-guardian-card.js` as a JavaScript module dashboard resource and use
the example in `dashboard.yaml`, replacing its fictional sensor ID with the
test status entity. Old/stable integrations without schema 1 show unavailable
dashboard data, never a guessed plan. No automatic dashboard/resource creation.

## Review Decisions Before Merge

1. Confirm the single-journey Gantt layout and notification-detail density on
   desktop and mobile, including service disruption and long station names.
2. Decide whether to add a bounded, persisted delivery ledger. Current data only
   proves the latest recorded action, not every hand-off or physical receipt.
3. Decide whether the card should ship as a separate frontend package or gain
   explicit HA static-resource registration. Currently the release ZIP does not
   install files from this development directory.
4. Extend beyond the next scheduled check only when the full shared scheduler
   contract can be exposed without inventing alerts or quota reservations.
5. Complete retained journey validation and a real disposable-HA acceptance run
   before calling this production-ready. Clock-change and overnight formatting
   have automated coverage, but real device notification receipt remains unknown.

The projection contains private itinerary information for the local dashboard,
as existing status attributes already do. Do not attach its contents to issues.
Integration diagnostics use an explicit safe allowlist and do not export it.
