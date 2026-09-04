# ADR 0007: Shared provider-account quota

- Status: accepted
- Date: 2026-09-04
- Provenance: first live TransportAPI acceptance day

## Context

Journey Guardian's durable broker counted four requests while TransportAPI
reported that the account's daily allocation was exhausted. The broker can
serialize every request made by this integration, but it cannot see requests
made by a legacy Home Assistant package, another integration, a script, or an
external application using the same provider account.

The earlier entity name implied that its locally observed reservations were the
provider account's complete daily usage. A routine calendar refresh also replaced
the transient live-check error before it could be inspected.

## Decision

- Treat the local counter as a conservative Journey Guardian budget, not an
  authoritative provider-account usage meter.
- Continue reserving and persisting every integration request before network
  access.
- When TransportAPI reports allocation exhaustion, classify it as a stable quota
  error, set the local budget to its daily limit, persist that state, and prevent
  further requests until rollover.
- Publish the latest budget snapshot on every failed live check.
- Retain the last privacy-safe live-rail error across provider-free calendar
  refreshes; clear it only after a successful live-rail review.
- Label the Home Assistant entity and its attributes so external consumers are
  explicitly outside its normal scope.

## Consequences

- Legacy and Journey Guardian can temporarily share credentials during cutover,
  but their combined provider usage cannot be predicted from the integration's
  local counter.
- Provider-reported exhaustion fails closed even when unseen consumers made most
  requests.
- A normal calendar refresh can restore safe planning and data health without
  erasing the evidence needed to diagnose the previous live failure.
- Retiring or disabling legacy provider polling remains necessary before relying
  on Journey Guardian's budget for planned automatic monitoring.
