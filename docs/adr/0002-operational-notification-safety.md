# ADR 0002: Operational notification safety

- Status: accepted
- Date: 2026-09-03
- Provenance: Journey Guardian shadow-mode acceptance testing

## Context

Journey Guardian must eventually replace time-sensitive legacy automations, but
an integration upgrade must not unexpectedly duplicate live travel alerts. Phase
transitions must occur at their calculated times rather than wait for the normal
poll interval, and Home Assistant restarts must not repeat an alert already sent.
Testing must not consume TransportAPI allowance.

## Decision

- Keep live-calendar notifications disabled by default until the user explicitly
  enables them in integration options.
- Allow simulation notifications while live notifications are disabled so the
  complete behavior can be accepted safely in shadow mode.
- Use Home Assistant-local persistent notifications for the first notification
  adapter. Mobile and announcement adapters remain deferred.
- Derive one operational phase from normalized journey timing and schedule only
  its remaining future boundaries with cancellable Home Assistant callbacks.
- Persist a bounded ledger of hashed source, departure, and phase fingerprints.
  Do not store journey summaries, locations, entity IDs, or notification targets.
- Provide an accelerated simulation timeline which bypasses calendar discovery,
  provider calls, and quota reservations.

## Consequences

- Upgrading does not enable alerts for real calendar journeys by itself.
- A refresh or restart can recover future boundary schedules without duplicating
  previously claimed notifications.
- Clearing a simulation immediately refreshes live state and cancels its timers.
- Persistent notifications prove the phase engine and deduplication before more
  invasive phone, speaker, or wearable adapters are introduced.
- Legacy automations remain active until live-provider and notification-adapter
  parity pass the cutover checklist and observation period.
