# Booking-check warnings (development)

This development slice adds a booking-specific warning to the existing travel
dashboard when a live rail check cannot match the timetable or resolve the
stations. A successful calendar read does not mean the train was verified.

The warning asks you to check the stations/times and supply any missing onward
booking. It does not assert that a missing leg exists merely because a check
failed. Provider outages, permission denial and quota failures are not described
as proof that your booking is wrong.

## Evidence and limits

- `current_rail_issue` records the failed check's completion time, stable error
  category, stage and hashed booking identity. Its time can be later than the
  calendar snapshot's `checked_at`: they describe different operations.
- The dashboard shows the last failed-check time, not a claim that a fresh check
  is running. A newer check replaces that evidence; a booking change prevents
  the warning from carrying over. No warning does not imply verification.
- Identity includes departure, arrival, title, location and endpoint labels.
  Changing a booking cannot inherit an unrelated warning. A successful live
  check clears the current failure. Simulation and idle views do not display it.
- The older `last_live_rail_error` remains a historical diagnostic. It alone
  cannot establish that the currently selected booking failed verification.
- The existing bounded check history restores the latest actionable failure
  after restart for the exact booking, integration entry, calendar and provider.
  Older records without a scoped booking key are not restored as warnings.
  A later success or non-booking failure supersedes the older warning. Restored
  evidence retains its original check time and cannot certify a live match.
  No new recorder, poller or provider requests are introduced.

## Bounded timetable investigation

The internal Railinfo client can check one explicitly supplied alternative
station for an exact booking. It uses the existing broker and journey-details
cache. The alternative must be a resolved station distinct from both the origin
and the originally booked destination; it is not inferred from calendar gaps.

A proposal requires one direct train with the exact scheduled departure and
arrival, matching station codes and UK service day. Expected times never count
as scheduled evidence. Duplicate or competing rows, cancellation, missing
identity, ambiguous clock changes, overnight bookings and stale or oversized
responses do not produce a proposal. The result carries the original booking
fingerprint, dated service identity and a five-minute evidence lifetime.
Uniqueness applies only to this response for the supplied alternative, not to
all services or possible destinations. It does not verify live operation,
the traveller's intention or ticket validity.

## What is not implemented

The internal lookup has no HA service, dashboard action or scheduled caller.
There is no automatic destination discovery, correction, confirmation action
or added phone/watch announcement. A proposed match must receive
explicit confirmation before adoption in the later workflow. Detecting a truly
missing onward booking needs evidence of intended journey continuity; the app
must not guess a final destination from unrelated calendar events. Onward-train
suggestions remain separate future development, not a warning prerequisite.

This is unreleased development based on the existing rail-connections branch.
It is not merged with the optional flight preview or newer mainline documentation
changes. Merged-tree testing and owner acceptance are required before release or
HA installation. Existing published versions and the live installation are
unchanged.

## Validation of this development slice

The network-disabled suite passed 704 tests with the existing early-termination
expected failure. The remaining dashboard-serving test passed separately with
local-only network access. Ten Node dashboard tests passed, including warning
bounds and plain-text rendering. Lint, privacy scan and diff checks passed.
No physical-device delivery or live HA acceptance is implied. Later work on the
parallel connection branch requires its own merged-tree validation.
