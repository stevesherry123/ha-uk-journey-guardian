# Upcoming booked legs: 0.3 preview

Introduced in **0.3.0-beta.1** as read-only groundwork. It includes v0.2.7 recovery
and follow-up fixes but is not the completed 0.3 disruption workflow. For a stable
maintenance update, choose v0.2.7. Installing a prerelease remains a deliberate
HACS version selection and requires an HA restart; no alarm settings change.

On the integration's **Status** entity, open its attributes/details:

- `upcoming_booked_legs`: up to 16 independent calendar legs with booked endpoints,
  departure/arrival times, underway/upcoming booked window and previous-leg hint.
- `upcoming_booked_leg_count`: total recognized unique bookings in the response.
- `booking_overview_truncated`: true when more than 16 legs were recognized.
- `booking_overview_source`: calendar, unavailable, or simulation. A simulation
  does not include the real booking overview.

The source is the same calendar response used for ordinary review, within its
existing 30-hour lookahead. No new source refresh, provider call, timer, alert,
GPS request or calendar write is introduced. The earliest selected booking and
its existing timing calculation remain unchanged.

## What the hints mean

| Hint | Meaning, not a confirmed connection |
| --- | --- |
| `first_booking` | First displayed booking in the current window |
| `possible_connection` | Previous endpoint name matches the next origin and scheduled gap is 0 to 120 minutes |
| `separate_booking` | Matching station but gap exceeds 120 minutes |
| `different_station` | Endpoint names do not match exactly after basic whitespace/case and map-prefix normalization |
| `overlapping_bookings` | The next booked departure is before the previous booked arrival |
| `arrival_unknown` | The previous booking has no timed arrival |

`scheduled_gap_minutes` is schedule arithmetic, never live transfer feasibility.
The two-hour boundary is a conservative preview heuristic, not an operator rule,
an intention-break state or confirmation of a shared ticket. Different station
aliases can remain unmatched; no fuzzy location matching is performed. Real
minimum transfer time, platform access and current railway progress are not
assessed. Separate bookings stay separate even when a connection looks possible.

Exact duplicate event records collapse. Otherwise competing/overlapping bookings
stay visible rather than being guessed away. Invalid end-before-start records
are excluded from this overview; it does not repair the source calendar.

## Important limits

Completed bookings drop out as the calendar window advances. The overview is
not today's full history, a claim ledger or a retained multi-leg engine. During
calendar outage it is unavailable, not a trustworthy empty travel day. Minimal
active-leg recovery remains separate and does not synthesize the missing list.

Early-termination recognition, live connection-risk alerts, plan-wide quota
scheduling, replacement-train search and explicit route adoption remain future
work. The known early-termination acceptance test is still an expected failure.
Keep fallback alarms and consult operator advice during real disruption.

The list is not persisted by this feature or included in downloaded diagnostics.
It does contain private station labels and journey times in HA attributes and
service responses; Recorder, connected consumers and backups can retain them.
Protect the installation and inspect exports before sharing.
