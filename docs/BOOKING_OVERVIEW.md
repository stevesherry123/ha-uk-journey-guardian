# Upcoming and retained booked legs: 0.3 preview

Introduced in **0.3.0-beta.1** as read-only groundwork. It includes v0.2.7 recovery
and follow-up fixes but is not the completed 0.3 disruption workflow. For a stable
maintenance update, choose v0.2.11. Installing a prerelease remains a deliberate
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

## Retained Plan (Beta.4)

The same Status entity also exposes a separate local history of previously
observed bookings. It begins collecting only after this preview is installed;
it cannot reconstruct bookings that disappeared before its first good review.

- `retained_booked_legs`: at most 64 records, sorted by booked departure, with
  a stable scoped `booking_id`, endpoints, departure/arrival and first/last seen
  timestamps. No raw calendar title, location, description or UID is stored.
- `retained_booked_leg_count`: the number currently retained, not a count of
  trains actually taken or completed.
- `retained_plan_source`: `calendar`, `calendar_unavailable`,
  `retained_after_restart`, `not_reviewed`, or `simulation_excluded`.
- `retained_plan_truncated`: coverage is incomplete because the incoming overview
  or retained store hit its limit. It stays set while that retained history
  remains; it is not a claim that every expected train was captured.
- `retained_plan_last_calendar_review_at`: last successful calendar review in
  this runtime, not a guarantee the upstream feed itself refreshed. Unknown
  after restart until a successful review; stored per-leg last-seen timestamps
  remain available separately.
- `retained_plan_persistence_error`: local load/save failed; the in-memory view
  can remain useful, but restart retention is not assured. A load failure
  protects the unreadable store from overwrite; fix storage and reload the
  integration before writes resume. Failed saves retry on subsequent reviews.

Each record distinguishes these booked windows:

| Window | Meaning |
| --- | --- |
| `upcoming` | Booked departure is still ahead |
| `booked_underway` | Between booked departure and booked arrival |
| `booked_window_elapsed` | Booked arrival time has passed, not proof of arrival |
| `arrival_unknown` | Departure has passed but no timed arrival was supplied |

Every outcome is `unconfirmed` and evidence is `calendar_only`. Existing rail
observations and arrival collection are separate; this preview does not yet
reconcile them into the retained plan. `in_latest_response: false` means the leg
was absent from the latest successful bounded calendar response, not cancelled.
During an outage, that flag describes the last successful response, not today.

Exact duplicates share an ID. Equivalent timezone representations do not change
identity. Changes to booked departure, arrival, title or location create a new
record; the earlier intent remains separately visible. This conservative rule
avoids merging competing bookings without a reliable calendar UID, but can show
both versions of an edited booking. It is not a booking-revision resolver, a
train service identity or evidence that the traveller boarded either train.

Records expire 48 hours after booked arrival, or departure if arrival is unknown.
Bookings over 24 hours long are excluded. New bookings use the existing 30-hour
lookahead and 16-leg overview limit. If 64 retained records are exceeded, current
response records take priority, then recent history; truncation is explicit.
New/removed records save immediately. Unchanged reviews checkpoint last-seen
times at most every 30 minutes, so a sudden restart may restore an older
last-seen time. Expiry is pruned on real reviews and startup, not by a background
timer while HA is stopped. Simulations never change or expose the real plan.

This is read-only groundwork: it never restores a future alarm from cached
bookings, changes next-train selection, makes provider calls, updates a calendar,
or treats an unavailable calendar as healthy. Protect HA storage, Recorder and
backups: station labels, timestamps and hashed IDs are private, not anonymous.
Expiry from this store does not delete older Recorder history, exports or backups.
Plan details are deliberately omitted from downloadable diagnostics.

## Important Limits

Completed bookings drop out of the upcoming overview as the calendar window
advances, but remain in the separate bounded retained view. Neither view is a
claim ledger or a live multi-leg monitoring engine. During
calendar outage it is unavailable, not a trustworthy empty travel day. Minimal
active-leg recovery remains separate and does not synthesize the missing list.

Early-termination recognition, live connection-risk alerts, plan-wide quota
scheduling, replacement-train search and explicit route adoption remain future
work. The known early-termination acceptance test is still an expected failure.
Keep fallback alarms and consult operator advice during real disruption.

The upcoming list is not persisted by that feature or included in diagnostics;
the separate retained plan is persisted locally as described above.
It does contain private station labels and journey times in HA attributes and
service responses; Recorder, connected consumers and backups can retain them.
Protect the installation and inspect exports before sharing.
