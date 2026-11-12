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
contract. The [recovery route contract](RECOVERY_ROUTE_CONTRACT.md) now represents
ordered legs, transfer requirements, complete endpoints, freshness and explicit
limits. An internal Railinfo acquisition/normalization API now maps the previously
observed direct/one-change shape; see the recovery contract for response limits,
rejection rules and unsupported overnight/multi-change cases. Runtime disruption
context, user controls and adoption remain pending.

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


## Broader journey planning access — 8 November 2026

Railinfo documents direct and one-change journeys. Journey Guardian uses that
scope for its current recovery search and approval. The National Rail Journey
Planner provides a manual fallback when the app cannot validate a complete
route. The card opens the planner without adding calendar or station details
to the link.

- [Railinfo developer API overview](https://railinfo.uk/developers)
- [National Rail Journey Planner](https://www.nationalrail.co.uk/journey-planner/)

National Rail describes its Real Time Journey Planner (RTJP) SOAP feed as
supporting multi-leg planning with live Darwin data. Its developer page says
the feed is moving to the Rail Data Marketplace, and describes formal licensing
and cost recovery charges. This establishes a candidate feed. Access,
installation-level availability and current terms still need verification
before building or advertising an adapter.

- [National Rail Online Journey Planner data feeds](https://www.nationalrail.co.uk/developers/online-journey-planner-data-feeds/)

An adapter must demonstrate a complete route with two changes, dated service
identities, matched predictions at every endpoint and explicit handling for
cancelled or shortened services. Adoption, persisted tracking and recheck
limits must then expand together. Until those checks pass, a response that
cannot reach the final destination uses the manual fallback.
