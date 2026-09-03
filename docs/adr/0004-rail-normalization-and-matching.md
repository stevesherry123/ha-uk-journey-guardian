# ADR 0004: Rail normalization and deterministic service matching

- Status: accepted
- Date: 2026-09-03
- Provenance: EB-004, EB-005, EB-007, EB-021, EB-037, and offline acceptance testing

## Context

Calendar events contain human-readable station names and planned times, while a
rail provider identifies stations with CRS codes and returns untrusted departure
records. A similar time alone is not enough to safely select a service. Duplicate,
corrected, malformed, ambiguous, and overnight records must not silently change a
journey decision. Provider identifiers and raw journey data must also remain out
of diagnostics.

## Decision

- Station identity is resolved from a validated configured CRS code, an explicit
  CRS code in calendar text, or one exact and unique match from a provider Places
  response. Conflicting or ambiguous evidence is rejected.
- Saved provider boards are validated and normalized into internal candidates
  before any decision is made. Raw payloads are not retained in coordinator data
  or diagnostics.
- Calendar journeys are matched within a bounded time window. Destination and
  operator evidence improve the match, but one unique best candidate is required.
- The provider train UID and service date produce a stable, one-way hashed service
  identity. The raw UID is not exposed by Home Assistant entities or diagnostics.
- Identical duplicate records collapse into one candidate. A later record may
  revise predicted time or platform while keeping the service identity. Conflicts
  in scheduled time, operator, or destination are rejected.
- Scheduled and predicted departures remain separate. Cancellation is explicit;
  it never creates an invented prediction.
- Midnight alignment considers adjacent dates but retains the provider service
  date in the stable identity.
- Production simulations create provider-shaped fixtures and pass through the
  same normalizer and matcher. Provider-unavailable simulation remains a separate
  acquisition-failure path.
- This slice is offline only. It adds no TransportAPI client and makes no network
  calls during setup, reload, review, or simulation.

## Consequences

- Normalization and matching can be tested with deterministic fixtures without
  consuming API allowance.
- Ambiguous or contradictory provider data fails safely instead of choosing the
  first record.
- Home Assistant exposes derived platform, match quality, and hashed service
  identity evidence while excluding the source payload.
- A future live client can be connected behind the existing provider broker
  without moving parsing or matching into acquisition code.
