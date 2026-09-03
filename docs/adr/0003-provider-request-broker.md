# ADR 0003: Provider request broker and freshness contract

- Status: accepted
- Date: 2026-09-03
- Provenance: EB-004, EB-005, EB-007, EB-037, and Journey Guardian testing

## Context

TransportAPI allowance is limited and must be shared by scheduled reviews,
manual reviews, and urgent checks. Independent provider callers could multiply
requests, consume the protected reserve, expose private request identifiers, or
make expired responses appear healthy. Provider failures and malformed payloads
must not leak upstream details into Home Assistant.

## Decision

- Every future provider client is invoked through one request broker owned by the
  Journey Guardian config entry.
- The broker hashes provider, operation, and parameters into a private cache key;
  it does not retain or expose the original request identity.
- Fresh results are cached briefly and concurrent equivalent requests share one
  in-flight task and one quota reservation.
- Only the durable TransportAPI budget can authorize a genuine cache miss.
  Routine work cannot consume the urgent reserve; an urgent waiter may retry a
  routine denial through that reserve.
- Provider payloads must be JSON objects with supported, finite values. Callers
  receive detached copies so they cannot mutate cached source data.
- Expired-but-bounded cached data may be returned after quota or provider failure,
  but it is explicitly classified as stale and unhealthy with a sanitized error
  category. Data beyond the stale limit is rejected.
- Short-lived provider payloads remain memory-only and are removed on config-entry
  unload. The important quota state remains versioned in Home Assistant storage.
- No live TransportAPI client is enabled as part of this decision. Tests use only
  deterministic provider fixtures.

## Consequences

- Loading, upgrading, or reloading the integration cannot contact a provider.
- Provider acquisition is testable independently from journey interpretation and
  decision logic.
- Raw payloads remain separate from derived rail observations and are excluded
  from diagnostics.
- A later TransportAPI client must implement its parser and freshness mapping at
  this boundary rather than introducing direct calls elsewhere.
