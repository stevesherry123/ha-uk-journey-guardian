# Changelog

All notable changes to Journey Guardian will be documented in this file.

## [Unreleased]

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
