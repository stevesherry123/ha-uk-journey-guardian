# Experimental Flight Preview

Development branch: `development/flight-travel-analysis`. This is an opt-in,
calendar-only shadow module within Journey Guardian, not a live flight tracker.
It does not change the rail engine or require a flight provider subscription.

## Enable And View

1. Install the flight-development prerelease, not the stable rail release.
2. In the integration's Configure options, enable **experimental read-only
   flight preview**. It is disabled by default, including on existing installs.
3. Set airport display time zones, one `IATA=IANA` profile per line. For example:
   `LHR=Europe/London`. Use the airport's actual zone, not a fixed UTC offset.
   Unknown airports display UTC explicitly. Profiles are not routing settings.
4. The integration creates a separate **Flight preview** sensor. Confirm its
   entity ID in HA; it may differ from the example below.
5. Load `/journey_guardian/journey-guardian-card.js` as a JavaScript module
   Lovelace resource, with a new version query when upgrading. The same resource
   registers the rail card and the separate flight card.
6. Add this card on a separate development dashboard:

```yaml
type: custom:journey-guardian-flight-card
entity: sensor.uk_journey_guardian_flight_preview
```

Disable the option to stop flight parsing and the flight sensor. If a previously
created entity remains in the HA registry, it will be unavailable while disabled.
Reverting the development install to the previous beta is also possible through
HACS; no calendar or rail routing profile migration is performed.

## What This Version Reads

The existing calendar fetch is reused, with its existing 30-hour lookahead and
configured upstream refresh interval. Opening a dashboard does not force an
upstream TripIt refresh. The integration's calendar refresh button remains
available; no extra flight polling is introduced.

Supported titles are `ZZ1234 AAA to BBB`, or `[Flight] AAA to BBB` with an
explicit category. These are synthetic examples. IATA endpoints and timed,
offset-qualified start/end instants are required. All-day, floating-time,
unreadable and non-positive or over-24-hour flight durations are not guessed.
Unsupported explicit flight records are counted visibly rather than silently
presented as a healthy empty itinerary.

Marketing flight numbers are retained separately from a supported calendar
operating-service line such as `Example Air 4321, Terminal 2, Gate ...`.
No airline-code translation or live service matching is attempted. Exactly two
terminal fields can be shown as booking information. No gates are inferred.

Elapsed durations and connection gaps use UTC instants. Airport-local display
uses configured IANA zones, including daylight-saving rules on the travel date.
A UK/European clock change does not imply that North America changes that day.

## Connection And Completion Boundaries

Adjacent bookings at the same airport with a non-negative gap of up to 24 hours
are shown as **possible calendar connections**. This is a display grouping,
not proof of a single ticket, through-checked bags or a viable transfer.
An airport change or overlapping flight is not a valid connection grouping.

```text
Booked flight A ----> scheduled gap ----> booked flight B
                     not a safety assessment
```

After the first booked arrival time passes, its bounded local context can be
retained while it connects to a still-present later calendar booking, including
through an integration reload. Future/active bookings removed from the calendar
are not resurrected from storage. The preview clears when no later booking
remains; it does not claim that the traveller has arrived.

States describe schedule windows: `scheduled`, `within_scheduled_flight`,
`connection_window`, `no_flights`, `needs_attention` or unavailable. They never
mean confirmed take-off, landing, cancellation or destination arrival.
Terminal differences must not become transfer instructions without current
airport/airline evidence.

## Privacy And Isolation

Only allowlisted service IDs, airports, instants and terminal labels enter the
sensor. Raw descriptions, URLs, booking references and passenger names are not
stored by this module. Downloadable diagnostics redact the flight projection
and airport profiles. The bounded local HA storage is private; enabled sensor
attributes are nevertheless itinerary data visible to authorised HA users and
may be recorded by HA Recorder. Do not expose this dashboard publicly.

Flights never enter rail selection, station routing, station progress, wake
alarms, rail notifications, Delay Repay or the rail arrival collector. No live
flight API calls, airport leave-home calculations or flight alerts exist yet.
The Apple Watch rail briefing is unchanged and is not a flight briefing.

## Road-Test Checklist

- Before leaving: compare every flight, date, endpoint, airport-local time and
  elapsed duration against the booking. Confirm the rail dashboard stays idle
  if the calendar contains only flights.
- During the connection: verify the first scheduled leg remains visible, the
  gap is correct, and a reload preserves context. Treat status as scheduled,
  not proof the aircraft or traveller moved.
- On the return: compare local dates and offsets, especially overnight travel
  and different daylight-saving transition dates.
- After the final scheduled arrival: verify the preview empties at the next
  calendar review, with no claim of actual arrival.
- Report missing/duplicate records, wrong time zones or stale data. Do not use
  the preview instead of airline/airport information for boarding decisions.

## Next Decision Points

Choose a flight-status source and its permitted cost/rate budget; date-qualified
operating/codeshare identity; a per-itinerary same-ticket/baggage policy;
airport-specific access and check-in/security policy; and explicit alert opt-in.
Keep these behind flight-specific interfaces and tests. Do not reuse rail
allowances, station Waze sensors or compensation thresholds for air travel.
