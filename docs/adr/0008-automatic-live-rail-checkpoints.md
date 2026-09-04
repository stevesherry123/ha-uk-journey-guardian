# ADR 0008: Automatic live-rail checkpoints

- Status: accepted
- Date: 2026-09-04
- Provenance: successful manual matching and user-approved legacy shadow cutover

## Context

Manual live checks proved the acquisition, station-resolution, calling-point, and
schedule-matching boundaries. Replacing the legacy packages requires unattended
checks, but unrestricted polling would risk the small daily provider allocation
and could repeat work after Home Assistant restarts or calendar synchronization.

## Decision

- Keep automatic provider use off by default and expose it as an explicit
  integration option.
- Schedule no more than four checks for the selected journey, approximately 150,
  90, 45, and 10 minutes before its calendar departure.
- Persist a privacy-safe hash of the journey departure and checkpoint before
  reserving provider allowance. A claimed checkpoint is not repeated after a
  reload, restart, reschedule, failure, or provider timeout.
- Catch up only when a checkpoint became due within the preceding 12 minutes.
  Older missed checkpoints are skipped rather than replayed.
- Treat the first three checkpoints as routine. Only the final ten-minute check
  may consume the configured urgent reserve.
- Continue to route Places and timetable requests through the shared broker and
  durable budget. Simulations and ordinary calendar reviews remain provider-free.
- Cancel and rebuild future callbacks whenever the selected coordinator journey
  changes, and verify the journey identity again immediately before acquisition.

## Consequences

- A normal journey uses at most four timetable requests plus any uncached station
  resolutions, without rapid polling.
- Late calendar synchronization can still obtain a useful recent checkpoint but
  cannot trigger a cascade of historical calls.
- A transient failure is not retried at the same checkpoint. The next planned
  checkpoint supplies the bounded eventual retry.
- Users must deliberately enable both automatic checks and live notifications if
  they want fully unattended provider monitoring and operational alerts.
