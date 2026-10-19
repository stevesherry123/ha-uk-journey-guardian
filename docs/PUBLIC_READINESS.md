# Public-readiness review

Documentation reviewed on 19 October 2026 for v0.2.6. HACS catalogue acceptance
and product reliability are separate: a catalogue listing is not certification
of alarm delivery, compensation advice, or every provider's data quality.

## Documentation review result

Reviewed README, prerequisites, manual review, station progress, isolated
rehearsal, feature comparison, shadow tools, security/release policies, changelog,
backlog and the eight architecture decisions. Historical security findings and
older changelog entries are dated evidence, not current user instructions.
The unpublished architecture discussion draft is not part of the public guides.

Corrected misleading or stale claims:

- The provider action selects Railinfo or TransportAPI, not TransportAPI alone.
- The simulation clears on restart and cannot demonstrate phone/watch delivery.
- Live delivery already exists through a helper/script; dedicated adapters and
  per-event controls remain planned. Automatic alerts do not pass message variables.
- The automatic schedule has twelve checkpoints, not a four-request ceiling.
- GPS retention, booked-leg selection and railway arrival collection are distinct.
- Arrival collection is currently Railinfo-only with three bounded attempts.
- Quiet nightly reviews do not demonstrate complete coverage of all bookings.
- Manual review, Google routing and the HACS submission are no longer future work.

New guides cover [first setup](GETTING_STARTED.md),
[troubleshooting](TROUBLESHOOTING.md) and
[the nightly safety net](TRAVEL_DAY_REVIEW.md). Tests check local guide links and
the notification-script example. External provider terms can change; check the
linked official documentation and your account allowance before enabling them.

## Before recommending broad reliance

- Complete a fresh-install walkthrough with someone unfamiliar with the project.
  Documentation review and isolated tests do not substitute for this.
- Verify the declared minimum HA version (2026.8) as well as the current supported
  version. The pinned test environment is not a compatibility matrix.
- Complete a real direct/return travel day, physical phone/watch alarm and stop
  test, then an active-journey HA restart test. Keep fallback alarms throughout.
- Close the early-termination acceptance gap before advertising shortened-service
  detection or replacement-train advice. Do not infer cancellation from GPS.
- Strengthen retained live-rail state across restart and repeated post-departure
  follow-up. The current schedule is not continuous service tracking.
- Improve the per-journey safety-net view/export and whole-trip evidence before
  presenting it as comprehensive compensation assistance. Operator-specific
  policies, ticket-aware eligibility and claim submission are not implemented.
- Continue watching the existing [HACS submission](https://github.com/hacs/default/pull/11772)
  for maintainer feedback. Repository updates do not require a duplicate request.

These are release-confidence and feature-scope tasks, not grounds to withhold
already-tested maintenance fixes. Keep limitations prominent while they remain.
