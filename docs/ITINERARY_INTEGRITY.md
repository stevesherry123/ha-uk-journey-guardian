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
  is running. The warning remains until a successful check or a booking change;
  it does not expire into an implied successful verification.
- Identity includes departure, arrival, title, location and endpoint labels.
  Changing a booking cannot inherit an unrelated warning. A successful live
  check clears the current failure. Simulation and idle views do not display it.
- The older `last_live_rail_error` remains a historical diagnostic. It alone
  cannot establish that the currently selected booking failed verification.
- This slice retains one scoped failure in memory. The existing check-history
  store still records failed checks, but rebuilding scoped warnings after a
  restart is not implemented here. No new recorder, poller or provider requests
  are introduced.

## What is not implemented

There is no automatic correction, candidate-service search, confirmation action
or added phone/watch announcement in this slice. A proposed match must receive
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

The backend suite passed 696 tests with the existing early-termination expected
failure. Three frontend-serving tests passed separately with local-only network
access; ten Node dashboard tests passed, including warning bounds and plain-text
rendering. Repository lint, compilation, privacy scan and diff checks pass.
No physical-device delivery or live HA acceptance is implied. Later work on the
parallel connection branch requires its own merged-tree validation.
