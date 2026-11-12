# Calendar Transport Classification

Rail selection must not turn every timed `Origin to Destination` event into a
train. In mixed TripIt calendars, a flight title can have exactly that shape.

## Selection Rules

- A timed route and the existing booked-window rules are still required.
- Explicit non-rail category lines in the title or description exclude an event.
  This includes TripIt's `[Flight]`, `[Parking]`, `[Lodging]`, car rental, cruise,
  ferry and other supported non-rail categories. Matching ignores case and
  normalizes whitespace. A non-rail category wins if category evidence conflicts.
- Flight-prefixed titles and airline-number/airport route titles such as
  `ZZ1234 AAA to BBB` are excluded even without a description.
- `[Rail]` and `[Train]` category evidence remains valid. A rail journey to an
  airport, or notes mentioning a connecting flight, is not excluded simply for
  containing the word airport or flight.
- Three-letter endpoint codes alone are not used to infer transport type: rail
  CRS and airport IATA codes can overlap.
- Untagged route calendars keep the existing compatibility contract. This is an
  exclusion safeguard, not a complete global transport classifier. An untagged
  non-rail event without flight-title evidence can remain ambiguous. Use a
  rail-only source or explicit category lines for mixed calendars.

The same selection path supplies operational timing and the other-bookings
overview. A rejected flight cannot create a rail timing or station-routing call.
Old flight-number labels are also rejected when restoring underway intent or
the retained rail overview; other minimal saved records cannot recover category
metadata that older releases did not retain.

## Separate Flight Development

Flight analysis is reserved for `development/flight-travel-analysis`, not this
rail correction. That work needs an explicit flight model, timezone-safe airport
times, airport access/check-in/security/parking boundaries, codeshare handling,
layover interpretation, and independent notification opt-in and tests. Rail
station margins and rail compensation thresholds must not be reused as flight
policy. This correction adds no flight monitoring or flight alarm support.

## Verification And Deployment

Regression tests cover mixed calendars, flight-only engine snapshots, alternate
non-rail categories, conflicting tags, valid airport-bound rail, the booking
overview, and old saved flight labels. Fixtures are fictional; do not add real
itineraries or TripIt links to the repository.

The correction originated on `fix/calendar-transport-classification` and is
included in dashboard prerelease `v0.3.0-beta.10`. Activation requires installing
that release and restarting HA. No calendar events or household notification
settings are edited. The flight-analysis branch remains independent.
