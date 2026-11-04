# Proposed connection and recovery state contracts

Updated 4 November 2026. Design contracts with partial local implementation;
see the delivery plan for verified scope. Confirmation persistence and controls
are implemented locally; live evidence/provider integration remains pending.

| Record | Identity and owned state |
| --- | --- |
| Booked leg | Calendar-scoped booking identity and revision; original stations, aware departure/arrival times; source presence and expiry |
| Connection | Ordered inbound/outbound booking IDs and revisions; explicit confirmation; allowance override; assessment evidence references |
| Preferences | Configurable global 10-minute fallback; station defaults; saved suggestion templates that never grant confirmation |
| Observation | Provider, dated service identity, station, event type, scheduled/predicted/actual time, observed time, freshness and provenance |
| Connected journey | Confirmed ordered leg links, origin and final destination; never infer final destination from the last event of the day |
| Disruption | Affected connected journey and legs, matched positive evidence or labelled user report; evidenced recovery origin |
| Recovery option | Complete ordered route to final destination, internal transfers, source/freshness, limits and affected booked legs |
| Adoption | Explicit selected option/version and revalidation result; active replacement legs; original booked baseline retained |
| Alert record | Connection/disruption identity, assessment transition, evidence references and delivery hand-off result |

## Proposed invariants

- Use UTC instants for arithmetic and retain appropriate local display zones.
- Only confirmed booking-pair connections produce connection-risk announcements.
- Apply override, then station default, then global fallback; expose the source.
- Missing/stale arrival or departure evidence cannot become a confident live margin.
- Negative predicted margin is at risk; missed needs distinct positive outcome evidence.
- Booking time/endpoint changes invalidate the affected confirmation; preserve its
  audit history and require renewed confirmation. Missing calendar data alone is
  neither a cancellation nor a booking edit.
- Saved templates may prefill settings but always require confirmation for new pairs.
- Adoption requires complete destination coverage, fresh revalidation and an explicit
  user action. Repeat submission must be idempotent. No implicit calendar writes.
- Adoption supersedes affected downstream legs for tracking only. Original evidence
  remains available and unrelated journeys remain unchanged.
- Persist confirmations, adoptions and notification deduplication with versioned
  schemas, scoped storage and expiry. Restore evidence with its original timestamps.
- Storage failure must surface degraded state; do not present an unsaved confirmation
  as durable. Provider fetches remain behind the broker.

## Policies to settle before implementation

Retention duration; bounded search window/change count; internal replacement
transfer confirmation; alert thresholds/hysteresis; cross-station transfers;
booking identity/revision migration and UI commands. The proposed edit invalidation
policy above requires review before wiring it into runtime.

## Implemented station-time evidence contract

`connection_evidence.py` defines provider/dated-service references and explicit
station arrival/departure observations with scheduled, predicted or actual kinds.
The pure assessor requires confirmation, expected matched services, resolved
station, allowance, current time and an explicit freshness window. It returns
unconfirmed, unknown, at risk or viable, plus a stable reason and optional margin.
Unknown and unconfirmed results have no numeric live margin.

Scheduled values are not substitutes for missing predictions. Actual arrival
can support a current onward connection when fresh; actual onward departure
returns unknown for separate outcome handling. Future observations, impossible
actual event timestamps and elapsed predictions cannot produce live confidence.
No production freshness threshold or polling schedule is enabled by this module.
See [ADR 0009](adr/0009-confirmed-connection-evidence.md).

The departure bridge consumes an existing provider-normalized RailObservation
only when its live prediction is available, current, not cancelled/retained and
not simulated. It retains the original observed time. This bridge does not
resolve incoming destination arrival and is not wired into connection polling.
