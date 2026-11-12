# ADR 0009: Confirmed connections and evidence-backed transfer margins

- Status: accepted product decisions; provider integration pending
- Date: 4 November 2026
- Provenance: owner architecture review and split-journey acceptance discussion

## Context

Separate calendar bookings express booked trains. Station continuity alone cannot
establish an intended connection, and scheduled arrival is not a live prediction.
The reported product gap is missing connection-risk warnings and disruption advice.

## Decision

Require explicit confirmation for each booked connection. Saved recurring rules
may prefill suggestions but never auto-confirm a pair. Apply a booked-pair
transfer override, then a station default, then a configurable global fallback
initially 10 minutes, exposing its provenance. These are user preferences rather
than official minimum interchange times.

Live assessment consumes independent incoming arrival and onward departure
observations at the same resolved interchange. Each observation identifies a
provider and dated matched service, event type, scheduled/predicted/actual kind,
event instant, observation instant and retained status. Preserve original source
age; rendering, cache reuse and restart do not refresh evidence timestamps.

Only fresh matched live evidence on a confirmed pair produces a live numeric
margin. Timetable-only, stale, retained, missing, wrong-service, wrong-station or
elapsed prediction data yields unknown, with an explicit reason and no numeric
live margin. The integration must not fabricate an arrival prediction by adding
a departure delay to scheduled arrival. An actual onward departure belongs to
outcome/disruption handling, not a current viable-connection display.

Freshness is an explicit caller-supplied policy. Tests using five minutes do not
establish a polling cadence or user-approved production freshness threshold.
The assessment uses UTC elapsed time across daylight-saving changes. Negative
predicted margin means at risk, not proof that the traveller missed a connection.

Warn when available transfer falls below the allowance using the existing travel
announcement route and a persistent dashboard warning. The local
[warning-delivery policy](../CONNECTION_ALERTS.md) now implements durable
deduplication and initial meaningful-change defaults.

Recovery targets the final destination of the confirmed connected journey and
includes routes with changes. The user approves a complete replacement route;
tracking follows its legs while preserving original bookings and evidence.
No partial route may be presented as complete recovery. Provider capability and
bounded search limits must be established before enabling recovery.

## Implementation status and consequences

Confirmation persistence, development controls and allowances exist locally.
The pure typed evidence assessor, existing normalized-departure bridge and
boundary tests are implemented. Provider arrival mapping and opt-in connection
monitoring have since been added locally; recovery search remains pending.
Use a separate arrival/event evidence contract instead of guessing new meanings
for the existing departure-centric RailObservation model. Provider identity and
station resolution must be established upstream of this assessment. Generic
assessment projection omits service identities; detailed evidence remains private.

Unknown does not mean healthy, on time, viable or cancelled. Explain the missing
fact and retain booked intent while evidence or provider support is unavailable.

## Local monitoring update: 4 November 2026

An opt-in Railinfo-only scheduler now connects the evidence assessor to the
development dashboard. It defaults to off, has durable daily/cadence limits
and respects the existing live-notification master for connection warnings.
See [warning delivery policy](../CONNECTION_ALERTS.md). Five minutes is its initial
development freshness policy; production acceptance remains pending.
