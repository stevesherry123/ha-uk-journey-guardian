# Changelog

All notable changes to Journey Guardian will be documented in this file.

## [Unreleased]

## [0.1.16] - 2026-09-07

### Fixed

- Chester, Liverpool Lime Street and London Euston now use deterministic CRS
  identities instead of consuming Places quota and depending on provider naming.
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
- Destination evidence now uses whole-name boundaries, so a place name such as
  `Chester` cannot incorrectly match inside `Manchester`.
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
