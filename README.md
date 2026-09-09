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
- an operational-phase entity with exact, cancellable boundary scheduling
- restart-safe local notification deduplication
- bounded preparation reminders and mode-aware station-access alerts
- checkpoint rail-status notifications with delay, platform and calling-point data
- a shared quota-enforcing provider request broker with cache and in-flight
  deduplication
- explicit rail-data freshness and bounded stale-data handling
- offline station-code resolution and defensive rail-board normalization
- deterministic service matching with stable privacy-safe service identities
- manual and opt-in automatic live-rail checks through the shared quota broker
- editable conservative station-access and early-warning timing
- a persistent shared TransportAPI budget with an urgent-call reserve
- status, next-departure, decision-path, API-budget, and data-health entities
- a **Refresh calendar and timings** button and
  `journey_guardian.review_now` action
- quota-free on-time, delayed, cancelled, split, and provider-outage simulations
- an explicit **Simulation active** diagnostic entity
- automated validation and unit tests

Automatic TransportAPI monitoring is off by default. When explicitly enabled in
the integration options, Journey Guardian makes one live check approximately 150,
90, 45, and 10 minutes before the selected departure. Each checkpoint is claimed
in persistent private storage before network access, and every request remains
behind the durable budget. Rail simulations remain provider-free.

The last successful rail observation remains visible between checkpoints. It is
labelled `retained` before departure and `historical` after departure; only a
genuinely new `current` observation can produce a new live-rail notification.

When a Google Routes key is configured, calendar reviews calculate the
station-access leg using the traveller's current Home Assistant coordinates.
Automatic mode uses traffic-aware driving while the traveller is home and public
transport while away. Equivalent requests use an adaptive cache, refreshing more
often only as the planned station departure approaches. Missing
coordinates, credentials, routes, or provider availability retain the configured
conservative fallback and its explicit `inferred` classification.

The device page includes **Test station route now**, which bypasses the cache,
and a **Station access routing** diagnostic showing working, cached, fallback,
or error state. Planned journeys automatically force fresh station-access
checks about 6 hours, 2 hours, 45 minutes, and 15 minutes before departure so
traffic changes can move the actionable leave time without continuous polling.

### Station access profiles

For regular exceptions, integration options accept one station CRS code and mode
per line. A matching profile takes priority over the default mode; stations
without a profile keep the default policy. For example:

```text
CTR=driving
CRE=driving
EUS=transit
```

Valid modes are `driving`, `walking`, `bicycling`, and `transit`. If a calendar
station cannot be identified from a configured CRS, an explicit calendar code,
or a deterministic known station name, the profile is not guessed: Journey
Guardian uses the default mode and its conservative fallback if live routing is
unavailable.

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

When known, a CRS station code can be appended to the origin or location as
`[EXC]`, `(EXC)`, or `CRS: EXC`. The code is optional: the offline resolver can
also require one exact station-name match from a future provider Places response.
Conflicting and ambiguous station evidence is rejected rather than guessed.

A recognized journey remains active until the timed calendar event ends. This
provides the lifecycle window needed for delayed-service and interchange checks;
provider monitoring will be added in a later feature slice.

See [PREREQUISITES.md](PREREQUISITES.md) for provider accounts, calendar setup,
API-key security, and notification requirements.

The integration's architectural boundaries, security defaults, state-handling
rules, and provider trust model are recorded in
[ADR 0001](docs/adr/0001-layered-journey-engine.md). Operational scheduling,
simulation, and notification safety are recorded in
[ADR 0002](docs/adr/0002-operational-notification-safety.md).
Provider acquisition, freshness, quota, and stale-data contracts are recorded in
[ADR 0003](docs/adr/0003-provider-request-broker.md).
Rail normalization, station identity, and service matching are recorded in
[ADR 0004](docs/adr/0004-rail-normalization-and-matching.md).
The deliberately manual first live-provider gateway is recorded in
[ADR 0005](docs/adr/0005-manual-live-rail-gateway.md).
Destination calling-point and strict schedule matching are recorded in
[ADR 0006](docs/adr/0006-calling-point-and-schedule-match.md).
Shared-account quota reconciliation and durable live-error evidence are recorded
in [ADR 0007](docs/adr/0007-shared-provider-account-quota.md).

Accepted development work follows the repository's
[release policy](docs/RELEASE_POLICY.md): unless explicitly held as draft work, a
completed change is published to `main`, tagged, released, and verified before it
is presented as ready for a Home Assistant upgrade.

Development-only replay, connection-risk, diagnostic-review, and notification
preview tools are
documented in [Shadow-test review tools](docs/SHADOW_TEST_REVIEW.md). They have
no Home Assistant runtime wiring and do not change live travel decisions.

The current comparison with the documented legacy acceptance inventory is in
[Feature comparison](docs/FEATURE_COMPARISON.md).

### Notification delivery roadmap

The current integration creates local persistent notifications only. The next
notification slice will add an explicit delivery target (for example, a selected
Home Assistant mobile-app notify service), a safe **send test notification**
control, and per-event preferences. Its planned event vocabulary is already
scaffolded in `notification_plan.py`, but it is not yet wired into Home
Assistant and cannot send any new notification in this release.

The proposed defaults prioritise action: wake-up reminders, leave-now, material
rail changes, cancellations, connection risk, and provider failures. Repeated
"on time" reassurance stays opt-in, with a checkpoint cadence and deduplication
so it is useful rather than noisy. Timetable changes remain informational; they
will not automatically move the departure plan.

## Departure calculation

Journey Guardian keeps the two safety margins independent:

```text
leave time = train departure - station buffer - route duration
start getting ready = leave time - preparation buffer - early-warning margin
```

The safety margins and conservative station-access duration are user choices.
Provider results include `source: google_routes`, a `live_<mode>` or
`cached_<mode>` classification, the calculation time, selected mode and distance.
Fallback results remain
`source: configured_fallback` and `classification: inferred`. Automatic mode
uses driving at home and public transport away from home; walking, driving and
cycling can also be selected explicitly.

## Installation during alpha

During development, add this repository to HACS as a **custom repository** of
type **Integration**. HACS then installs it under `custom_components/` in the
Home Assistant configuration directory.

After downloading it:

1. Restart Home Assistant.
2. Open **Settings → Devices & services → Add integration**.
3. Search for **UK Journey Guardian**.
4. Select the calendar, traveller, and zones. Provider credentials can be
   deferred until the manual live-rail check is needed.
5. Keep existing travel alarms enabled while validating shadow-mode results.

After installation, open **Settings → Devices & services → UK Journey
Guardian → Configure** to tune the preparation, early-warning,
station-arrival, and conservative station-access durations. Live-calendar
notifications are deliberately disabled by default during shadow testing and can
be enabled on this screen. Simulation notifications remain enabled for testing.

The project may be submitted to HACS's default catalogue after it is stable,
branded, released, and passing HACS and Home Assistant validation. HACS indexes
the GitHub repository; it does not replace or host the source repository.

## Entities

The integration creates **Status**, **Operational phase**, **Rail data
freshness**, **Next departure**, **Prepare at**, **Leave home at**, **Station
arrival at**, **Decision path**, **Journey Guardian TransportAPI budget**,
**Data health**,
**Refresh calendar and timings**, and **Check live rail now** entities. Home Assistant generates
their entity IDs from the configured device name, so IDs can differ between
installations.

## Actions

`journey_guardian.review_now` immediately refreshes the configured calendar and
returns the normalized engine snapshot when a response is requested.

`journey_guardian.review_rail_now`—also available as **Check live rail now** on
the device—first refreshes the calendar and then explicitly checks TransportAPI.
The first unresolved origin and destination may use three routine calls: two
exact station lookups and one live departure-board request filtered to services
that call at the intended destination. Station resolutions are reused in memory,
and the broker can reuse a very recent board. This action never bypasses the
daily limit or consumes the urgent reserve. The next ordinary calendar refresh
can replace the manual rail observation.

**Automatic live rail checkpoints** are opt-in under the integration's
**Configure** menu. They run approximately 150, 90, 45, and 10 minutes before a
departure. The first three are routine; the final check may use the protected
urgent reserve. A restart-safe hashed ledger prevents duplicate checks, and a
12-minute catch-up window tolerates modest calendar synchronization or startup
latency. Enabling or reloading inside that window can therefore perform the one
recently due check.

The TransportAPI budget entity counts requests reserved by Journey Guardian. It
cannot observe requests made with the same provider account by legacy packages,
other integrations, scripts, or external applications. If TransportAPI reports
that the account allocation is exhausted, Journey Guardian immediately closes
its local budget for the rest of that provider day and records a stable error.

`journey_guardian.simulate_journey` activates a synthetic scenario using generic
locations and an offset from the current time. While it is active, reviews bypass
the configured calendar and no TransportAPI request or quota reservation can
occur. Supported scenarios are `on_time`, `delayed`, `cancelled`,
`split_on_time`, `stale_data`, and `provider_unavailable`. The stale-data case
keeps conservative timing available while making **Data health** off and **Rail
data freshness** explicitly stale.

`journey_guardian.clear_simulation` explicitly returns reviews to the configured
calendar. Simulations are held only in memory and also clear when Home Assistant
restarts or when the synthetic journey finishes.

For a rapid acceptance test, select the `on_time` scenario, set **Departure in
minutes** to `6`, and enable **Accelerated timeline**. The operational phase then
changes to preparation after one minute, leaving after three, station arrival
after five, and active travel after six. Preparation and leaving create local
Home Assistant persistent notifications once each, including across a restart.
This path does not call or reserve allowance from TransportAPI.

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

1. destination profiles and user-facing station resolution
2. validate automatic TransportAPI checkpoints against representative journeys
3. unified manual-review decision tree
4. richer station-wide disruption notifications
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
