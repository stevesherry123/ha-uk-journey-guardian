# ADR 0005: Manual-only live rail gateway

- Status: accepted
- Date: 2026-09-03
- Provenance: EB-004, EB-005, EB-007, EB-037, and user acceptance of v0.1.8

## Context

The provider broker, rail normalizer, and simulations have passed offline tests,
but automatic monitoring would broaden both operational risk and quota use. The
first live connection needs to validate credentials, station resolution, current
TransportAPI response shape, and service matching without allowing installation,
reload, polling, or a simulation to spend allowance.

## Decision

- Live rail acquisition is available only through the dedicated **Check live rail
  now** button or `journey_guardian.review_rail_now` action.
- Setup, reload, ordinary **Review now**, ten-minute polling, and all simulations
  remain provider-free.
- The live client uses TransportAPI's documented header authentication so secrets
  never appear in request URLs or broker cache identities.
- Every Places and station-timetable request passes through the shared broker and
  durable budget before network access. Manual testing does not consume the urgent
  reserve.
- The initial unresolved station may require one Places request and one timetable
  request. Exact station resolutions are cached only in memory, with hashed keys
  and a bounded size. Repeated board requests also use the broker's short cache.
- Timetable queries request passenger services in a bounded window around the
  calendar departure and explicitly request live augmentation.
- Raw provider responses and raw train UIDs remain outside coordinator state,
  entity attributes, diagnostics, and logs. Only normalized observations are
  published.
- Missing credentials, simulations, absent journeys, ambiguous stations,
  malformed responses, provider failures, and quota denial fail before an unsafe
  decision can be published.

## Consequences

- A user deliberately controls each real provider review during the first live
  validation milestone.
- One manual result may be replaced by the next provider-free calendar refresh;
  this is intentional until automatic monitoring policy is accepted.
- Evidence from real responses can validate the normalization boundary before
  scheduled polling or notification behaviour is enabled.
- Automatic monitoring remains a separate future decision with its own frequency,
  urgency, freshness, and lifecycle acceptance criteria.
