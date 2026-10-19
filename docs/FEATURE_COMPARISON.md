# Feature comparison: Journey Guardian and the legacy acceptance inventory

Reviewed against v0.2.6 on 19 October 2026. This is a capability map, not a
claim that every feature has completed real-world acceptance.

This is a comparison against the repository's documented legacy capability
inventory in `BACKLOG.md`; no private legacy configuration or personal routes
are included here. “Partial” means the building blocks exist but the behaviour
has not passed the required real-travel acceptance test.

| Capability | Journey Guardian now | Cutover position |
| --- | --- | --- |
| Timed calendar journey discovery and lifecycle | Implemented | Retain legacy until real-day validation |
| Conservative preparation, leave, and station arrival timing | Implemented | Validate against real travel |
| Repeating acknowledged wake-up alarm | Implemented with optional awake evidence | Validate watch delivery on a real travel morning |
| Station access by road, walking, cycling, or transit | Implemented, with CRS profiles | Validate configured profiles |
| Quota-aware rail checks | Implemented | Direct service validated; waypoint matching needs evidence |
| Direct service live status, delay, platform, calling point | Partial | Direct outbound test passed; provider mismatch remains for one return service |
| Post-departure delayed-service checks | One automatic check at +15 minutes while the journey remains current | Repeated follow-up until departure is not implemented |
| Split-journey interchange monitoring | Diagnostic helper only | Not ready for cutover |
| Meaningful-change notification deduplication | Implemented for persistent alerts and the shared script path | Physical delivery needs household acceptance |
| Mobile push, spoken announcements, wearables | Supported through a selected Home Assistant delivery script | Validate each household delivery script separately |
| Manual-review parity and failure explanation | Implemented in 0.2.2 | HA/watch script path available; validate the chosen delivery route |
| GPS progress and configured diversions | Implemented, including bounded post-booked-end retention | Proximity only; not boarding or actual railway arrival |
| Arrival evidence and nightly review | Railinfo collector and provider-free review implemented | Bounded attempts; not a complete ledger or operator-specific eligibility engine |
| Early termination and replacement service advice | Not implemented | Explicit open acceptance gap in the isolated rehearsal |
| Local destination transit comparison | Not implemented | Legacy remains required |
| Privacy-safe diagnostics and provider budgeting | Implemented | Continue observation |

## Notification preview and remaining work

Version 0.1.31 added an inactive notification preview builder. It produces the
planned journey-detected, wake-up, and leave-now sequence from an in-memory
snapshot only. It is not registered with Home Assistant, has no control, and
cannot deliver notifications.

The current live path selects a text helper and delivery script, uses explicit
opt-in, and keeps simulations local. The preview helper remains development-only,
not a screen in the integration. Further dedicated notification adapters need:

1. a dedicated harmless test-send control;
2. per-event preferences based on the event catalogue;
3. channel-specific deduplication, cooldowns, and superseding behaviour;
4. a preview screen before enablement; and
5. physical device acceptance alongside the existing isolated reload/failure tests.

Until those controls and real-travel acceptance are complete, Journey Guardian
should not be treated as a proven replacement for independent wake alarms or
manual operator checks. See the [setup guide](GETTING_STARTED.md) and
[isolated rehearsal](COMMUTE_REHEARSAL.md).
