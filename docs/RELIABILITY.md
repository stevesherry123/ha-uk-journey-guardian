# Reliability and Acceptance

HACS catalogue inclusion is not certification of alarm delivery, compensation
advice or provider data quality. Match expectations to the installed release's
README, [feature comparison](FEATURE_COMPARISON.md) and changelog.

## Evidence boundaries

- Isolated rehearsals test integration logic, not physical phone/watch delivery,
  every live provider response or every real travel situation.
- A simulation does not establish that a live notification script will deliver.
  Test the selected delivery path and retain independent fallback alarms.
- GPS proximity is not boarding, actual railway arrival or evidence of service
  cancellation. Distinguish scheduled, predicted and confirmed observations.
- Provider budgets and bounded checkpoints are not continuous service tracking.
- A quiet nightly review does not establish that every booking was on time.
- Post-journey screening is not operator/ticket-specific compensation eligibility
  or an automatic claim submission service. Keep independent travel evidence.

See [arrival evidence](TRAVEL_DAY_REVIEW.md), [manual review](MANUAL_TRAVEL_REVIEW.md),
[station progress](STATION_PROGRESS.md) and
[isolated commute rehearsal](COMMUTE_REHEARSAL.md) for the specific current limits.
The rehearsal documents the early-termination acceptance gap explicitly.

## Before relying on a new setup or control path

1. Follow the public setup guide on a fresh installation using your own sources.
2. Test the declared-minimum HA version and any newer supported version affected
   by the change; one pinned environment is not a compatibility matrix.
3. Verify representative direct/return journeys, physical alarm delivery and stop
   behaviour, and an active-journey restart with fallback arrangements retained.
4. Validate provider evidence and all relevant split/interchange/cutover gates
   before disabling an existing independent workflow.
5. Review redacted diagnostics before sharing them. Never upload raw provider
   credentials, private storage, full HA logs or personal itinerary data.

Known limits and accepted release scope remain public. Internal review diaries
and administrative publication checklists are not user-facing guarantees.
