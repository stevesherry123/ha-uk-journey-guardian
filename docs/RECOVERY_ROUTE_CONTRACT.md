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

The next work package is provider search acquisition/normalization with bounded
candidate counts and clear unsupported/no-complete-route outcomes, followed by
selection and continued tracking. Partial results must never be presented as a
complete solution when the final destination has not been reached.
