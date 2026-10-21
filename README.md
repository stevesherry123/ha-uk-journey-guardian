# UK Journey Guardian

UK Journey Guardian is a Home Assistant commuting assistant for departure
timing, live UK rail checks, station access, and separate booked rail legs.

The current stable release targets Home Assistant 2026.8 or newer.

The stable maintenance line is **0.2.7**. The **0.3.0-beta.1** prerelease adds a
[read-only booking overview](docs/BOOKING_OVERVIEW.md), not completed automatic
interchange or disruption recovery. Choose prereleases deliberately.

Start with the [setup and first-journey guide](docs/GETTING_STARTED.md).
For missing journeys, alarms, or provider results, use
[troubleshooting](docs/TROUBLESHOOTING.md).

> [!WARNING]
> UK Journey Guardian is travel assistance, not a guaranteed transport service.
> Keep a fallback alarm while validating a new installation, and do not rely on
> any single provider or Home Assistant instance as the sole source of departure
> advice.

## Design principles

- no stations, cities, homes, workplaces, or notification targets are built in
- origins and destinations come from configuration and calendar events
- more than one regular destination can be configured
- preparation and station-arrival buffers are configurable per traveller
- the route to the station can be walking, driving, cycling, or automatically chosen
- split bookings use separate calendar events; automatic interchange recovery is planned
- departure location and time select the live service; destination confirms it
- credentials and journey details are redacted from diagnostics
- provider calls are bounded, cached and protected by failure fallbacks

## Current capabilities

- a [Travel review now briefing](docs/MANUAL_TRAVEL_REVIEW.md) for HA and watch
  shortcuts, using the shared calendar, station-access, and rail-provider engine
- optional [GPS station progress](docs/STATION_PROGRESS.md) from ordered station
  zones, with freshness checks and return-leg direction detection
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
- explicit station-code resolution and defensive rail-board normalization
- deterministic service matching with stable privacy-safe service identities
- manual and opt-in automatic live-rail checks via TransportAPI or Railinfo
- editable conservative station-access and early-warning timing
- a persistent shared TransportAPI budget with an urgent-call reserve
- status, next-departure, decision-path, API-budget, and data-health entities
- a **Refresh calendar and timings** button and
  `journey_guardian.review_now` action
- quota-free on-time, delayed, cancelled, split, and provider-outage simulations
- an explicit **Simulation active** diagnostic entity
- automated validation and unit tests

A live rail provider is selected in the integration options. TransportAPI uses
the configured daily credit budget; Railinfo uses its separate published
fair-use allowance. Automatic monitoring is off by default. When enabled in the
integration options, Journey Guardian makes bounded live checks 150, 120, 75,
45, 30, 15, 10, 7, 5, 3, and 1 minute before departure, plus one check 15
minutes afterwards. Each checkpoint is claimed in persistent private storage
before network access, and every request remains behind the durable budget. Rail
simulations remain provider-free.

The last successful rail observation remains visible between checkpoints. It is
labelled `retained` before departure and `historical` after departure; only a
genuinely new `current` observation can produce a new live-rail notification.
Recovery rejects rail observations older than six hours or with invalid time,
provider or schedule evidence. During a calendar outage, a minimal saved booking
can remain visible only while underway and before its original end; data health
stays off and automatic departure-board checks pause until the calendar returns.
See [restart recovery](docs/RESTART_RECOVERY.md).

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
EXC=driving
SMP=transit
NTH=walking
```

Valid modes are `driving`, `walking`, `bicycling`, and `transit`. If a calendar
station cannot be identified from its configured or explicit calendar CRS, the
profile is not guessed: Journey Guardian uses the default mode and its
conservative fallback if live routing is unavailable.

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

A recognized journey remains selected until the timed calendar event ends.
Selection is booked intent, not proof of boarding or arrival. GPS progress and
provider-based arrival collection have separate bounded monitoring rules.
Automatic interchange recovery and early-termination detection are not yet
implemented.

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
Automatic checkpoint scheduling is recorded in
[ADR 0008](docs/adr/0008-automatic-live-rail-checkpoints.md).

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

International air travel is recorded as a future optional module in the
[development backlog](BACKLOG.md). It will use provider-neutral flight legs and
airport profiles, and may consume a separately configured flight-tracking
integration, without changing the existing UK rail path.

The evidence-led post-journey review records confirmed destination delays and
flags possible Delay Repay claims without submitting anything. Any future claim
submission will require explicit per-claim user approval.
See [arrival evidence and the nightly safety net](docs/TRAVEL_DAY_REVIEW.md)
for supported providers, collection limits, and what a missing report means.

### Notification delivery roadmap

The current integration creates local persistent notifications and can hand live
messages to an existing Home Assistant announcement engine. Configure an
`input_text` helper and a script; Journey Guardian writes the rendered message
to the helper, then calls the script so household-specific delivery remains
outside the integration. Simulations remain local, and a failed announcement
falls back to a persistent notification.

The separately enabled home wake-up alarm turns the first preparation reminder
into a repeating announcement. While the configured person remains in the home
zone, Journey Guardian repeats it at the configured interval (six seconds by
default). An optional wake-up evidence entity stops the alarm as soon as it
reports that the traveller is awake. Without evidence, the alarm continues until
the traveller leaves home, the journey changes, the leave-home boundary arrives,
or the configurable 15-minute safety limit expires. Away from home, the existing
three-reminder pattern remains unchanged. Phone and watch haptics depend on the
selected Home Assistant announcement script delivering a mobile notification.

Live notifications require explicit opt-in. Current delivery covers preparation,
leave-now, and selected live-rail updates; it is not automatic connection-risk or
replacement-train advice. There is not yet a per-event preference screen or a
dedicated mobile adapter. Test the configured delivery script separately before
relying on phone or watch alerts.

## Departure calculation

Journey Guardian keeps the two safety margins independent:

```text
leave time = train departure - station buffer - route duration
start getting ready = leave time - preparation buffer - early-warning margin
```

The safety margins and conservative station-access duration are user choices.
When live routing is available, a separate minimum station-access allowance can
retain fixed overhead such as parking and walking into the station. Journey
Guardian uses the greater of the live route duration and that configured
minimum.
Provider results include `source: google_routes`, a `live_<mode>` or
`cached_<mode>` classification, the calculation time, selected mode and distance.
Fallback results remain
`source: configured_fallback` and `classification: inferred`. Automatic mode
uses driving at home and public transport away from home; walking, driving and
cycling can also be selected explicitly.

## Installation

Until the default-catalogue submission is accepted, add this repository to HACS
as a **custom repository** of type **Integration**. HACS then installs it under
`custom_components/` in the Home Assistant configuration directory.
Use this repository URL:

```text
https://github.com/stevesherry123/ha-uk-journey-guardian
```

After downloading it:

1. Restart Home Assistant.
2. Open **Settings → Devices & services → Add integration**.
3. Search for **UK Journey Guardian**.
4. Select the calendar, traveller, and zones. Provider credentials can be
   deferred until the manual live-rail check is needed. The calendar source is
   force-refreshed daily by default; this can be changed from 15 minutes to
   weekly, or disabled.
5. Keep existing travel alarms enabled while validating shadow-mode results.

After installation, open **Settings → Devices & services → UK Journey
Guardian → Configure** to tune the preparation, early-warning,
station-arrival, conservative station-access durations, and upstream calendar
refresh interval. Live-calendar notifications are deliberately disabled by
default. Validate local simulations and separately test the delivery script
before enabling them. The development notification-preview helper is not a
user-facing preview screen. Simulation notifications remain enabled for testing.

The [default-catalogue submission](https://github.com/hacs/default/pull/11772)
was opened on 10 October 2026. Consult that page for its current status. HACS
indexes the GitHub repository; it does not replace or host the source repository.

## Entities

The integration creates **Status**, **Operational phase**, **Rail data
freshness**, **Next departure**, **Prepare at**, **Leave home at**, **Station
arrival at**, **Decision path**, **Journey Guardian TransportAPI budget**,
**Data health**, **Simulation active**, **Station access routing**,
**Travel review now**, **Refresh calendar and timings**, **Check live rail now**,
and **Test station route now** entities. **Station progress** is added when
ordered station zones are configured. Home Assistant generates their entity IDs
from the configured device name, so IDs can differ between installations.

## Actions

`journey_guardian.travel_review_now` refreshes calendar, access timing, and
eligible live rail data, then delivers a briefing. Use `notify: false` for a
response without delivery. See [Travel review now](docs/MANUAL_TRAVEL_REVIEW.md).

`journey_guardian.review_now` immediately refreshes the configured calendar and
returns the normalized engine snapshot when a response is requested.

Journey Guardian otherwise forces Home Assistant to update the selected source
calendar once per configured interval. The default is daily. This is separate
from Journey Guardian's ten-minute local review cadence and prevents integrations
with slow default polling, such as Remote Calendar, from silently serving stale
events. Selecting **Disabled** leaves all source refresh timing to the calendar
integration. The **Refresh calendar and timings** button always forces a source
update regardless of the configured interval.

`journey_guardian.review_rail_now`—also available as **Check live rail now** on
the device—first refreshes the calendar and then explicitly checks the selected
live rail provider.
The first unresolved origin and destination may use three routine calls: two
exact station lookups and one live departure-board request filtered to services
that call at the intended destination. Station resolutions are reused in memory,
and the broker can reuse a very recent board. This action never bypasses the
daily limit or consumes the urgent reserve. Ordinary calendar refreshes retain
the latest matched rail observation for the same journey.

**Automatic live rail checkpoints** are opt-in under the integration's
**Configure** menu. They run 150, 120, 75, 45, 30, 15, 10, 7, 5, 3, and 1 minute
before departure, plus 15 minutes afterwards while the journey remains current.
Checks through 15 minutes before departure are routine; the final ten minutes and
post-departure check may use the protected urgent reserve. A restart-safe hashed
ledger prevents duplicate checks, and a 12-minute catch-up window tolerates
modest calendar synchronization or startup latency. Enabling or reloading inside
that window can therefore perform the one recently due check.
When the latest available rail observation reports a delay, three additional
bounded checks at +30, +45 and +60 minutes can run while that booking remains
current. They stop when delay evidence is absent/unavailable, the service is
cancelled, the calendar is unavailable, or the booking changes/ends. A service
missing from a board is not proof that it departed.

The TransportAPI budget entity counts requests reserved by Journey Guardian. It
cannot observe requests made with the same provider account by legacy packages,
other integrations, scripts, or external applications. If TransportAPI reports
that the account allocation is exhausted, Journey Guardian immediately closes
its local budget for the rest of that provider day and records a stable error.
Railinfo calls are deliberately excluded from this entity: they remain bounded
by the same checkpoint schedule, 30-second cache, de-duplication and HTTP 429
back-off, but do not consume TransportAPI credits.

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
Home Assistant persistent notifications. Simulations clear on restart, so this
is not a restart-recovery test. They do not contact live rail or routing providers
and do not test physical phone/watch delivery.

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

1. reliable early-termination evidence and bounded recovery advice
2. retained actionable rail status across restart and delayed-service follow-up
3. real-travel acceptance of direct and split commuting bookings
4. richer station-wide disruption and interchange monitoring
5. destination profiles and optional local-transit comparison
6. dedicated notification adapters and per-event preferences
7. HACS catalogue review and public-user feedback

The maintained development list is in [BACKLOG.md](BACKLOG.md).
The [public-readiness review](docs/PUBLIC_READINESS.md) records remaining
acceptance work and the latest documentation audit.

## Release strategy and path to v1.0

Journey Guardian uses semantic releases. Every accepted change is versioned and
published so HACS can expose the update; therefore patch numbers include safe
documentation, test, and inactive-scaffold changes as well as runtime fixes.

The intended progression is:

| Version | Purpose |
| --- | --- |
| `0.1.x` | Alpha hardening, shadow-test tools, documentation, and safe scaffolds. |
| `0.2.0` | Initial stable rail core with direct journeys, restart recovery, routing profiles, diagnostics, and conservative notification defaults. |
| `0.3.0` | Split-journey expansion after interchange and waypoint matching pass representative real tests. |
| `0.4.0` | Notification-adapter expansion with explicit mobile target selection, test-send, preferences, deduplication, and end-to-end acceptance. |
| `0.5.x+` | Optional expansion modules, including international air travel. These do not block a stable UK rail core. |
| `0.9.0` | Release candidate: feature freeze except for acceptance fixes. |
| `1.0.0` | Stable UK rail Journey Guardian. |

### v1.0 acceptance gate

Version 1.0 is a reliability milestone, not a promise that every future travel
module exists. It requires all of the following:

- repeated real-world acceptance of direct and split rail journeys
- robust provider matching for ordinary services and waypoint/calling-point
  services
- proven restart/reload recovery, provider quotas, and bounded failure fallbacks
- validated station-access profiles and conservative fallback timing
- at least one user-selected mobile notification path accepted end-to-end
- no duplicate or missed critical alerts across restarts or timetable updates
- complete privacy, diagnostics, configuration-migration, and HACS validation
- a defined observation period with legacy automations retained, followed by a
  safe, evidence-led retirement decision

International flight support and automated Delay Repay claim submission remain
post-1.0 modules. They will be developed behind separate opt-in and acceptance
gates; they must not delay or weaken the stable rail core.

## Development

The [isolated HA commute rehearsal](docs/COMMUTE_REHEARSAL.md) exercises runtime
wiring with fictional external inputs and captured announcements. It includes
an explicit open acceptance case for early termination, not a passing claim of
recovery support.

```bash
python -m pip install -e '.[test]'
ruff check .
pytest
python -m compileall custom_components/journey_guardian
```

Use Python 3.14.2 or newer, matching the test environment. See the rehearsal
guide for the network-disabled test command and the known acceptance gap.

## Licence

UK Journey Guardian is released under the MIT Licence.
