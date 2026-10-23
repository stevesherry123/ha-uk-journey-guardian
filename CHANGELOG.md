# Changelog

## 0.3.0-beta.8 (Dashboard Review Branch)

- Development-branch prerelease only; not merged to main or the stable line.
- Add a read-only dashboard projection, conditional notification timeline and
  actual upcoming data checks, without scheduling or sending extra alerts.
- Package the beta Lovelace card and serve only that static JavaScript file.
  Journey data continues to use authenticated HA entity states.
- Include overnight, clock-change, cancellation, stale and missing-data states.
- Keep existing dashboards unchanged; add the review dashboard explicitly.

## 0.3.0-beta.7

- Include stable v0.2.13 ordered routing failover alongside the retained-booking
  preview. Stable remains the recommended installation for normal journeys.

## 0.2.13 (Stable Line)

- Try the preferred Waze sensor, then configured Google driving for the same
  leg, then the configured constant if no usable estimate is available.
- Expose fallback reasons separately from terminal routing errors; successful
  Google recovery remains working or cached and clears routing Repairs.
- Explain Google recovery and worst-case constant allowances in operational
  notifications. The selected allowance drives wake-up and all other timings.
- Reject unusable Google origin coordinates before requesting a route; preserve
  existing minimum allowances, provider limits and notification deduplication.

## 0.3.0-beta.6

- Include stable v0.2.12 explicit Waze sensor profiles and deterministic station
  alias matching alongside the existing retained-booking preview.

## 0.2.12 (Stable Line)

- Connect explicitly selected existing Waze duration sensors through the existing
  station-access profiles field; preserve legacy mode-only entries.
- Add exact calendar-name aliases and reuse resolved CRS identities so named
  calendar origins do not silently miss configured per-station choices.
- Keep provider choice per origin: Waze errors use a labelled fallback, never a
  silent Google switch. Validate minutes, freshness and restored/unavailable
  states; keep sensor IDs and private route attributes out of diagnostics.
- Apply existing minimum door-to-station allowance and all preparation/station
  buffers unchanged. Native sensor refreshes use HA, not a new Waze API client.
- Show Waze success as working and clear sustained routing Repairs on success.
- Add isolated HA profile/reload, source-selection and sensor-validation tests.

## 0.3.0-beta.5

- Include stable v0.2.11 calendar availability, response validation and bounded
  source-refresh recovery fixes alongside the retained-booking preview.

## 0.2.11 (Stable Line)

- Do not treat absent/unavailable/unknown calendars, missing response entries or
  malformed event lists as a healthy empty travel day. Detect a calendar that
  becomes unavailable during its service response as well.
- Verify calendar availability after a forced source update before recording a
  successful refresh. Retry failed configured refreshes after a bounded
  15-minute interval, even when a prior successful daily refresh is recent.
- Rehearse unavailable-source startup, reload and recovery without provider
  requests; add regression tests for silent update failures and malformed data.
- No calendar/feed credentials, alarm settings, provider quota or TLS settings
  change. External feed/network outages still require source recovery; this
  release does not claim to prevent upstream failures or revive future alarms
  from stale bookings.

## 0.3.0-beta.4

- Retain up to 64 independent booked legs across calendar refreshes and HA
  reload/restart in a separate, read-only local travel plan. Completed booking
  windows no longer disappear from this view as the next train advances.
- Keep a 48-hour window after each booked arrival (departure if unknown), with
  expiry pruning, scoped storage, corruption validation and bounded checkpoints.
- Label calendar absence, restart retention, truncation, persistence failures
  and unconfirmed outcomes explicitly. Edited bookings remain separate rather
  than guessing that one service replaced another.
- Preserve current alarm, next-train, routing, quota and provider scheduling.
  Simulations neither mutate nor display the real retained plan. No live
  multi-leg monitoring, cancellation detection or recovery search is added yet.
- Extend the network-disabled four-booking HA rehearsal across the complete day
  and successive runtime reloads. Raw titles/locations and retained plan details
  remain excluded from downloadable diagnostics.

## 0.3.0-beta.3

- Include the stable v0.2.10 packaging, safe route-error categories and sustained
  failure Repairs notices alongside the existing read-only booking overview.

## 0.2.10 (Stable Line)

The v0.2.9 tag was blocked before publication by a packaging-test import issue;
the test now works without a custom Python path.

- Publish reproducible runtime-only HACS ZIP assets with no install telemetry.
- Surface repeated sustained calendar/source, routing and live-rail failures
  through explanatory Repairs notices without extra provider requests.
- Distinguish Google Routes request/access/quota/timeout failures safely and
  reject malformed payloads, invalid coordinates and non-finite durations.
- Alarm settings, configured fallback durations and rail checkpoint timing are
  unchanged. Google account access or billing settings are not modified.

## 0.3.0-beta.2

- Apply the HACS review's catalogue-first installation guidance to the preview
  line and link stable v0.2.8. No runtime changes from 0.3.0-beta.1.

## 0.2.8 (Stable Line)

- Record HACS approval on 21 October 2026 and lead installation with HACS search;
  custom repositories remain a fallback. Includes a wording regression check.
- Runtime unchanged from v0.2.7; no 0.3 booking-overview preview in this stable tag.

## 0.3.0-beta.1

### Added

- Read-only upcoming-booking overview on Status, using the existing calendar
  response. Includes independent endpoints/times and schedule-only continuity
  hints, with exact-duplicate removal and explicit truncation above 16 legs.
- Four-booking integration rehearsal proving the overview survives reload without
  new provider work or changes to the current departure/leave plan.

### Scope

- Includes v0.2.7 reliability fixes. This is a prerelease, not the stable 0.3
  multi-leg/disruption milestone. Stable users can remain on v0.2.7.
- Connection hints do not assert a shared ticket, feasible transfer, train
  arrival, missed connection or early termination. No new alerts or searches.
- The window is the existing 30-hour calendar lookahead, not a complete travel-day
  ledger. Completed legs disappear; calendar outage is explicitly unavailable.
- Overview details are local private HA state, omitted from diagnostics, but may
  be retained by Recorder, service consumers, exports or backups.

## 0.2.7

### Added

- Versioned, minimal booked-intent recovery during calendar outages after
  restart, bounded to an underway booking's original end and a 24-hour duration.
- At most three extra automatic rail checkpoints (+30, +45 and +60 minutes)
  while the latest available observation reports a delay and the booking remains
  current. Existing provider budgets, back-off and durable claims still apply.
- Full-runtime rehearsal of calendar outage, integration reload, recovery and
  confirmed booking removal, without duplicate alerts or outage rail requests.

### Fixed

- Validate restored observation types, timezone-aware timestamps, provider,
  schedule match and a six-hour maximum evidence age. Simulation, corrupt,
  future-dated and incompatible records fail closed.
- Retain explicit historical/retained labels after restart; a restored booking
  never turns a failed calendar into healthy data or starts pre-departure alarms.

### Privacy and Scope

- Local recovery now stores minimal endpoint names/codes and booked times, but
  not raw calendar titles, descriptions, locations or credentials. Protect HA
  storage and backups. Diagnostics continue to exclude these journey details.
- Legacy observation-only records remain readable for the same matching booking;
  outage intent recovery begins after a successful review writes the new schema.
- This does not implement early-termination recognition, replacement-train advice,
  continuous delayed-service tracking, or HA Repairs.

## 0.2.6

### Documentation

- Add a first-install, calendar, notification-script, wake-alarm and upgrade guide.
- Add troubleshooting and an honest arrival/nightly-review guide, including
  Railinfo-only collection, bounded attempts, quiet-report semantics and gaps.
- Correct stale feature comparisons, simulation/restart claims, provider action
  descriptions, checkpoint request counts, and development setup instructions.
- Link the existing HACS submission and distinguish current features from plans.
- Add documentation-link and delivery-example regression checks.

No journey timing, provider acquisition or notification behaviour changes.

## 0.2.5

### Added

- Full-runtime Home Assistant commute rehearsals with real entities, services,
  timers, provider parsing, storage reloads, GPS tracking and nightly review.
  Only calendar/provider I/O and announcement delivery are fictional.
- A network-disabled rehearsal gate in validation and release workflows.
- An explicit expected-failure acceptance case for shortened services, separate
  from passing coverage. Unexpected errors in that case are not suppressed.

### Fixed

- Suppress bounded home wake reminders after awake evidence or the repeating
  alarm's safety limit has finished the wake-up phase. Away reminders remain.
- Recover a due preparation reminder if a simultaneous coordinator refresh
  cancels its timer, using the durable ledger to avoid duplicate delivery.
- Distinguish destination-arrival delay from saved departure-delay observations
  in the nightly report, preserving genuine earlier departure-delay evidence.

### Known Gap

- A shortened-service response can remain unmatched rather than produce an
  early-termination cancellation/recovery workflow. The rehearsal leaves that
  journey unresolved, never fabricating a destination arrival. Recovery search
  and reliable early-termination evidence remain separate work.

## 0.2.4

### Added

- Keep positively observed GPS journeys under monitoring for up to three hours
  beyond booked arrival, including during temporary calendar unavailability.
- End the extension at destination proximity, the next booked departure, expiry,
  simulation, or invalid route configuration without changing next-train alerts.
- Restore eligible monitoring and selected diversions after restart using only
  endpoint fingerprints and booked times, not calendar titles or station names.
- Expose extended-monitoring state and its booked-arrival and expiry boundaries.

### Fixed

- Use stable timestamp serialization for route fingerprints across restoration.
  Upgrading can reset an older saved observation once.

### Scope

- This is GPS-only monitoring, not boarding, railway arrival or compensation
  evidence. Provider-based arrival collection remains separate. Intentional
  touring breaks are outside the commuting-assistant scope.

## 0.2.3

### Added

- Optional alternative GPS station paths, including automatic reversal for return
  journeys and calendar endpoints on a diversion.
- Evidence-led route selection: retain multiple possible paths until fresh GPS
  identifies one. Missed branch observations remain uncertain after rejoining.
- Expose possible next waypoints and the selected station path; preserve route
  selection across restarts without storing station names or coordinates.
- Validate bounded, acyclic route configuration and redact alternative paths
  from diagnostics. Existing single-route installations remain compatible.

### Limitations

- Configured GPS diversions do not prove boarding, railway arrival, cancellation
  or compensation entitlement. Tracking still follows the selected calendar leg,
  which currently ends at its booked end time.

## 0.2.2

### Added

- Add a Travel review now button and `journey_guardian.travel_review_now` action
  that force-refresh the calendar and station-access route, check eligible live
  rail data through the shared provider broker, and return a readable briefing.
- Explain missing journeys, calendar problems, unresolved stations, ambiguous
  services, timetable mismatch, provider failures, cancellations, route fallbacks,
  and calendar journeys already underway without asserting boarding/departure.
- Keep the full report in a local HA notification and deliver a summary through
  the configured announcement script, even when automatic notifications are off.
  Simulation reviews stay local. `notify: false` returns the report silently.
- Reuse completed reviews for 30 seconds and serialize simultaneous requests so
  repeated watch taps do not multiply provider calls or notifications.

### Fixed

- Avoid rereading the calendar and recalculating access while checking rail for
  the same explicit travel review. Pass the watch summary directly to compatible
  announcement scripts as well as updating the legacy text helper.
- Declare config-entry-only setup for Home Assistant metadata validation.

## 0.2.1

### Added

- Opt-in station progress using an ordered list of Home Assistant station zones
  and the configured traveller's GPS source. Calendar endpoints select the route
  segment and direction, including return legs.
- Expose the latest observed station, current station proximity, next configured
  waypoint, and GPS freshness without making additional rail-provider requests.
- Reject stale, inaccurate, ambiguous, backwards, and out-of-order observations;
  restore the latest waypoint after restart for the same calendar leg.
- Strip the leading `zzz ` map-sort prefix from progress labels. Keep private
  route configuration out of downloadable diagnostics.

### Limitations

- GPS proximity is not proof of boarding, a station call, or railway arrival,
  and does not change Delay Repay evidence or trigger announcements.
- Progress follows the coordinator's selected calendar leg. Missed stations are
  not inferred, and delayed journeys beyond the booked end time or diversions
  need a future retained-journey/disruption implementation.

## 0.2.0

### Fixed

- Treat a selected calendar that has not finished loading as expected startup
  state instead of calling unavailable Home Assistant calendar services and
  emitting warnings.
- Make the bounded startup recovery refresh the upstream calendar before
  reviewing it, so a late calendar load does not leave stale source data.

### Changed

- Declare the Home Assistant calendar integration as an ordered startup
  dependency and promote the tested rail core to the first stable HACS release.

## 0.2.0-beta.17

### Fixed

- Do not silently disable the repeating home wake-up alarm when no optional
  awake-evidence entity is configured. Without evidence, the alarm now repeats
  until a home, journey, leave-time, or safety-limit stop is reached.
- Preserve the wake-up alarm for upgraded installations that already have a
  delivery script, while giving new installations a separate explicit enable
  switch.

### Added

- Expose privacy-safe wake-up eligibility, delivery channel, repeat count, and
  stop reason in the status entity and downloadable diagnostics.

## 0.2.0-beta.16

### Added

- Add an opt-in home-only repeating wake-up alarm driven by a user-selected
  binary sensor or input boolean, with configurable awake polarity, repeat
  interval, and maximum duration.
- Stop the alarm when awake evidence appears, the traveller leaves home, the
  journey changes, the leave-home boundary is reached, or the safety limit
  expires.

### Changed

- Preserve the existing three-reminder preparation pattern away from home and
  whenever no wake-up evidence entity is configured.

## 0.2.0-beta.14

### Added

- Add a configurable forced source-calendar refresh interval, with a daily
  default and choices from 15 minutes to weekly or disabled.
- Record the last successful source refresh and any privacy-safe refresh error
  on the status sensor.

### Changed

- Make manual calendar and live-rail reviews refresh the selected Home Assistant
  calendar entity before Journey Guardian reads its events.

## 0.2.0-beta.13

### Changed

- Require the HACS repository description and topic checks to pass without
  validation exceptions, readying the repository for a future default-catalogue
  submission.

## 0.2.0-beta.12

### Fixed

- Publish version tags containing a prerelease suffix as GitHub prereleases so
  beta builds are not presented as stable releases.

## 0.2.0-beta.11

### Security

- Remove credentials from options-form defaults so saved provider secrets are
  not returned to the browser; blank submissions preserve the existing value.
- Minimise downloaded diagnostics by removing entity identifiers, route and
  service details, exact evidence timestamps, and request fingerprints.
- Remove installation-specific route examples and coordinates from the current
  public tree, and expand the repository privacy scanner to catch common secret
  formats and private route data.

### Fixed

- Require explicit calendar CRS codes or provider resolution instead of a
  route-specific built-in station map.
- Gate tagged GitHub releases on tests, lint, privacy scanning, Hassfest, HACS
  validation, and an exact tag-to-manifest version match.
- Bring the public documentation in line with the current beta capabilities and
  automatic checkpoint schedule.

## 0.2.0-beta.10

- Removed literal entity-shaped placeholders from tests so the repository privacy gate passes.

## 0.2.0-beta.9

- Corrected setup-test lifecycle coverage for the nightly review scheduler.

## 0.2.0-beta.8

- Corrected automatic rail checkpoints to use the intended 150-minute early check and 15-minute post-departure retry.
- Added config-flow coverage for the selected live rail provider.

## 0.2.0-beta.7

### Added

- Add a restart-safe Railinfo arrival collector which checks the destination
  movement board after each observed journey, matches the original service,
  and stores scheduled arrival, actual arrival and destination delay evidence.
- Add a configurable Delay Repay alert threshold with a conservative
  15-minute default.

### Changed

- Make the nightly travel-day review evidence-led: a successful departure
  lookup no longer proves an on-time arrival, missing arrival evidence is
  reported as unresolved, normal evidenced journeys stay silent, and the last
  privacy-safe per-leg review is included in integration diagnostics.
- Retain up to 250 sanitized live checks so dense morning and evening travel
  remains available when the nightly review runs.
- Run the travel-day review at 04:00 for the previous date so late services can
  complete before possible compensation is assessed.

## 0.2.0-beta.6

### Added

- Add a configurable minimum station-access allowance so short live-routing
  estimates cannot remove fixed overhead such as parking and walking into the
  station. Routing diagnostics expose both provider and applied durations.

## 0.2.0-beta.5

### Fixed

- Match Railinfo journey legs by their requested origin and intermediate
  destination, so a through train is correctly identified even when it
  terminates beyond the traveller's alighting station.

## 0.2.0-beta.4

### Added

- Optional Railinfo live-rail provider. It requires no credentials and uses its
  separate fair-use allowance rather than consuming TransportAPI credits.
- A provider selector in the integration options, with Railinfo station search,
  live-board normalization, response caching, request de-duplication and
  rate-limit handling.

## 0.2.0-beta.3

### Added

- A provider-free nightly Journey Guardian review at 23:30 local time. It
  summarises the day's saved live-rail evidence, highlights delayed or
  unresolved journeys, and never makes an additional TransportAPI request.

### Changed

- Use a dense final-minute checkpoint cadence and one post-departure
  confirmation instead of routine 5-, 15-, and 30-minute post-departure polls.

## 0.2.0-beta.2

- Prevent overlapping pre- and post-departure catch-up windows from making
  duplicate live-rail requests.

All notable changes to Journey Guardian will be documented in this file.

## [0.2.0-beta.1] - 2026-09-10

### Added

- Add a configurable announcement-engine adapter which writes each live journey
  message to a selected `input_text` helper and then calls a selected script.
  Simulation messages remain local, and failed announcement delivery falls back
  to a Home Assistant persistent notification.

## [0.1.35] - 2026-09-10

### Fixed

- Close the live-rail monitoring blind spot around departure by checking again
  two minutes before departure and at bounded post-departure checkpoints even
  when the last provider response still described the service as on time.

## [0.1.34] - 2026-09-09

### Added

- A public release strategy and evidence-based v1.0 acceptance gate in the main
  README, including the boundaries for post-v1 international and Delay Repay
  modules.

## [0.1.33] - 2026-09-09

### Added

- A future evidence-led Delay Repay assistance workstream, including policy
  verification, post-journey outcome evidence, eligibility advice, deadline
  reminders, and explicit approval requirements for any claim submission.

## [0.1.32] - 2026-09-09

### Added

- A future international air-travel workstream, covering flight itineraries,
  timezone safety, airport profiles, provider and FlightRadar24 adapters,
  passenger notifications, and shadow-mode acceptance gates. This is planning
  documentation only and has no Home Assistant runtime effect.

## [0.1.31] - 2026-09-09

### Added

- An inactive, read-only notification timeline preview and a documented feature
  comparison against the legacy acceptance inventory. Neither is registered in
  Home Assistant or able to deliver a notification.

## [0.1.30] - 2026-09-09

### Added

- An inactive notification-event catalogue for future mobile delivery, test
  notifications, per-event preferences, and connection-risk alerts. It has no
  Home Assistant runtime wiring and does not alter current notification output.

## [0.1.29] - 2026-09-09

### Added

- Development-only rail replay, connection-risk, and diagnostics explanation
  tools for reviewing shadow-test evidence without altering live decisions.

## [0.1.28] - 2026-09-09

### Added

- Station access profiles now allow a specific travel mode per CRS station,
  such as `EXC=driving`, `SMP=transit`, and `NTH=walking`.
- Stations without a profile retain the configured default mode and conservative
  fallback; unknown stations are never guessed as driving.

## [0.1.27] - 2026-09-09

### Added

- Live-rail diagnostics now retain the privacy-safe minute offset when a
  provider timetable does not match the calendar departure. This makes future
  matching failures actionable without retaining calendar text or raw API data.

## [0.1.26] - 2026-09-09

### Fixed

- When a live rail check cannot match a scheduled service, Journey Guardian now
  makes bounded post-departure retries. This gives providers time to publish
  the service's real-time record instead of stopping checks at departure.

## [0.1.25] - 2026-09-09

### Added

- The latest verified rail observation is retained across a Home Assistant restart when it matches the same calendar journey.
- Delayed services receive automatic follow-up checks after scheduled departure.

## [0.1.24] - 2026-09-09

### Fixed

- If the initial review races Home Assistant's calendar startup, Journey
  Guardian now automatically retries after two minutes. No manual refresh or
  separate Home Assistant automation is required.

## [0.1.23] - 2026-09-09

### Changed

- Live timetable changes now remain notification and diagnostic information.
  They no longer move preparation, leave-home, or station-arrival timing away
  from the calendar plan.

## [0.1.22] - 2026-09-09

### Fixed

- Successful live-rail observations now remain visible between automatic
  checkpoints instead of being cleared by the next calendar poll or forced
  station-route check.
- Retained delayed and cancelled observations continue to control status,
  actionable departure timing, and operational phase until fresh provider
  evidence replaces them or the selected journey changes.
- Retained evidence is labelled `retained` before departure and `historical`
  after departure, preventing it from being mistaken for a fresh provider call
  or generating duplicate rail notifications.

## [0.1.21] - 2026-09-08

### Added

- A **Test station route now** button bypasses the route cache to verify the
  configured Google Routes key and current journey immediately.
- A diagnostic routing-health sensor exposes working, cached, fallback, and
  error states with duration, distance, mode, timestamps, and sanitized errors.
- Planned journeys force fresh station-access calculations about 6 hours,
  2 hours, 45 minutes, and 15 minutes before departure.

### Fixed

- The station-access mode now has its missing options-flow translation.

## [0.1.20] - 2026-09-08

### Fixed

- Test fixtures no longer resemble an installation-specific Home Assistant
  person entity, allowing the repository privacy validation to complete.

## [0.1.19] - 2026-09-08

### Added

- Google Routes can now provide live station-access durations and distances for
  driving, walking, cycling, and public transport.
- Automatic access mode selects traffic-aware driving while the traveller is
  home and public transport while away, avoiding a driving assumption on return
  legs.
- Equivalent route requests use a bounded adaptive cache to prevent calendar
  polling from multiplying provider calls while refreshing more frequently near
  departure.

### Changed

- Station-access notifications name the effective live mode selected by the
  timing engine.
- Missing credentials, coordinates, routes, or provider availability preserve
  the configured conservative duration and its `inferred` provenance.
- Routing failures expose a sanitized timing attribute and log only once per
  journey and failure category.

## [0.1.18] - 2026-09-08

### Added

- Status diagnostics now expose the last live-rail check, the next scheduled
  automatic checkpoint, and the last notification type and time.
- Rail observations expose whether they have been retained from the final live
  check rather than acquired by the current calendar refresh.

### Changed

- The manual calendar button is now labelled **Refresh calendar and timings** so
  it cannot be confused with the quota-consuming live-rail button.
- The final successful rail observation remains visible after departure with
  `historical` freshness, preserving the matched service, platform and calling
  point evidence throughout the active journey.

## [0.1.17] - 2026-09-08

### Added

- Automatic live-rail checkpoints now create passenger-facing on-time or delayed
  notifications with the current platform and confirmed calling point.
- Preparation now produces a bounded three-message wake-up sequence, followed by
  a station-access notification that names driving when it is the configured mode.
- Live status notifications are emitted once per checkpoint and again only when
  the predicted time, delay, platform, service, or leg count materially changes.

### Changed

- Operational notification fingerprints now remain stable when live rail data
  adjusts the actionable departure, preventing duplicate leave-now alerts.
- Existing installations can edit the station-access mode through the options
  flow as well as the fallback duration.

### Fixed

- Future automatic rail timers now run as native asynchronous Home Assistant jobs,
  preventing the intermittent unawaited-checkpoint coroutine seen in live logs.

## [0.1.16] - 2026-09-07

### Fixed

- Explicit calendar CRS codes now use deterministic station identities instead
  of consuming Places quota and depending on provider naming.
- Persistent live-check records now identify the exact failing stage: origin
  resolution, destination resolution, timetable acquisition or matching.

## [0.1.15] - 2026-09-07

### Fixed

- Provider names ending in `Rail Station` or `Railway Station` now match the
  corresponding calendar station name without weakening ambiguity safeguards.
- Future automatic-checkpoint callbacks now schedule their coroutine through
  Home Assistant instead of creating an unawaited coroutine.

## [0.1.14] - 2026-09-07

### Added

- A bounded, privacy-safe history of the latest 20 live-rail checks is persisted
  across Home Assistant restarts and included in downloaded diagnostics.
- Audit records include the trigger, journey fingerprint, resolved CRS codes,
  provider operation, sanitized outcome, match quality, budget and journey state.

### Changed

- A failed live-rail lookup no longer replaces a valid calendar journey with a
  generic error state. Calendar timing and operational phase remain actionable,
  while `last_live_rail_error` records that live data is degraded.

### Fixed

- Failed automatic checkpoints now retain enough evidence to distinguish station
  resolution, timetable, matching and quota failures after a restart.

## [0.1.12] - 2026-09-04

### Added

- Opt-in automatic live-rail checks approximately 150, 90, 45, and 10 minutes
  before the selected calendar departure.
- A restart-safe privacy-preserving checkpoint ledger prevents the same journey
  checkpoint from reserving provider allowance twice.
- A bounded catch-up window allows a recently due checkpoint to run when calendar
  synchronization or Home Assistant startup is slightly late.

### Changed

- The final ten-minute automatic checkpoint may use the configured urgent reserve;
  earlier checkpoints remain routine and stop before consuming it.
- The legacy capability audit now records every behaviour that must be replaced or
  deliberately retired before the old packages are removed.

## [0.1.11] - 2026-09-04

### Fixed

- Failed live checks now publish the latest durable budget snapshot immediately,
  rather than temporarily displaying the count from before the attempt.
- TransportAPI allocation responses are classified as quota exhaustion and close
  the local budget for the rest of the provider day. This prevents repeated
  attempts when legacy or external consumers have used the same account quota.
- The last privacy-safe live-rail error remains visible after routine calendar
  refreshes restore healthy calendar planning.

### Changed

- The budget entity is labelled **Journey Guardian TransportAPI budget** and
  explicitly identifies its scope. Its normal count covers this integration's
  reservations, not unseen requests made by other consumers of the provider
  account.

## [0.1.10] - 2026-09-03

### Fixed

- Live timetable requests now resolve the intended destination to a CRS code and
  ask TransportAPI only for services that call there. This supports journeys
  whose train continues beyond the calendar destination.
- Destination evidence now uses whole-name boundaries, so a short place name
  cannot incorrectly match inside a longer unrelated place name.
- A provider service more than five minutes from the calendar departure is
  rejected instead of silently changing the user's travel advice. The safe
  calendar timing remains available with a stable mismatch error.

### Added

- Live observations expose `exact_schedule` or `near_schedule` match quality and
  a signed schedule-offset attribute for privacy-safe diagnosis.
- Regression coverage for a train terminating beyond the intended calling point,
  a later train to a different destination, and unsafe schedule displacement.

### Changed

- The first live check with uncached origin and destination names can use three
  routine calls: two Places resolutions and one live timetable request.

## [0.1.9] - 2026-09-03

### Added

- A dedicated **Check live rail now** button and
  `journey_guardian.review_rail_now` action for explicitly controlled first live
  TransportAPI checks.
- A TransportAPI client using header credentials, the current Places endpoint,
  and a bounded live `station_timetables` request around the calendar departure.
- In-memory, bounded station-resolution reuse keyed by a privacy-safe hash.
- End-to-end contract tests for live client parameters, credential isolation,
  station resolution, delayed observations, timing updates, and quota-free polling.
- An architecture decision record defining the manual-only live gateway.

### Changed

- TransportAPI may now be contacted only through the dedicated manual control.
  Setup, reload, scheduled calendar polling, ordinary review, and simulation do
  not invoke the provider.
- TransportAPI's documented `crs:`-prefixed response codes normalize to the same
  canonical CRS identity used by calendar and Places data.
- A first unresolved station can consume two routine calls (Places plus timetable);
  repeated checks can reuse station and short-lived board caches.

## [0.1.8] - 2026-09-03

### Added

- Offline CRS station resolution from configured codes, explicit calendar codes,
  and exact unique saved Places results.
- Defensive station-board normalization with separate scheduled and predicted
  departures, cancellation, platform, and privacy-safe stable service identity.
- Deterministic calendar-to-service matching using bounded time, destination, and
  operator evidence, with explicit rejection of ambiguous results.
- Coverage for direct, delayed, cancelled, duplicate, corrected, malformed,
  conflicting, ambiguous, split, and overnight provider records.
- Architecture decision record for rail normalization and matching boundaries.

### Changed

- On-time, delayed, cancelled, stale-data, and split simulations now traverse the
  production rail normalizer and matcher using in-memory provider-shaped fixtures.
- Status and diagnostic attributes expose only derived match evidence; raw
  provider payloads and raw train identifiers are not retained or exposed.
- This release remains fully offline and cannot consume TransportAPI allowance.

## [0.1.7] - 2026-09-03

### Added

- A shared provider request broker with short-lived caching, concurrent request
  deduplication, hard quota enforcement, and protected urgent retries.
- Explicit current and stale provider-result contracts with privacy-safe
  acquisition metadata and bounded stale fallback.
- Strict JSON provider-payload validation and detached cached responses.
- A **Rail data freshness** diagnostic entity and quota-free `stale_data`
  simulation scenario.
- Regression tests for concurrent consumers, quota denial, urgent reserve races,
  malformed responses, provider outages, stale expiry, unload cancellation, and
  budget restoration after restart.

### Changed

- Malformed persisted quota usage now fails closed at the daily limit instead of
  risking additional provider allowance.
- The provider broker is created during config-entry setup but remains dormant;
  this release does not enable or call TransportAPI.

## [0.1.6] - 2026-09-03

### Added

- An operational-phase entity covering waiting, preparation, leaving, station
  arrival, active travel, cancellation, and provider-unavailable states.
- Exact, cancellable Home Assistant timers for each operational boundary.
- Restart-safe notification deduplication using privacy-safe hashed fingerprints.
- Local persistent notifications for preparation, leaving, cancellation, and
  provider-unavailable phases.
- An accelerated simulation timeline for observing the complete phase sequence
  in minutes without contacting TransportAPI.

### Changed

- Live-calendar notifications remain off by default during shadow testing and
  can be enabled explicitly from the integration options; simulation alerts are
  always available.
- The normal simulated departure default is now 180 minutes, keeping the default
  preparation time in the future with the conservative timing settings.

## [0.1.5] - 2026-09-03

### Added

- Quota-free journey simulation actions for on-time, delayed, cancelled,
  split-journey, and provider-unavailable scenarios.
- A diagnostic simulation-active entity and explicit simulated rail-observation
  provenance.
- Separate scheduled and predicted departure values for simulated delays.
- Deterministic tests proving simulations bypass calendar calls and cannot
  reserve TransportAPI allowance.

### Changed

- The actionable next-departure entity uses a simulated predicted departure
  while preserving the scheduled value in diagnostic attributes.
- Simulations are deliberately held only in memory and clear automatically when
  their synthetic journey finishes or Home Assistant restarts.

## [0.1.4] - 2026-08-29

### Added

- Preparation, leave-home, and station-arrival timestamp entities calculated
  from the recognized journey and conservative safety margins.
- An editable timing options flow for existing installations.
- Explicit `configured_fallback` and `inferred` provenance on every calculated
  timing entity and in privacy-safe diagnostics.
- A release packaging regression test for the Journey Guardian logo.

### Changed

- Added configurable early-warning and station-access fallback durations while
  preserving safe defaults for existing config entries.

## [0.1.3] - 2026-08-29

### Fixed

- Excluded disposable development environments and build outputs from the
  repository privacy scan.
- Sanitized calendar/provider failures before exposing error state, diagnostics,
  or action responses.
- Registered integration actions independently from the config-entry lifecycle.
- Simplified setup-form selectors for broader Home Assistant compatibility.
- Made Google Routes credentials optional until that provider is enabled.
- Made TransportAPI credentials optional until rail monitoring is enabled.

### Changed

- Removed the manual TransportAPI budget reset so the configured daily limit
  cannot be bypassed.
- Removed the unused Core-only `strings.json` translation source.
- Renamed the public-facing project to UK Journey Guardian.
- Replaced location-specific routing assumptions with generic calendar parsing.
- Added support for selecting multiple destination zones.
- Added per-traveller preparation, station-buffer, and station-access settings.
- Added provider and Home Assistant prerequisites documentation.
- Added a public, privacy-safe development backlog including HACS submission.

### Added

- A default completion contract that publishes accepted work to `main`, creates
  the matching release, and verifies upgrade availability unless explicitly held.
- Architecture decision record and cutover engineering gates covering provider
  trust, freshness, state recovery, Repairs, migrations, and request brokering.
- Planned, active, and completed calendar-journey lifecycle handling so an
  underway leg remains available for follow-up monitoring until its event ends.
- Non-identifying brand icon for HACS and Home Assistant presentation.
- Initial Home Assistant custom-integration scaffold.
- UI configuration for calendar, traveller, zones, and TransportAPI allowance.
- Generic calendar normalization and origin/destination extraction.
- Persistent TransportAPI quota manager with an urgent-call reserve.
- Status, next-departure, decision-path, API-count, and data-health entities.
- Manual review button and Home Assistant actions.
- Redacted diagnostics, tests, and automated validation.
