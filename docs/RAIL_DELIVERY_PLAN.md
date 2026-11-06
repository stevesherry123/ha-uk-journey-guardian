# Rail connections and end-to-end recovery delivery plan

Updated: 6 November 2026. Status: accepted product scope; partial local implementation.
No release date is promised. Current stable: v0.2.13. Existing previews retain
bookings and show schedule hints; they do not deliver this connection/recovery workflow.

## Consolidated architecture and implementation guide

### Product intent and current assessment

Deliver dependable rail commuting assistance from preparation through connections, disruption and outcome review. Flights are deferred. Existing single-leg timing, provider broker, notification controls, retained booking groundwork and evidence collection should be extended. The reported user gap is connection-risk and disruption advice. Historical checkpoints establish progress but do not verify current HA state or current provider capability.

### State ownership

- Booked plan: independent original calendar legs and stable identities; keep booking edits distinguishable.
- Connection preferences: global allowance initially 10 minutes, station defaults and per-connection overrides, plus saved suggestion templates.
- Confirmed connections: explicit user confirmation tied to specific bookings; saved templates never substitute for confirmation.
- Observations: matched service facts and predictions, source, timestamps, freshness and confidence; preserve user reports separately.
- Active travel: original selected leg or explicitly adopted replacement route. A replacement can contain multiple trains and its own internal connections.
- Disruption cases: triggering evidence, affected original leg, search origin/destination, candidate routes and adoption history.
- Delivery and outcomes: restart-safe alert history and per-leg evidence, preserving original intent alongside what was tracked.

The coordinator orchestrates these stores and the decision engine. Entities and dashboard actions read projections or submit explicit commands; they do not call providers directly. Existing broker controls all searches and live checks.

### User flow

1. Discover separate rail events and retain them independently.
2. Suggest plausible connections; prefill saved preferences and show the allowance source.
3. User confirms the specific connection, optionally edits its allowance and saves a suggestion template.
4. Monitor incoming arrival and onward departure under one shared provider budget.
5. Warn through the existing announcement route when fresh predictions put available transfer below the allowance; retain the dashboard warning and update on meaningful changes.
6. On supported disruption evidence, search direct and multi-train options from an evidenced origin to the final destination of the confirmed connected journey, considering all affected downstream legs.
7. Present complete route details, internal changes, evidence freshness, arrival estimates and unknown ticket acceptance.
8. User explicitly selects an option; revalidate its availability and timings before adoption.
9. After explicit approval of the complete route, track its internal legs and transfers through the final destination. Show which original downstream legs are superseded for tracking; preserve their booked records and leave unrelated journeys untouched.
10. Retain original bookings, adopted route and observed outcomes for the travel-day review.

### Delivery gates

1. Baseline and capability discovery: reconcile current branch/runtime, inspect a representative split journey, validate provider service identity, short-running evidence and multi-change route search. Output a capability matrix with supported and unavailable behaviours.
2. Data contracts and persistence: define booking/connection identity, confirmation invalidation on edits, evidence freshness, adopted multi-leg routes, schema migrations and bounded retention. Agree open policy decisions below.
3. Connection controls: implement station/global preferences, per-connection override, suggestion templates and explicit confirmation. Prove templates never auto-confirm a connection and unrelated bookings are not silently linked.
4. Live assessment and warnings: monitor current and onward trains, compute explained margins, qualify stale data, suppress duplicate warnings and restore state safely after restart. Validate a real split journey and physical announcements.
5. Recovery search: deliver bounded direct/multi-change candidates after matched disruption or labelled user confirmation. Unsupported searches produce an actionable manual fallback. Do not build an unbounded network-wide optimizer to compensate for missing provider capability.
6. Explicit adoption: revalidate selected end-to-end routes, track internal trains and transfers, preserve booked intent and explicitly identify downstream legs superseded for tracking. Prove duplicate selection and restart cannot create duplicate tracking or notifications. Include a case where a leg-only recovery would strand the user after an onward departure; require a complete final-destination option or an explicit unavailable outcome.
7. Full acceptance: rehearse normal/tight/missed connections, delayed onward trains, cancellations, early termination, failed searches, stale evidence, booking edits, overnight/DST cases, outages, quota exhaustion and restart. Then complete an agreed real-travel observation period before deployment/cutover claims.

### Remaining design policies

- Suggestion-template fields and booking-edit invalidation.
- Cross-station transfers and ambiguous/overlapping events.
- Route-search limits, provider costs and maximum changes; distinguish transfer preferences from official provider minimums.
- Allowance policy and confirmation behaviour for internal connections in a newly selected replacement route.
- Alert meaningful-change thresholds, recovery messages and oscillation control.
- Evidence retention duration and UI details.

These policies are resolved in the relevant delivery gate. This plan does not itself authorize deployment or an HA restart; the implementation progress below records local work.


## Delivery tracking

| Gate | Status | Required evidence |
| --- | --- | --- |
| Baseline and provider discovery | In progress | Source inventory and official overview checked; detailed arrival/short-running/search schemas remain unverified |
| State contracts and persistence | Partly implemented locally | Versioned confirmations and typed time evidence tested; adoption/evidence retention pending |
| Confirmation and allowances | Implemented and reviewed locally | Persistence, defaults, provenance and fictional mobile controls tested; saved templates and live HA acceptance pending |
| Live risk and warnings | Opt-in monitoring and announcements implemented locally | Durable transitions and guarded existing delivery route tested; live HA/physical delivery acceptance pending |
| End-to-end search | Route contract and internal Railinfo search implemented locally | Bounded one-query direct/one-change normalization tested; disruption context, user controls, broader provider coverage and selection pending |
| Explicit adoption | Pending | Whole-route approval, downstream tracking, original evidence retained |
| Release acceptance | Pending | Outage/restart rehearsals and real-travel observation |

## Documentation is part of each delivery gate

Every feature change must update the relevant user guide, known limitations,
configuration examples and troubleshooting guidance in the same change. Update
the changelog with the actual shipped behaviour and validation; label unreleased
work explicitly. Keep README and stable installation advice aligned with published
releases, and distinguish preview-only behaviour. Never describe a passing rehearsal
as verified physical delivery or a loaded version as real-travel acceptance.

Architecture changes need an ADR describing the accepted decision and migration
impact. Update this status table with evidence when a gate advances. Before a
release, check local documentation links, release/version consistency, privacy of
examples, upgrade instructions, and documented fallback behaviour. Use fictional
journeys in public fixtures and guidance. No private itinerary or installation
identifiers belong in public documentation.

## First work package: capability and state contracts

- Inventory existing broker, service matching, retained plan, arrival collection,
  notification ledger and dashboard boundaries; extend these rather than duplicate them.
- Establish whether each configured provider can supply matched destination arrival,
  cancellation, early termination, direct and multi-change journey searches, stable
  service IDs and fresh revalidation. Record quota cost, limitations and manual fallback.
- Define confirmed connected-journey endpoints; never use an unrelated return booking
  as the recovery destination.
- Specify booking-edit invalidation, connection confirmation and override identity,
  replacement internal connections, expiry and schema migration before runtime changes.
- Acceptance example: a delayed incoming train threatens an onward train; a later
  early termination requires a route to the final destination. A route ending at
  the interchange after the onward departure must not count as successful recovery.

## Work-package findings

See the [provider capability inventory](RAIL_PROVIDER_CAPABILITIES.md) and
[proposed state contracts](RAIL_STATE_CONTRACTS.md). Source inspection is complete;
upstream provider verification remains pending. The review-only connection helper
now classifies negative predicted margins as at risk rather than confirmed missed.

Official-documentation discovery confirms Railinfo advertises direct and one-change
planning; broader change coverage and detailed live schemas remain unverified.
Three focused connection checks now pass on Python 3.14.2; the full HA suite has
not run. See the capability inventory for sources and retrieval limitations.

### Allowance foundation implemented locally

The review-only connection module now resolves connection override, station
default and labelled global fallback (10 minutes). Invalid values are rejected.
Connection arithmetic uses UTC instants, including repeated local times during
autumn clock changes; timezone-free times are rejected. Seven focused checks
passed on Python 3.14.2 by direct execution. No settings UI, persisted confirmation,
live assessment or alerts are enabled; these remain pending. Zero minutes is
accepted by the pure resolver pending the settings-bound policy decision.

### Confirmation persistence foundation implemented locally

Added a storage-interface-based, versioned confirmation store with exact booking
pair identities, expiry, scoped loading, bounded capacity and serialized writes.
Booking identity changes cannot inherit confirmation; templates have no confirmation
path. Failed writes do not commit confirmation in memory, and unreadable or
wrong-scope stores block writes until successfully loaded. Ten focused checks
passed by direct execution on Python 3.14.2 across allowance and confirmation
modules, including restart, edited identity, expiry and failed-save behaviour.
The store is not yet instantiated by the HA coordinator; no confirmation UI,
HA storage integration or live alert gating is enabled. Retention policy and
booking identity integration still require completion before runtime use.

### HA lifecycle wiring, local and awaiting integration validation

The coordinator now owns a calendar/entry-scoped HA confirmation store, loaded
during entry setup. Storage keys and scope are hashed. Load failures disable
confirmation writes without interrupting existing journey startup; successful
reload clears degraded status. The store owns no background timers or listeners.
An HA adapter regression test and setup mock update are included. Ruff passes;
HA integration tests remain unrun because pytest/HA test dependencies are absent
from the available Python environment. This slice must not be released until
those checks pass. Booking-pair lookup uses existing exact retained IDs, but
confirmation commands, UI and booking identity validation are still pending.

### HA validation completed: 3 November 2026

Using Python 3.14.2 and cached test dependencies, 18 focused connection/storage/
startup tests pass under pytest. The full network-disabled suite completed with
one existing early-termination expected failure and one frontend test blocked by
local TCP binding restrictions; all other tests passed. The frontend test passed
when rerun with approved loopback binding and external sockets still disabled.
Repository-wide Ruff and privacy scan pass. This supersedes earlier notes about
unavailable HA test dependencies; the adapter and startup tests are now verified.
No live HA restart, provider requests or deployment occurred. The existing
early-termination acceptance gap remains open and is not waived by these checks.

### Confirmation actions: 4 November 2026

Added confirm/revoke actions with exact retained-booking validation, simulation
isolation, persisted revocation and save-failure protection. Validation requires
current adjacent same-station bookings, booked arrival and non-overlapping times,
with an onward departure still in the future. The [development controls guide](CONNECTION_CONTROLS.md)
documents usage, expiry and limitations. No dashboard controls, live connection
monitoring, station preferences or recovery search are enabled by these actions.

Validation for the confirmation-action slice: 52 focused tests passed before
adding six further input/isolation cases; all seven service tests then passed.
The broader network-disabled suite passed with the existing early-termination
expected failure; the previously verified loopback frontend test was explicitly
deselected because this run does not allow local TCP binding. Ruff, privacy scan,
54 local documentation links and diff checks pass. These checks do not establish
physical announcements, live provider coverage or deployment readiness of the
remaining connection/recovery workflow.

### Dashboard confirmation controls: 4 November 2026

The development card now projects current adjacent connection candidates from
retained identities and shows persisted confirmation, optional allowance override
and confirm/revoke controls. Actions refresh entity listeners after saving.
Pending writes disable controls, errors remain visible and simulation hides real
connections. No live risk status is claimed. The existing schema-1 projection is
extended with optional connection fields for older card compatibility.
Seven Node tests pass, including successful/failed writes and invalid overrides;
backend projection, sensor and service regression checks cover saved-state changes
and simulation isolation. Browser visual acceptance remains pending before release.

### Transfer defaults: 4 November 2026

Development options now expose the global transfer fallback (initially 10) and
station-name defaults, with validated duplicate-free parsing. The dashboard
projects applied minutes and provenance; explicit booked-pair overrides take
precedence. Exact station-name matching normalizes whitespace/case and the
optional zone prefix; no fuzzy station matching is introduced. Controls and
limitations are documented in the connection guide. Risk monitoring remains
pending; defaults do not affect existing access or preparation timings.

Validation for transfer defaults: 50 focused parser/options/retained-plan tests
and seven dashboard tests pass. The broader network-disabled regression suite
also passes with the existing early-termination expected failure and the loopback
frontend test explicitly deselected. Ruff, privacy and diff checks pass.

### Browser acceptance of connection controls: 4 November 2026

Fictional local preview now includes suggested, confirmed and failed-save
scenarios with simulated local actions. Desktop, 390px and 320px layouts were
inspected. Confirm, override, remove and failed-save states were exercised;
mobile document widths equal viewport widths (no horizontal overflow). Browser
console had no errors. A status update during save exposed disabled controls
remaining stuck after re-render; fixed by rendering the completed save state
and retaining visible action feedback. A regression check now simulates a
re-render during the save. No real HA actions or provider requests were made.
This accepts the fictional control layout, not physical alerts or live deployment.

### Ten-minute work round: 4 November 2026, started 09:38 UTC

Added the pure station-time evidence contract and assessment foundation, documented
in [ADR 0009](adr/0009-confirmed-connection-evidence.md). The assessor verifies
confirmation, expected provider/service and station/event identities, provenance,
freshness and event plausibility before returning a numeric transfer margin.
Absent or unusable evidence produces unknown with a stable reason. This does
not add provider requests, arrival mappings, polling or live warnings.

Validation for this timeboxed slice: 53 focused connection/evidence tests passed;
seven dashboard tests passed. The broader network-disabled suite passed with
the existing early-termination expected failure; the loopback frontend test was
explicitly deselected (previously passed with approved local TCP access).
Compilation, repository Ruff, privacy scan, 56 local documentation links and
diff checks passed. No live HA changes, provider requests or release were made.

### Arrival-provider mapping round: 4 November 2026, started 09:51 UTC

Verified public provider fields through browser discovery and implemented the
[Railinfo arrival contract](RAILINFO_ARRIVAL_CONTRACT.md), conservative pure mapper
and broker-backed acquisition method. No scheduled/automatic caller is enabled.
Generic board/service clocks remain excluded; only explicit Darwin arrival
predictions with matched direct-service intent are accepted.

Validation: 88 focused Railinfo/arrival/evidence tests pass, including a mapped
arrival feeding a seven-minute transfer against a ten-minute allowance and
becoming unknown as the original observation ages. The broader network-disabled
suite passes with the existing early-termination expected failure; the local
TCP frontend test was explicitly deselected. Ruff, compilation, privacy scan,
59 local documentation links and diff checks pass. Finished around 09:58 UTC,
within the ten-minute limit. Public provider discovery used example stations;
no HA configuration, private itinerary or provider credentials were accessed.
No release or live monitoring activation occurred.

### Fifteen-minute monitoring round: 4 November 2026, started 09:59 UTC

Added a disabled-by-default Railinfo-only connection monitor, durable bounded
checkpoint claims, independent two-leg acquisition and dashboard margins with
evidence expiry. Confirmed incoming intent can remain relevant briefly after
booked arrival without changing operational leg selection. See the
[monitoring guide](CONNECTION_MONITORING.md) for exact daily/request limits,
catch-up/cooldown behaviour, unsupported cases and remaining acceptance gates.
At the end of that monitoring-only round, connection-risk announcements and
end-to-end recovery remained pending; see the later alert round below.

Monitoring validation includes durable claim restart/cooldown/day-cap tests,
failed-save pause without retry bursts, disabled/simulation/unsupported-provider
isolation, revocation during acquisition, two-leg risk acquisition, retained
incoming continuity and dashboard expiry/allowance-change behaviour. The latest
48 focused monitoring/review/retained-plan tests pass, plus seven dashboard tests.
A broader regression run is recorded below. No live HA configuration, release
or deployment was performed.

Final regression for this round passed with the existing early-termination
expected failure and the local-TCP frontend test explicitly deselected. Ruff,
compilation, privacy scan, 64 documentation links and diff checks pass. Work
finished around 10:13 UTC, within the requested 15-minute window. The monitoring
option remains off by default and no live installation was changed.

### Connection-alert round: 4 November 2026

The morning round was interrupted before its final validation result was retrieved.
Continuation started at 15:50 UTC with a fresh 15-minute cap. Added durable warning
transition claims, meaningful-change/recovery defaults and guarded delivery through
the existing announcement route. See [connection alerts](CONNECTION_ALERTS.md)
for policy, hand-off uncertainty, fallback and restart tradeoffs. The dashboard
retains a historical warning when current evidence becomes unknown. Monitoring
remains off by default and live notices respect the existing notification master.
No live installation has been modified.

Alert validation: 39 focused warning/delivery/monitor tests and nine Node
dashboard tests pass, including concurrent claim suppression, restart after an
uncertain hand-off, disabled/simulated/revoked contexts, storage failure, shared
route failure and timeout fallback. A broader network-disabled regression run
passes with the existing early-termination expected failure; the local-TCP
frontend test was explicitly deselected. Desktop and 390px/320px fictional
warning/recovery/stale layouts were reviewed with no horizontal overflow or
console errors. Ruff, compilation, privacy scan and documentation link checks
pass. GitHub still reports stable v0.2.13 on 4 November. Work finished around
16:00 UTC, within the continuation's 15-minute window. No release, real-device
announcement or live HA setting/restart was performed.

### Development-branch publication: 4 November 2026

Work is being consolidated on `development/rail-connections`, based on dashboard
commit `88ef3fd6c37bbf3bfca88f3069e5c0330e7ab5ad` (verified equal to the remote
dashboard head). This branch contains the connection/monitoring/alert slices and
public documentation updates. Validation now also runs on pushes to this dedicated
branch. Main, stable release tags and live HA remain unchanged. The pre-existing
untracked owner architecture brief is excluded from staging/publication.
Future reviewed slices should be committed and pushed incrementally, with test
evidence and documentation updated together rather than accumulating only locally.

### End-to-end route contract: 4 November 2026

Added a pure [recovery route contract](RECOVERY_ROUTE_CONTRACT.md) that rejects
interchange-only/partial routes, disconnected or unreachable transfers, stale
predictions, cancelled services and unsupported bounds. Context requires a
confirmed connected-journey endpoint and fresh evidenced origin; route identity
and prediction/allowance revision are separate. No search or adoption is exposed.
This slice is committed/pushed incrementally to development/rail-connections.

Validation for the route-contract slice: 27 focused recovery tests pass. The
broader network-disabled run passed 652 tests with the existing early-termination
expected failure; the local-TCP frontend test was explicitly deselected. Two
additional preference/wait-bound cases passed in the final focused run. Ruff,
privacy and documentation checks pass. Hosted validation of the preceding branch
commit was still queued; no hosted pass is implied. Search acquisition, adoption
and live journey acceptance remain pending.


## Development checkpoint — 6 November 2026

- Added one brokered Railinfo recovery query to the confirmed final destination,
  with bounded direct/one-change normalization and explicit unavailable outcomes.
  See [the recovery contract](RECOVERY_ROUTE_CONTRACT.md) for exact limitations.
- Reject stale origin context before querying; preserve provider observation age
  and recheck at completion. Reject ambiguous duplicate schedules even if one
  copy is cancelled. No new runtime caller or public recovery control is enabled.
- Full local regression: 683 passed, one existing expected failure, and the local
  TCP frontend-serving test deselected under local network restrictions. Lint,
  compilation and privacy scan pass. No physical journey acceptance is claimed.
- Investigated the previous GitHub failure: Python setup failed before tests
  because `ubuntu-latest` selected Ubuntu 26.04, without a Python 3.14.2 build.
  Pin the test job to Ubuntu 24.04, supported by the official
  [Python versions manifest](https://github.com/actions/python-versions/blob/main/versions-manifest.json).
  HACS and Hassfest had passed; the new run must establish the test outcome.
- Next: build the recovery request from confirmed connected bookings and an
  evidenced disruption or explicit user origin confirmation, then expose route
  review and revalidation before adoption. Broader changes remain a capability gap.
