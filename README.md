# UK Journey Guardian

UK Journey Guardian is a proactive Home Assistant travel engine for timely
departures, live UK rail disruption handling, multimodal route decisions, and
split-journey monitoring.

The current alpha targets Home Assistant 2026.8 or newer.

> [!WARNING]
> UK Journey Guardian is currently an alpha project. The current release provides
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
- planned, active, and completed calendar-journey lifecycle states
- optional multiple destination zones
- per-traveller preparation time, station buffer, and station-access preference
- preparation, leave-home, and station-arrival timestamp entities
- editable conservative station-access and early-warning timing
- a persistent shared TransportAPI budget with an urgent-call reserve
- status, next-departure, decision-path, API-budget, and data-health entities
- a **Review now** button and `journey_guardian.review_now` action
- quota-free on-time, delayed, cancelled, split, and provider-outage simulations
- an explicit **Simulation active** diagnostic entity
- automated validation and unit tests

The alpha does not yet call TransportAPI, Google Routes, or local transit
providers. Until live routing is added, station-access timing uses a configurable
conservative fallback and is explicitly classified as inferred. Providers will
be added behind the shared coordinator and quota guard after shadow-mode
decisions have been verified.

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

A recognized journey remains active until the timed calendar event ends. This
provides the lifecycle window needed for delayed-service and interchange checks;
provider monitoring will be added in a later feature slice.

See [PREREQUISITES.md](PREREQUISITES.md) for provider accounts, calendar setup,
API-key security, and notification requirements.

The integration's architectural boundaries, security defaults, state-handling
rules, and provider trust model are recorded in
[ADR 0001](docs/adr/0001-layered-journey-engine.md).

Accepted development work follows the repository's
[release policy](docs/RELEASE_POLICY.md): unless explicitly held as draft work, a
completed change is published to `main`, tagged, released, and verified before it
is presented as ready for a Home Assistant upgrade.

## Departure calculation

Journey Guardian keeps the two safety margins independent:

```text
leave time = train departure - station buffer - route duration
start getting ready = leave time - preparation buffer - early-warning margin
```

The safety margins and conservative station-access duration are user choices.
Until live routing is enabled, the timing entities include
`source: configured_fallback` and `classification: inferred`. Selecting walking
explicitly will use a walking route when that capability is implemented;
automatic mode may compare suitable modes.

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

After installation, open **Settings → Devices & services → UK Journey
Guardian → Configure** to tune the preparation, early-warning,
station-arrival, and conservative station-access durations.

The project may be submitted to HACS's default catalogue after it is stable,
branded, released, and passing HACS and Home Assistant validation. HACS indexes
the GitHub repository; it does not replace or host the source repository.

## Entities

The integration creates **Status**, **Next departure**, **Prepare at**, **Leave
home at**, **Station arrival at**, **Decision path**, **TransportAPI calls
today**, **Data health**, and **Review now** entities. Home Assistant generates
their entity IDs from the configured device name, so IDs can differ between
installations.

## Actions

`journey_guardian.review_now` immediately reviews the configured calendar and
returns the normalized engine snapshot when a response is requested.

`journey_guardian.simulate_journey` activates a synthetic scenario using generic
locations and an offset from the current time. While it is active, reviews bypass
the configured calendar and no TransportAPI request or quota reservation can
occur. Supported scenarios are `on_time`, `delayed`, `cancelled`,
`split_on_time`, and `provider_unavailable`.

`journey_guardian.clear_simulation` explicitly returns reviews to the configured
calendar. Simulations are held only in memory and also clear when Home Assistant
restarts or when the synthetic journey finishes.

> [!IMPORTANT]
> Always confirm that the **Simulation active** entity is off before relying on
> Journey Guardian for a real journey.

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
4. internal scheduling and actionable departure notifications
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
