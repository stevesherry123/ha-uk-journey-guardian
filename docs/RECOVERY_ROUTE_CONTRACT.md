# End-to-end recovery route contract (unreleased development)

This is a pure validation foundation. There is no search button, automatic
recovery query, replacement adoption or calendar write in this slice.

## Request context

A recovery request belongs to a specific confirmed connected journey. Its final
destination must be explicitly confirmed; it must not be inferred from the last
calendar booking of the day or an unrelated return journey. The starting station
must be supported by fresh provider-confirmed or user-confirmed evidence. GPS
proximity alone cannot establish a recovery origin. The caller supplies the time
the traveller will actually be ready to board at that station.

The runtime connection-plan/disruption layer still needs to construct this context;
setting a boolean in the pure data object is not a substitute for that integration.

## Complete route requirement

An option must start at the evidenced station and reach the request's final
destination through a contiguous sequence of train legs. A route ending at an
interchange after the original onward train has gone is rejected as incomplete.
No invalid or unsupported leg may be silently dropped to make a partial route
appear successful. Repeated services must be coalesced correctly by an adapter;
the validator rejects duplicate service legs and station loops.

Each leg requires scheduled baseline times, an explicit cancellation assessment,
and fresh matched departure/arrival predictions for the same dated service and
resolved endpoint stations. Timetable-only, actual/already-completed, retained,
stale, future-observed, mismatched or cancelled evidence cannot become a new
ready-to-select recovery option. All duration arithmetic uses UTC instants,
including repeated local clocks across daylight-saving changes.

## Transfers and limits

Every internal transfer must meet its applicable allowance using predicted times.
Resolved station defaults or explicit overrides can be supplied with their source;
otherwise the configurable global fallback applies. The caller must resolve saved
station names to station codes rather than silently ignoring user preferences.
The option records required/available minutes and provenance for each change.

The caller must explicitly supply maximum changes, maximum initial waiting time,
maximum journey duration and evidence freshness. The contract accepts at most
nine legs as a defensive structural bound. Tests exercise direct, one-change and
two-change shapes; this is not a claim that the current provider searches all
of them. No production waiting/duration policy is selected by these tests.
Railinfo's previously verified public overview advertises direct and one-change
searches; broader provider search and access remain separate discovery work.

## Identity, revalidation and uncertainty

The option ID binds the connected journey, endpoints, services and scheduled
baseline. A separate revision changes when predictions or transfer requirements
change. Refreshed observations with equivalent predictions can preserve the
revision, but validity is still bounded by the oldest required observation,
origin-evidence freshness and the first departure time.

Ticket acceptance remains explicitly unknown. A complete assessed option does
not establish ticket validity, reserved seating, physical boarding or guaranteed
transport. The future user-selection action must revalidate the complete route,
show the affected original legs and obtain explicit approval. Original bookings
and evidence must remain intact.

## Development Railinfo search adapter — 6 November 2026

`RailinfoClient.async_recovery_search` now accepts a confirmed recovery request
and makes one brokered `/journeys` query to its final destination. It uses the
raw journey-details cache, independently of the existing direct-service matcher.
It preserves the original observation time, rejects unhealthy cached results,
and checks freshness again after acquisition. Stale origins and readiness beyond
the supplied waiting limit are rejected before a provider request.

The pure `normalize_railinfo_recovery` adapter validates the previously observed
field shape: same-day direct and one-change train routes with explicit Darwin
predictions at both ends of every leg. It accepts at most 40 response candidates;
an oversized or malformed envelope is rejected whole. Unsupported candidates,
partial destinations, duplicate scheduled candidates (including cancellation
conflicts), missing predictions and unachievable transfers are excluded whole.
Valid options are ordered by final predicted arrival, then number of legs.

Status values distinguish `options_available`, `no_complete_route_in_response`,
`invalid_response`, `stale_response`, `provider_unavailable`,
`recovery_origin_not_current`, `readiness_exceeds_wait_limit` and
`unsupported_service_day`. No complete route in one response does **not** establish
that no route exists. A later user flow must offer an actionable manual fallback.

Current limitations: no overnight rollover, cross-station walking links, bus legs
or searches with more than one change. Caller-supplied waiting, duration and
freshness limits are still required; these tests do not choose production policy.
No extra network-wide searches are performed to fill provider coverage gaps.

This is an internal development API with fictional regression fixtures. It is
not connected to disruption detection, Home Assistant services or dashboard
buttons. The caller still needs to construct a request from confirmed connected
bookings and a valid recovery origin. User selection, full revalidation,
downstream supersession preview, adoption and continued tracking remain pending.
No automatic recovery or deployment is claimed.
