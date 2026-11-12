# Confirmed connection monitoring (unreleased development)

This feature exists locally on the development branch. It is not in stable
v0.2.13 and has not been installed or accepted on live journeys.

## Enable deliberately

Select Railinfo as the rail provider. Confirm the intended booking pair using
[connection controls](CONNECTION_CONTROLS.md), then enable **Monitor confirmed
connections (development)** in integration options. It defaults to off. Options
use the existing integration reload flow, so make changes outside active travel
or wake alarms. Other rail providers do not activate this monitor.

The dashboard shows an evidence-backed connection margin when both services can
be matched and fresh explicit predictions are available. It shows unknown when
required evidence is unavailable, stale or unsupported. Fresh risk transitions
can now use the existing live-announcement route when live notifications are
enabled; see [warning policy and delivery history](CONNECTION_ALERTS.md).

## Bounds and provider use

- One pending timer per integration entry, with no parallel connection evaluation.
- Candidate checkpoints: incoming booked arrival minus 15 and 5 minutes, plus
  5 minutes; onward booked departure minus 2 minutes and plus 5 minutes.
- Checkpoints are restricted to the bounded interchange window. Only the most
  recent checkpoint within a two-minute catch-up window can run after reload.
- At most eight connection evaluations per local day across confirmed pairs,
  with at least five minutes between evaluations. Claims are saved before work.
  Provider/storage failures also consume their successfully claimed slot.
- A failed claim save pauses further claims until successful ledger reload,
  preventing an immediate retry loop. An unreadable ledger never authorizes work.
- One evaluation uses up to four journey requests (matching and prediction for
  each leg), plus up to four station lookups on a cold resolution cache. Shared
  broker caching can reduce these; they do not consume TransportAPI credits.
  The cap applies to this connection monitor, not all other integration traffic.
- Five-minute evidence freshness is the initial development policy. Original
  broker observation timestamps are preserved; cached/restarted data is not
  relabelled fresh. An elapsed prediction also expires the displayed margin.

## Continuity and uncertainty

An already confirmed incoming leg can remain relevant after its booked arrival
when it leaves the upcoming calendar list. Its retained identity can be monitored
while the onward booking is still available, until a bounded maximum of 15 minutes
past onward booked departure. Changed/revoked pairs and simulation are rechecked
before acquisition and before publishing a result. Missing calendar availability
suspends monitoring; it does not prove cancellation.

The selected operational journey, preparation times and calendar bookings are
not changed by connection checks. A negative predicted margin means at risk,
not confirmed missed. No full-day recovery, automatic route adoption or guaranteed
connection is supplied by this development slice.

Predictions use the [conservative Railinfo contract](RAILINFO_ARRIVAL_CONTRACT.md):
strict matched service/date/endpoints/schedule, explicit Darwin times, no inferred
arrival from departure delay. Previous-operating-day queries after midnight,
ambiguous clock-change times, timetable fallback and shortened-service records
may therefore remain unknown. Live acceptance and richer disruption handling
are still required before release.
