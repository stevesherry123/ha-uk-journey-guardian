# Arrival evidence and the nightly safety net

The safety net flags journeys needing attention; it is not a compensation
decision, a complete journey ledger, or an automatic claim submission service.

## What is collected

The arrival collector currently supports **matched Railinfo services only**.
It needs a non-cancelled live service match with a service identity, destination
code, and a timed calendar end. Merely having a calendar event is not enough.
Use automatic rail checks or an eligible explicit rail review to obtain a match.
TransportAPI departure checks do not activate this Railinfo arrival collector.

After the booked arrival, the collector checks destination movement data at
approximately **+5, +20 and +60 minutes**, stopping after a confirmed match or
three unsuccessful attempts. Matching requires an actual railway arrival for
the saved service identity/date; GPS proximity does not count. Pending collection
is saved locally for restart recovery, subject to a 12-hour recovery window.
Provider failures, missing movements or delays beyond these attempts can leave
the outcome unresolved. Collection is not unlimited tracking.

## What runs overnight

At **04:00 in Home Assistant's configured local time**, the integration reviews
the preceding calendar day's saved evidence without making new rail API calls.
A startup after 04:00 can recover the previous day's missed review. This is not
an arbitrary historical backfill or a rolling 24-hour window. Overnight travel
can have evidence collected after the review; a final correction is not guaranteed.

| Evidence | Review meaning |
| --- | --- |
| Confirmed arrival at or above the configured threshold | Possible claim requiring human review |
| Confirmed late arrival below the threshold | Delay observed, no threshold flag |
| Confirmed on-time arrival | No observed arrival delay |
| Provider cancellation evidence | Possible claim requiring human review |
| No trustworthy actual arrival or failed latest evidence | Unresolved, not confirmed on time |

The default threshold is **15 minutes**, editable in integration options. It is
one user-selected screening threshold, not an operator-specific policy engine.
Cancellation does not automatically establish a full refund: the applicable
ticket, operator policy, whether travel was completed and the final arrival
matter. Check the operator's current rules yourself. Departure delay is recorded
separately and does not establish the final destination delay.

## What you see

HA creates a **UK Journey Guardian nightly review** persistent notification only
when saved journeys include possible claims or unresolved outcomes. It gives
aggregate counts, not a complete station-by-station evidence pack. It does not
currently send that report through the phone/watch script.

No notification can mean no saved evidence, completed journeys below the
threshold, or that the review has not run. **Silence does not prove every booked
journey was on time.** Downloaded integration diagnostics include aggregate
`last_travel_day_review` counts and redacted recent-check outcomes. A dedicated
per-journey report/export screen is not implemented.

## Known limits and your next action

- Early termination can currently appear as an unmatched service, not a
  cancellation. Replacement-train search and automatic recovery are not ready.
- Separate bookings are separate evidence groups, not a ticket-aware whole-trip
  compensation assessment. Missed-connection entitlement is not calculated.
- The history is bounded to the latest 250 check records, not indefinite storage.
- Local evidence stores include station codes and journey times; protect HA
  backups. Public diagnostics remove identifying journey details, but should
  still be checked before sharing. Do not upload raw storage or full HA logs.

For any disruption, keep tickets, actual arrival details and operator evidence
independently. Follow the operator's claim process and deadline. The integration
does not submit claims, store payment details, or guarantee eligibility.
