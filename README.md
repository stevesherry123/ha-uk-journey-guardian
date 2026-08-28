# UK Journey Guardian

UK Journey Guardian is a proactive Home Assistant travel engine for timely
departures, live UK rail disruption handling, multimodal route decisions, and
split-journey monitoring.

The current alpha targets Home Assistant 2026.8 or newer.

> [!WARNING]
> UK Journey Guardian is currently an alpha project. The first release provides
> the integration foundation and shadow-mode calendar decisions. Do not remove
> an existing travel alarm or rely on it as the sole source of departure advice.

## Design principles

- no stations, cities, homes, workplaces, or notification targets are built in
- origins and destinations come from configuration and calendar events
- more than one regular destination can be configured
- preparation and station-arrival buffers are configurable per traveller
- the route to the station can be walking, driving, cycling, or automatically chosen
- split journeys are represented as separate calendar events and monitored by leg
- departure location and time select the live service; destination confirms it
- credentials and journey details are redacted from diagnostics
- provider calls are guarded by explicit quotas and failure fallbacks

## Alpha capabilities

- UI-based Home Assistant configuration
- privacy-preserving diagnostics
- generic normalization of the next timed calendar journey
- optional multiple destination zones
- per-traveller preparation time, station buffer, and station-access preference
- a persistent shared TransportAPI budget with an urgent-call reserve
- status, next-departure, decision-path, API-budget, and data-health entities
- a **Review now** button and `journey_guardian.review_now` action
- automated validation and unit tests

The alpha does not yet call TransportAPI, Google Routes, or local transit
providers. Those providers will be added behind the shared coordinator and quota
guard after shadow-mode decisions have been verified.

## Calendar format

The preferred and development-tested calendar source is a TripIt calendar feed,
but any Home Assistant calendar entity can work when it supplies timed events in
the expected format.

Each rail leg must be a separate event whose title contains both endpoints:

```text
Rail operator - Example Central to Example Junction
```

The required separator is ` to ` (case-insensitive). The event must have a timed
start, not only an all-day date. Setting the event location to the departure
station is strongly recommended as an independent confirmation. For split
journeys, create or import one event per leg.

See [PREREQUISITES.md](PREREQUISITES.md) for provider accounts, calendar setup,
API-key security, and notification requirements.

## Departure calculation

Journey Guardian keeps the two safety margins independent:

```text
leave time = train departure - station buffer - route duration
start getting ready = leave time - preparation buffer
```

Both buffers are user choices. The home-to-station route duration is requested
for the configured access mode. Selecting walking explicitly uses a walking route;
automatic mode may compare suitable modes when that capability is implemented.

## Installation during alpha

During development, add this repository to HACS as a **custom repository** of
type **Integration**. HACS then installs it under `custom_components/` in the
Home Assistant configuration directory.

After downloading it:

1. Restart Home Assistant.
2. Open **Settings → Devices & services → Add integration**.
3. Search for **UK Journey Guardian**.
4. Select the calendar, traveller, and zones. Provider credentials can be
   deferred until the related monitoring feature is enabled.
5. Keep existing travel alarms enabled while validating shadow-mode results.

The project may be submitted to HACS's default catalogue after it is stable,
branded, released, and passing HACS and Home Assistant validation. HACS indexes
the GitHub repository; it does not replace or host the source repository.

## Entities

- `sensor.journey_guardian_status`
- `sensor.journey_guardian_next_departure`
- `sensor.journey_guardian_decision_path`
- `sensor.journey_guardian_transportapi_calls_today`
- `binary_sensor.journey_guardian_data_healthy`
- `button.journey_guardian_review_now`

Entity IDs can differ if similarly named entities already exist.

## Actions

`journey_guardian.review_now` immediately reviews the configured calendar and
returns the normalized engine snapshot when a response is requested.

## Privacy and security

The repository must never contain personal calendar data, names, addresses,
private entity IDs, configuration-entry IDs, API credentials, tokens, or
notification targets. Tests use fictional locations and times. Downloaded
diagnostics redact configured entities, credentials, destinations, and journeys.

Please report security concerns according to [SECURITY.md](SECURITY.md).

## Roadmap

1. destination profiles and station-code resolution
2. TransportAPI station-board client with enforced daily quota
3. unified manual-review decision tree
4. scheduled departure and leave-time engine
5. lightweight interchange monitoring
6. Google walking/driving estimates and UK local-transit comparison
7. notification adapters and wearable entry points
8. HACS default-catalogue submission after stable releases

The maintained development list is in [BACKLOG.md](BACKLOG.md).

## Development

```bash
python -m pip install pytest ruff
ruff check .
pytest
python -m compileall custom_components/journey_guardian
```

## Licence

UK Journey Guardian is released under the MIT Licence.
