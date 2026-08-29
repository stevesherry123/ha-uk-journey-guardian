# ADR 0001: Layered, local-first journey engine

- Status: accepted
- Date: 2026-08-29
- Provenance: project engineering principles and UK Journey Guardian review

## Context

Journey Guardian must replace long-running Home Assistant automations without
turning calendar, routing, and rail-provider responses into one coupled workflow.
It must remain understandable during outages, survive Home Assistant restarts,
protect limited provider quotas, and avoid exposing personal journey details.

## Decision

The integration will use these boundaries:

`user intent -> journey discovery -> resolver -> state model -> decision engine -> request broker`

- Home Assistant configuration and calendar events express user intent.
- Discovery normalizes untrusted source records without making provider calls.
- Resolvers map generic user input to provider identifiers.
- The state model distinguishes scheduled, predicted, confirmed, cancelled, and
  inferred values and records source freshness.
- The decision engine consumes normalized state and produces privacy-safe outcomes
  and decision paths.
- A shared request broker owns provider authentication, caching, in-flight request
  deduplication, persistent quota accounting, and the urgent reserve.

Raw source observations needed for recovery or incident analysis remain separate
from derived journey summaries. Important stored state uses explicit schema
versions and migrations. Restart and reload recovery must be idempotent.

External data is untrusted. Malformed, duplicate, stale, corrected, and unsupported
records are handled explicitly. Provider exceptions are reduced to stable public
error categories before reaching entities, diagnostics, Repairs, or user logs.

Configuration stays Home Assistant-native. Actionable configuration and provider
problems use Repairs; diagnostics redact credentials, identifiers, locations, and
journey content. Providers receive read-only access unless a separately reviewed
feature clearly requires write access.

## Consequences

- Provider clients must not call external services directly from entities or
  buttons.
- Feature slices require tests at the layer boundary they introduce, including
  restart and failure behavior where state is durable.
- Estimated or inferred values must never appear indistinguishable from verified
  provider observations.
- Legacy automations remain enabled until cutover acceptance tests and an
  observation period pass.
