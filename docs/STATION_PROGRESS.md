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
and resets when the coordinator selects another leg or simulation is enabled.
The current calendar selector stops selecting a leg at its booked end time.
Consequently this is not a complete delayed-travel or multi-leg journey tracker.
Only explicitly configured diversions can be followed. It does not modify
wake-up notifications, existing
announcement automations, arrival collection, or Delay Repay decisions.

The latest route fingerprint, candidate-route fingerprints and indices, and
observation time are stored
locally for restart recovery, accepted for at most 24 hours and only for the same
leg and route. Coordinates and station names are not written to that store.
The sensor itself contains station names and observation times: Home Assistant's
normal history/recorder and backups can retain these. Exclude the sensor from
Recorder if location-history retention is unwanted. Route options are redacted
from integration diagnostics. No new personal data is sent to external services.
