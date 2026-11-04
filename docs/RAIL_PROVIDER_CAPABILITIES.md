# Rail provider capability inventory

Updated 3 November 2026. Source inspection of the local dashboard development
branch, not live-provider validation. An absent adapter feature does not establish
that the upstream service lacks it. No new provider requests or credentials used.

| Capability | Existing implementation | Required next evidence/work |
| --- | --- | --- |
| Station resolution | Railinfo station search; TransportAPI places adapter | Retain explicit ambiguity handling |
| Service matching | Shared normalizer matches departure and destination; dated service identity | Validate identity continuity across prediction, arrival and recovery results |
| Departure predictions | Shared model supports predicted departure; new pure bridge preserves timestamp and rejects unusable observations; Railinfo mapping currently sets expected departure blank | Wire only after per-leg monitoring and expected-service references exist; confirm upstream fields |
| Destination arrival prediction | Separate typed evidence contract and conservative Railinfo journey mapper implemented locally | See [arrival contract](RAILINFO_ARRIVAL_CONTRACT.md); opt-in development monitoring now wired; live acceptance pending |
| Confirmed arrival | Railinfo board collector matches dated service identity and actual arrival | Reuse evidence; do not treat nightly collection as live arrival prediction |
| Cancellation | Normalizer recognizes cancellation status | Validate positive matched evidence on each supported provider |
| Early termination | No complete supported detection path established | Validate shortened-service evidence; keep explicit unresolved/manual path |
| Direct search | Railinfo /journeys feeds direct-service matcher | Define a separate recovery-search result contract |
| Multi-change search | Railinfo adapter explicitly discards changes != 0 and multi-leg results; TransportAPI client has no recovery search | Validate upstream journey-search response, access, cost and transfer semantics before promising support |
| Budget/cache/retries | Existing shared broker | Allocate a bounded end-to-end search and monitoring budget; Railinfo quota_controlled=False is not evidence of unlimited upstream capacity |

## Review findings

The existing connection helper previously labelled a predicted arrival later than
onward departure as missed. This is now at risk: predictions alone cannot prove
that the user missed a train. The helper remains review-only; no live connection
warnings are enabled by this change.

## Official documentation check: 3 November 2026

[Railinfo's developer reference](https://railinfo.uk/developers) documents
journey planning with direct routes and one change, plus live status. This
supports investigating two-train recovery, not promising arbitrary multi-change
coverage. It also documents separate departures and arrivals board endpoints.
The existing generic board path therefore needs contract verification before
changing arrival collection. Its REST fair-use limit is documented as 240
requests per minute per IP with 429/Retry-After responses; shared broker caching
and bounded scheduling remain necessary.

[TransportAPI's developer portal](https://developer.transportapi.com/) advertises
journey planning and rail journey details, with separate managed-service access.
This does not prove the configured account includes the required planner, nor
establish its response schema or cost. Do not silently enable a paid service.

Detailed Railinfo OpenAPI retrieval was unavailable through browsing, and direct
retrieval failed DNS resolution in this environment. Arrival prediction fields,
early-termination signals, revalidation and routes with more than one change
remain unverified. No provider contract is inferred from marketing descriptions.

### Next adapter boundary

Keep recovery route search separate from the existing direct-service matcher:
removing its direct-only filter would feed multi-leg results into a single-leg
contract. Introduce a route result containing ordered train legs, internal
transfers, final-destination coverage, freshness and explicit search limits.
Only map a provider after its detailed response contract is established.

### Local verification

The three existing connection assessment tests pass by direct execution on
Python 3.14.2, including the corrected negative-margin risk classification.
This is a focused pure-function check, not the full Home Assistant test suite.

## Capability gate exit

Record official provider contracts or approved representative responses for
predicted destination arrivals, cancellation, early termination and multi-change
search. Document date/time zones, identity, freshness, errors, limits and cost.
Use fictional/sanitized fixtures. Until then these capabilities are unverified,
not completed, and no automatic recovery claim should appear in user guidance.

## Arrival verification update: 4 November 2026

Browser access succeeded where the web reader had failed. Explicit direct-journey
arrival prediction fields and provenance were inspected in public sample responses.
See the [observed arrival contract](RAILINFO_ARRIVAL_CONTRACT.md) for mapping,
strict limits and remaining runtime integration. Generic arrival-board and
service-detail clocks are not treated as verified arrival prediction fields.
