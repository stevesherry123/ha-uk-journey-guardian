# Connection warnings and delivery history (unreleased development)

Connection warnings are implemented locally and are not in stable v0.2.13.
They require [confirmed connection monitoring](CONNECTION_MONITORING.md) and the
existing **live notifications** setting to be enabled. Monitoring defaults to off;
loading or upgrading this development code alone does not enable these warnings.
When live notifications are disabled, monitoring can still populate the dashboard.

## Initial development policy

- Warn at the first fresh assessment below the configured transfer allowance.
- During risk, announce an update when available transfer time changes by at least
  five minutes from the last alert, or the required allowance changes.
- Announce recovery only when the fresh available transfer exceeds the allowance
  by at least two minutes. This hysteresis reduces repeated risk/recovery messages
  close to the threshold. It does not guarantee the connection will be made.
- Keep at least five minutes between alert attempts for a booked connection.
  Connection checks remain bounded by the existing eight-evaluations-per-day cap.
- Missing, stale, retained or timetable-only evidence never produces an all-clear
  announcement. Unknown does not clear the previous warning history.
- Negative available transfer is described as arrival after onward departure,
  not a confirmed missed train. Available live arrival/departure times are shown.

These are development defaults, subject to real-travel acceptance before release.
They do not introduce frequent background polling or change wake-up repetition.

## Delivery route and guards

Use the existing configured announcement helper and script. If unavailable or
failing, the existing Home Assistant persistent-notification fallback is used.
The route has a bounded 20-second wait; a timeout can create the local fallback.
It cannot guarantee a phone/watch receipt or undo a script already handed off.
A successful recovery script hand-off dismisses an earlier local fallback with
the same connection ID so an obsolete risk notice is not left standing.

Before the helper write and before script hand-off, recheck that the connection
is current, its allowance still matches the assessed one, evidence is unexpired,
monitoring is active, and simulation/calendar state still permits the action.
Disabled live alerts cannot claim or deliver a connection notice. A context change
while waiting for the shared delivery lock suppresses the old notice.

## Restart, uncertainty and storage failures

The calendar/entry-scoped ledger stores hashed booking-pair identities and bounded
transition metadata, not station names, calendar titles or full warning text.
Its expiry follows the onward booking's retained-intent expiry; at most 64 active
records are retained. The transition is durably claimed before delivery, and its
hand-off outcome is saved afterwards.

If HA stops after the claim but before the outcome is saved, the outcome remains
**delivery unconfirmed**. The same warning is not automatically replayed after
restart: replay could duplicate an already handed-off announcement. This is
at-most-once attempt accounting, not guaranteed exactly-once device delivery.
A failed ledger save pauses further claims until a successful reload. The
integration surfaces a dashboard alert-history error rather than sending without
reliable deduplication. A suppressed in-flight attempt also remains recorded;
only a subsequent meaningful transition can produce another attempt.

## Dashboard

Fresh risk remains visible alongside the numeric margin and applied allowance.
If evidence expires, the numeric margin changes to unknown. A separate historical
notice retains that a previous assessment found risk until fresh evidence can
reassess it; it never labels old data current. The last alert attempt shows time,
kind and hand-off result, always with device receipt unconfirmed.

Fictional preview scenarios cover risk, recovered margin, stale evidence and
uncertain hand-off. Physical delivery and live HA acceptance remain required
before release. Recovery-route search is still a separate pending milestone.
