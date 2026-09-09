# Development backlog

This backlog deliberately uses generic terminology. Real stations, destinations,
addresses, calendars, people, notification targets, and credentials must remain
inside each user's Home Assistant installation.

## Legacy cutover checklist

- [x] discover and normalize generic timed calendar journeys
- [x] retain an underway journey until its calendar event ends
- [ ] provide manual-review parity through the shared decision engine
- [ ] monitor direct and split rail legs within the shared provider budget
- [x] calculate preparation and leave times with a conservative routing fallback
- [x] send configurable local operational notifications with restart-safe
  deduplication
- [x] replace rapid wake-up loops with bounded, cancellable phase scheduling
- [ ] pass direct, split, delayed, cancelled, restart, and provider-outage tests
- [ ] disable the legacy packages and complete an observation period
- [ ] remove the legacy packages only after the observation period succeeds

## Real-travel readiness sequence

- [x] retain successful pre-departure rail evidence between calendar and route
  refreshes without duplicating notifications
- [ ] persist the latest actionable journey and rail observation across a Home
  Assistant restart, with schema versioning and bounded expiry
- [ ] follow delayed services after scheduled departure at bounded intervals
  until departure, cancellation, or the calendar journey ends
- [ ] expose sustained calendar, routing, and rail-provider failures through
  Home Assistant Repairs rather than relying only on log warnings
- [ ] validate direct outbound and return journeys during one real travel day
  before adding interchange monitoring or additional notification adapters

## Legacy capability parity inventory

The legacy packages remain the acceptance specification until every applicable
capability below is implemented, deliberately retired, or recorded as an
accepted replacement decision. Route names and private entity IDs are omitted.

- [ ] support multiple configured origin stations and choose only the assistant
  whose origin matches the timed calendar leg
- [ ] calculate a dynamic preparation alarm from preparation time, station
  access duration, station buffer, and an early-warning margin
- [ ] provide an optional persistent wake-up alarm that repeats until bounded
  timeout, explicit acknowledgement, or configured movement/activity evidence
- [x] support road-routing station access with freshness checks, per-origin
  conservative fallbacks, and one warning per journey when routing is unavailable
- [x] support public-transport and walking access to a station, including an
  arrive-by request, conservative fallback, and one warning per journey
- [x] schedule quota-aware rail checkpoints approximately 150, 90, 45, and 10
  minutes before departure without duplicate requests across route profiles
- [ ] report live service status, predicted time, platform, destination evidence,
  ambiguous same-time matches, missing services, cancellations, delays, and
  station-wide disruption
- [ ] notify on meaningful rail-state transitions while suppressing unchanged
  repeats across reviews, reloads, restarts, and date rollover
- [ ] issue a leave-now notification using current access time and retain a
  conservative last-chance warning when normal confirmation cannot be produced
- [ ] monitor a delayed service after scheduled departure at bounded follow-up
  intervals, stopping when it leaves the board or is cancelled
- [ ] make manual review cover no upcoming journey, departed journey, unknown
  origin, board-not-yet-open, provider unavailable, ambiguous match, and the
  configured station-access mode
- [ ] provide configurable notification adapters for mobile push, spoken
  announcements, and wearable delivery without private entity IDs in integration
  code
- [ ] optionally trigger a destination-area local-transit review from presence,
  with a cooldown and manual-review control
- [ ] compare a preferred local-transit route with the fastest available route,
  apply a configurable time tolerance, account for disruption, and provide safe
  fallback instructions
- [ ] expose enough privacy-safe state and diagnostics to prove each legacy helper
  can be removed without losing deduplication, alarm, routing, or disruption state

## Release polish

- [ ] ship the options-flow translation regression fix so the automatic live rail
  toggle always displays a human label in Home Assistant

## Legacy defects and temporary controls

- [ ] correct the legacy timed-event predicates if the packages remain enabled:
  their negated all-day tests currently admit unrelated timed events and can make
  several route assistants refresh provider sensors for one journey
- [ ] remove the duplicated event loop in the legacy return assistant if that
  package remains in service
- [ ] during shadow testing, disable the legacy route-assistant automations,
  delayed-service monitors, and manual provider-review script before enabling
  Journey Guardian live requests
- [ ] after cutover, remove the three legacy REST rail sensors and their stored
  provider credentials from core configuration; do not rely on their long scan
  interval as a permanent quota control

## Engineering gates for cutover

- [x] use Home Assistant-native configuration and privacy-safe diagnostics
- [x] persist the shared provider budget and protect an urgent reserve
- [x] sanitize calendar/provider exceptions into stable public categories
- [x] keep integration actions safe across config-entry reloads
- [x] document the layered, local-first architecture and trust boundaries
- [x] route every provider request through a caching, deduplicating request broker
- [x] expose source freshness and distinguish stale data from healthy current data
- [x] separate raw provider observations from derived journey decisions
- [x] distinguish scheduled, predicted, cancelled, and inferred values
- [ ] add provider confirmation semantics without inferring them from predictions
- [ ] surface actionable configuration/provider faults through Home Assistant Repairs
- [ ] version persisted journey state and test idempotent restart/reload recovery
- [x] reject or normalize malformed, duplicate, corrected, and unsupported rail
  records before they reach the decision layer
- [ ] validate calculated departure decisions against authoritative observations
- [ ] retain the rationale for deferred or rejected engineering decisions

## Pre-feature hardening

- add Home Assistant integration-level tests for config flow, setup, unloading,
  coordinator refreshes, entities, actions, diagnostics, and recovery paths
- add contract tests for malformed, duplicate, stale, corrected, and unsupported
  calendar/provider records
- preserve privacy-safe raw source observations separately from derived state where
  replay or incident investigation is required
- add schema versions and migrations before persisting journey lifecycle state
- surface prolonged calendar unavailability using a last-successful-review
  timestamp and a privacy-safe stale-data warning
- sanitize provider and calendar exceptions before exposing error state,
  diagnostics, logs, or action responses
- preserve the TransportAPI allowance as a hard daily limit by removing or
  tightly controlling manual budget resets
- register integration actions during integration setup and make their lifecycle
  safe across config-entry reloads and unloading
- add an options and reconfiguration flow for calendars, profiles, buffers,
  access mode, destinations, provider settings, notification adapters, and quotas
- collect provider credentials only when the corresponding provider is enabled;
  validate credentials and support reauthentication without exposing saved values
- expand the privacy scanner to cover provider keys, Home Assistant tokens,
  authorization headers, private entity domains, and a maintained private-place
  denylist
- prevent unchanged coordinator reviews from creating unnecessary entity-state
  and Recorder writes
- add a privacy-safe `simulate_journey` action for deterministic acceptance tests
  without calendar-feed latency or provider quota use (implemented in v0.1.5)
- add accelerated operational-phase simulations plus restart-safe local
  notification deduplication (implemented in v0.1.6)
- add a quota-enforcing request broker with cache, in-flight deduplication,
  sanitized errors, bounded stale fallback, and unload cancellation (implemented
  in v0.1.7)
- expose rail freshness and a quota-free stale-data simulation (implemented in
  v0.1.7)
- add offline station resolution, rail-board normalization, deterministic
  matching, stable service identity, and production-path simulations (implemented
  in v0.1.8)
- add an explicit manual-only TransportAPI gateway with header authentication,
  quota brokering, bounded live boards, and no background provider calls
  (implemented in v0.1.9)
- filter live boards by the intended calling-point CRS code, use whole-name
  destination evidence, and reject material schedule offsets (implemented in
  v0.1.10)
- reconcile provider-reported account exhaustion, retain live-check errors across
  calendar refreshes, and clarify integration-local budget scope (implemented in
  v0.1.11)
- add opt-in restart-safe automatic live-rail checkpoints with bounded catch-up
  and urgent-reserve use only at the final checkpoint (implemented in v0.1.12)
- add a shadow-mode acceptance checklist covering calendar discovery, state
  transitions, restart recovery, stale data, diagnostics, and entity history
- add privacy-safe structured telemetry for poll times, event and candidate
  counts, decision transitions, and error categories without journey details
- align public entity-ID examples with Home Assistant's generated defaults and
  remove translation files that are not used by custom integrations

## Core journey engine

- editable traveller profiles with preparation and station-arrival buffers
- destination profiles supporting any number of regular destinations
- expose rail station name and CRS-code resolution in the user-facing journey
  flow without hard-coded personal routes (offline resolver implemented in v0.1.8)
- lightweight monitoring for every leg of a split journey
- delayed-service checks after scheduled departure when a train has not departed
- provider failure handling, stale-data warnings, and quota-safe fallbacks
- validate the manual live gateway against representative real journeys before
  enabling any automatic provider monitoring

## Routing and notifications

- [x] Google Routes estimates for walking, cycling, road, and public-transport
  station-access legs with a bounded adaptive cache and conservative fallback
- configurable notification, announcement, and wearable adapters
- enhanced manual review using the same traveller and destination decision tree
- optional UK local-transit comparison for suitable destination profiles
- investigate an optional Seatfrog integration for UK rail journeys, covering
  operator and service eligibility, journey matching, available APIs or deep
  links, commercial requirements, and where to surface relevant upgrade offers;
  journeys without an available upgrade must continue unaffected

## International air-travel module

This is a future, disabled-by-default extension of Journey Guardian, not a
separate replacement integration. It must not affect the existing rail decision
path until it has independent acceptance coverage.

- add provider-neutral flight-leg and itinerary models, with IATA airport codes,
  airline/flight number, scheduled and estimated departure/arrival, terminal,
  gate, and explicit source freshness
- preserve IANA time-zone information for every flight and ground-transfer time;
  cover outbound and return journeys across the UK and North American time zones,
  including daylight-saving transitions
- add airport profiles for access mode, airport-arrival target, check-in,
  security, bag-drop, immigration, and connection buffers, all with conservative
  fallbacks and explicit provenance
- calculate a calendar-led `home → airport → flight → destination` plan without
  changing rail-only journey timing
- introduce an optional flight-status provider adapter behind the existing
  request-budget, caching, freshness, redaction, and failure-handling contracts
- evaluate FlightRadar24 as an optional Home Assistant entity/event adapter:
  consume a deliberately selected tracked flight or airport board rather than
  duplicate its polling or hard-code a target
- support flight-specific evidence and notifications: check-in, leave for the
  airport, terminal/gate change, delay, cancellation, boarding, arrival, and
  connection risk
- expose a read-only flight itinerary and notification preview before enabling
  any live mobile delivery
- define airport and flight-provider test fixtures, including date-qualified
  flight-number matching, codeshares, aircraft substitution, overnight flights,
  cancelled flights, and ambiguous same-number services
- validate direct international journeys and a connection in shadow mode before
  enabling live flight notifications; retain existing alarms and manual checks
  throughout the observation period
- consider a separate Journey Guardian flight dashboard only after the decision
  engine works; reuse dedicated aviation cards for map/aircraft visualisation
  rather than reimplementing them

## Post-journey delay-repay assistance

This is a future rail follow-up module. It must be evidence-led, preserve
privacy, and never submit a financial claim without explicit user approval.

- retain a privacy-safe post-journey outcome record containing the booked leg,
  provider-confirmed actual arrival, delay minutes, evidence freshness, and any
  uncertainty or matching failure
- distinguish service delay from a missed connection, cancellation, shortened
  journey, voluntary re-routing, and calendar/ticket mismatch; never infer a
  claim from an incomplete result
- maintain a reviewed, date-versioned catalogue of rail-operator Delay Repay
  policies, thresholds, eligibility conditions, exclusions, and claim windows
- compare the confirmed delay against the applicable operator policy and produce
  a clear advisory: likely eligible, likely ineligible, or insufficient evidence
- present a post-journey review containing the evidence, policy version, claim
  deadline, and required ticket/payment details without storing sensitive ticket
  data in diagnostics or the notification ledger
- provide a user-controlled reminder before a claim deadline and an exportable
  claim checklist or evidence summary
- investigate operator-supported claim APIs or secure user-authorised web flows;
  only add claim submission after explicit per-claim confirmation, robust
  authentication handling, an auditable result, and failure recovery
- create fixtures for threshold delays, late-night arrivals, cancellations,
  disrupted connections, operator changes, and policy changes; validate against
  real journeys before offering eligibility advice

## Distribution

- publish alpha releases for installation as a HACS custom repository
- create non-identifying brand assets (packaged and regression-tested)
- add and pass HACS Action and Hassfest validation
- pin or constrain development and CI tooling for reproducible validation
- update GitHub's checkout and Python setup actions to Node.js 24-based releases
  once their pinned replacement versions are adopted
- add a repository description and generic topics without private route details
- protect the default branch with required validation checks when the development
  workflow is ready for pull requests
- document supported Home Assistant versions and upgrade migrations
- submit to the HACS default catalogue after the integration is stable
