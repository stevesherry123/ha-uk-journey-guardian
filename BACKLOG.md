# Development backlog

This backlog deliberately uses generic terminology. Real stations, destinations,
addresses, calendars, people, notification targets, and credentials must remain
inside each user's Home Assistant installation.

## Pre-feature hardening

- add Home Assistant integration-level tests for config flow, setup, unloading,
  coordinator refreshes, entities, actions, diagnostics, and recovery paths
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
  without calendar-feed latency or provider quota use
- add a shadow-mode acceptance checklist covering calendar discovery, state
  transitions, restart recovery, stale data, diagnostics, and entity history
- add privacy-safe structured telemetry for poll times, event and candidate
  counts, decision transitions, and error categories without journey details
- align public entity-ID examples with Home Assistant's generated defaults and
  remove translation files that are not used by custom integrations

## Core journey engine

- editable traveller profiles with preparation and station-arrival buffers
- destination profiles supporting any number of regular destinations
- rail station name and CRS-code resolution without hard-coded personal routes
- lightweight monitoring for every leg of a split journey
- delayed-service checks after scheduled departure when a train has not departed
- provider failure handling, stale-data warnings, and quota-safe fallbacks

## Routing and notifications

- Google Routes estimates for walking, cycling, and road station-access legs
- configurable notification, announcement, and wearable adapters
- enhanced manual review using the same traveller and destination decision tree
- optional UK local-transit comparison for suitable destination profiles

## Distribution

- publish alpha releases for installation as a HACS custom repository
- create non-identifying brand assets
- add and pass HACS Action and Hassfest validation
- pin or constrain development and CI tooling for reproducible validation
- update GitHub's checkout and Python setup actions to Node.js 24-based releases
  once their pinned replacement versions are adopted
- add a repository description and generic topics without private route details
- protect the default branch with required validation checks when the development
  workflow is ready for pull requests
- document supported Home Assistant versions and upgrade migrations
- submit to the HACS default catalogue after the integration is stable
