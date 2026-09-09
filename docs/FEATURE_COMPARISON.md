# Feature comparison: Journey Guardian and the legacy acceptance inventory

This is a comparison against the repository's documented legacy capability
inventory in `BACKLOG.md`; no private legacy configuration or personal routes
are included here. “Partial” means the building blocks exist but the behaviour
has not passed the required real-travel acceptance test.

| Capability | Journey Guardian now | Cutover position |
| --- | --- | --- |
| Timed calendar journey discovery and lifecycle | Implemented | Retain legacy until real-day validation |
| Conservative preparation, leave, and station arrival timing | Implemented | Validate against real travel |
| Repeating acknowledged wake-up alarm | Not implemented | Legacy remains required |
| Station access by road, walking, cycling, or transit | Implemented, with CRS profiles | Validate configured profiles |
| Quota-aware rail checks | Implemented | Direct service validated; waypoint matching needs evidence |
| Direct service live status, delay, platform, calling point | Partial | Direct outbound test passed; provider mismatch remains for one return service |
| Post-departure delayed-service checks | Implemented | Needs real journey validation |
| Split-journey interchange monitoring | Diagnostic helper only | Not ready for cutover |
| Meaningful-change notification deduplication | Implemented for local persistent alerts | Mobile delivery remains absent |
| Mobile push, spoken announcements, wearables | Not implemented | Legacy remains required |
| Manual-review parity and failure explanation | Partial | Needs no-journey, ambiguous, and provider-failure acceptance cases |
| Local destination transit comparison | Not implemented | Legacy remains required |
| Privacy-safe diagnostics and provider budgeting | Implemented | Continue observation |

## Notification next slice

Version 0.1.31 adds an inactive notification preview builder. It produces the
planned journey-detected, wake-up, and leave-now sequence from an in-memory
snapshot only. It is not registered with Home Assistant, has no control, and
cannot deliver notifications.

The next live-notification delivery change should be reviewed separately and
must include all of the following:

1. an explicit selection of a Home Assistant notify service rather than a
   hard-coded mobile target;
2. a test-send control that cannot send a journey detail;
3. per-event preferences based on the event catalogue;
4. channel-specific deduplication, cooldowns, and superseding behaviour;
5. a preview screen that shows what would be sent before enablement;
6. explicit live opt-in and a separate simulation path; and
7. end-to-end tests covering reload, restart, target failure, and disabled
   events.

Until those controls and real-travel acceptance are complete, Journey Guardian
is not a replacement for legacy mobile alerts, wake alarms, or manual checks.
