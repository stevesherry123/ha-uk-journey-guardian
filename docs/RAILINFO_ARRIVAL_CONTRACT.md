# Railinfo arrival prediction contract (unreleased development)

Verified 4 November 2026 through the provider's public browser interface.
This is an observed field contract with strict rejection rules, not a guarantee
that the upstream API will retain its schema or provide every service.

## Sources and discovery

The [official API reference](https://api.railinfo.uk/docs) documents the
arrival board as using Darwin where available and a timetable fallback otherwise.
Its response example/schema does not specify a structured arrival record. A small
public arrival-board sample used `departures`, `public_dep` and `etd` names.
Those fields are not mapped to incoming arrival evidence because their arrival
semantics were insufficiently established. Service lookup likewise returns
generic `scheduled`/`expected` calling-point clocks, so it is not used for this map.

The documented [journey endpoint](https://railinfo.uk/developers) was inspected
using its public example station pair, independent of the owner's itinerary.
The observed direct-train legs included `from_crs`, `to_crs`, `dep`, `arr`,
`expected_dep`, `expected_arr`, `headcode`, `mode`, `status` and `status_source`.
The envelope included `date`, `is_today`, `journeys`, `changes` and `legs`.
Explicit `expected_arr` with `status_source: darwin` supports a provider-reported
arrival prediction, including an on-time prediction equal to scheduled arrival.
No actual railway arrival is established by these fields.

Only the field shape was copied into fictional tests. No real public service
record or private journey was added as a repository fixture. Browser discovery
supersedes earlier notes that detailed reference retrieval was unavailable.

## Accepted mapping and conservative limits

- Require the matching response date and `is_today: true`, also consistent with
  the broker observation's UK local date.
- Require a direct journey with exactly one train leg, matching resolved endpoints,
  the existing dated headcode identity and exact booked departure/arrival clocks.
- Require explicit `expected_arr`, Darwin provenance and supported non-cancelled
  leg status. Never synthesize arrival by adding departure delay to the timetable.
- Reject duplicate/conflicting matched records rather than choosing one.
- Interpret provider clocks in Europe/London regardless of the booking's display
  timezone. Support ordinary overnight arrival rollover relative to the booked
  arrival day, within less than 12 hours of its scheduled arrival.
- Reject ambiguous/nonexistent DST clocks without explicit provider offsets.
- Queries for a previous operating day after midnight remain unsupported by this
  mapper's current-day gate; report unknown instead of relabelling old data live.
- A timetable fallback, absent prediction, changed schedule, ambiguous identity or
  unsupported response produces no usable arrival evidence.

The observation timestamp is the original broker acquisition time. It is not a
claim to know the age of the provider's underlying feed. Cache reuse preserves
that timestamp. The evidence assessor separately enforces its freshness policy.

## Acquisition and runtime status

`RailinfoClient.async_arrival_prediction` and `async_departure_prediction` obtain the raw journey response through
the existing shared broker under `journey_details`, preserving rate-limit/error
handling and original cache timestamps. This cache namespace is distinct from
the existing transformed station-board response. Stale/unhealthy broker results
cannot produce live arrival evidence. The client does not consume TransportAPI
credits; that does not mean unbounded provider use is acceptable.

The development [connection monitor](CONNECTION_MONITORING.md) is now an opt-in
caller, using matched incoming/onward services and bounded broker requests. It
defaults to off. Connection-risk announcements are locally implemented behind existing live-alert
settings; recovery search remains pending,
as do live acceptance and production policy review.
