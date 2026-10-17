# Station progress

Station progress is optional and local to Home Assistant. It uses existing GPS
updates; it does not request additional phone updates or call a rail provider.

## Configuration

In the integration's options, enter station zone entity IDs in **Ordered station
zones**, one per line, in geographical route order. Use 2 to 100 unique zones.
Leave the field blank to disable the progress sensor. Existing installations
remain unchanged until this option is configured.

Use the actual entity IDs, including older IDs retained after a zone rename.
Zone display names must match the calendar origin and destination names, ignoring
case, repeated whitespace, and a leading `zzz ` prefix. Intermediate stations
need not be scheduled calls. The integration selects the segment between the
calendar endpoints and reverses its order for return journeys. Unmatched or
ambiguous endpoints produce `route_unmatched`, not a guessed route.

Zones must provide valid coordinates and a radius greater than zero and no more
than 1,000 metres. A missing/invalid configured zone produces `route_unavailable`.
The configured traveller must have an active GPS device-tracker source.

### Alternative paths

Use **Alternative station paths** for optional diversions. Each line starts and
ends at stations on the base route, in base-route order, with extra stations
between them, separated by `>`:

```text
zone.example_junction > zone.example_diversion > zone.example_rejoin
```

Configure up to four paths and 100 unique stations in total. Extra stations must
not appear in the base list or another alternative. Return journeys reverse all
paths automatically. Calendar endpoints can also be stations on an alternative.

Fresh, unambiguous GPS at a path-specific station narrows the possible routes.
An observation at a shared station cannot prove which branch was taken, even
after rejoining. If GPS misses a whole branch, the route remains uncertain.
Neither timetable expectations nor proximity to the rejoining station select a
branch. Route geometry or calendar-leg changes reset the observation history.

## Meaning of the sensor

- `current_station`: the station zone containing the accepted GPS uncertainty
  circle, or empty if no station can currently be identified.
- `last_observed_station`: the latest positively observed waypoint on this leg.
- `next_waypoint`: the next configured waypoint after that observation, **not**
  an assertion that this is the next station the train will physically pass.
- `location_age_seconds`: age of the source tracker's last state update, not the
  person entity's update. Unchanged GPS states may be conservatively treated as
  stale even if the phone repeats the same fix.
- `rail_arrival_confirmed`: always false. GPS is proximity evidence only.
- `candidate_route_count` and `route_selection`: remaining possible paths and
  whether the route is configured, observed, or still ambiguous.
- `next_waypoints`: possible next configured markers. `next_waypoint` is empty
  unless all remaining paths agree, including whether the route has ended.
- `route_waypoints`: labels for the selected route, empty while ambiguous.
  `waypoint_count` is empty when possible routes have different lengths.

Fixes older than five minutes, accuracy worse than 100 metres, uncertainty
circles not wholly inside a station zone, and overlapping station matches cannot
advance progress. Previously observed stations do not move backwards. If the
phone skips updates while passing several stations, those passages are not
invented. Normal person changes update the sensor immediately; a minute timer
checks freshness even when the person stops updating.

## Scope and privacy

Progress starts no earlier than two hours before the selected calendar departure
and normally follows the selected calendar leg. A fresh accepted fix beyond the
origin, timestamped after booked departure, makes that leg eligible for bounded
continued GPS monitoring. An origin-only visit or pre-departure fix does not.

GPS monitoring may continue for up to **three hours after booked arrival**, even
when the calendar selector moves to a later booking or the calendar temporarily
becomes unavailable. It stops on destination proximity, the next booked train's
departure, expiry, simulation, or invalid route configuration. It is monitoring
of booked intent, not proof that the traveller boarded or that a train is delayed.
An explicit calendar removal before booked arrival clears monitoring, except
while the calendar reports unavailable. Configured-zone loss clears progress.

The sensor exposes `monitoring_extended`, `booked_arrival_at`, and
`monitoring_deadline`. A destination fix remains visible for that update; the next
update can switch to the next booking or idle. GPS proximity never changes
railway-arrival evidence or compensation classifications.

This is a GPS-only extension, not a retained multi-leg rail engine. The calendar
selector and next-train notifications remain unchanged. Existing provider-based
arrival collection remains separate. Only explicitly configured diversions can
be followed; wake-up and announcement behaviour are unaffected. Intentional
touring breaks are outside scope: separate commuting bookings remain supported
without adding a dedicated break state.

The latest route fingerprint, candidate-route fingerprints and indices, and
observation time are stored locally for restart recovery, accepted for at most
24 hours and only for the same leg and route. Eligible monitoring also stores
booked departure/arrival times, a known next departure, and endpoint fingerprints,
valid only within the
three-hour extension and resolvable uniquely against current configured zones.
Coordinates, station names, entity IDs and calendar titles are not written to
that store. Fingerprints are pseudonymous, not anonymized location information.
The stable timestamp fingerprint format changes in v0.2.4, so upgrading may
reset an older saved observation once; fresh accepted fixes establish progress.
The sensor itself contains station names and observation times: Home Assistant's
normal history/recorder and backups can retain these. Exclude the sensor from
Recorder if location-history retention is unwanted. Route options are redacted
from integration diagnostics. No new personal data is sent to external services.
