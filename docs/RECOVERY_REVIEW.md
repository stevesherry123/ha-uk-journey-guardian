# Recovery route review (development only)

Updated 8 November 2026. The development branch includes the Home Assistant
action and dashboard form for explicit Railinfo recovery review and selection.
Approval starts durable tracking for the selected replacement. The initial
tracking workflow uses on-demand live checks and user-confirmed arrivals.

1. Confirm each intended connection between separate rail calendar bookings.
2. With Railinfo selected and a current calendar review, open **Find another
   route** on the Journey Guardian card.
3. Choose the affected train and the final booked train in the connected journey.
   Enter the station name you can leave from now.
4. Select **Confirm station and find routes**. Review the predicted times,
   transfer allowance, expiry and affected bookings. Ticket acceptance is unknown.
5. Choose **Recheck this route** for an option you would consider. Journey
   Guardian makes a fresh Railinfo request and marks the route as rechecked if
   the trains, times and transfer requirements still match. Review and choose
   again if the result changes.
6. If the search cannot verify a complete route, check live departures or ask
   station staff about onward travel.

The equivalent Home Assistant action is `journey_guardian.review_recovery`.
It accepts `affected_booking_id`, `final_booking_id` and `origin` and returns a
status. The status sensor publishes the advisory result in its live `recovery`
attribute, which is excluded from Recorder. The card displays the live attribute.

This first version treats the traveller as ready at the named station when
they submit the action. It uses a maximum two-hour wait, eight-hour route
duration, five-minute evidence age and a calendar review at most 15 minutes old.
Only same-day direct or one-change Railinfo routes are supported. Affected
bookings must still be present in the current calendar response. Station names
and saved station defaults resolve through the existing station resolver before
one route query. An unresolved station or conflicting defaults stops the review.

## Intended flow and implemented boundaries

```mermaid
flowchart TD
    A[Explicit user request and confirmed recovery station] --> B[Rebuild exact booking context and search policy]
    B --> C{Current complete confirmed chain?}
    C -->|No| M[Manual fallback required]
    C -->|Yes| D[One brokered final-destination search]
    D --> E[Rebuild bookings, confirmations and preferences]
    E --> F{Context unchanged and unexpired?}
    F -->|No| M
    F -->|Yes| G[Revalidate every complete route with current time]
    G --> H{Fresh achievable options?}
    H -->|No| M
    H -->|Yes| I[Advisory route review and affected-booking preview]
    I -->|Explicit selection| J[Recheck exact route and show approval preview]
    J -->|Explicit approval| K[Track replacement while retaining booked baseline]
```

`RecoveryReviewController` implements B through H and an internal result for I.
The Home Assistant action and card implement A and I. Search acquisition follows
[the recovery route contract](RECOVERY_ROUTE_CONTRACT.md).

## State and ownership

The controller is scoped to one integration runtime. Its initial state is
`not_requested`. A dashboard read cannot trigger acquisition. Only the explicit recovery action calls `async_review`.
A second command during acquisition returns `search_in_progress` without
starting another query. Search parameters come from an immutable policy snapshot:
evidence age, initial wait, total duration, resolved transfer preferences and
global fallback. The Railinfo boundary still supports at most one change.

The inputs callback rebuilds the context from current calendar intent, exact
confirmations and preferences without provider I/O. Keep the original user-origin
confirmation timestamp unchanged; rebuilding is not a new location confirmation.
Read inputs before acquisition and again after it returns, including unsuccessful
searches. A changed scope or policy discards results. Revocation or unloading can
also call `invalidate`, preventing an in-flight result from restoring old options.

Before exposure, validate every route again against the complete final destination,
current time and captured policy. Do not mix routes from another journey, retain
only a partial route, or expose unrecognized provider status text. Successful
results remain advisory and preserve unknown ticket acceptance. The selection is an in-memory approval preview. Booking changes and
replacement tracking require a separate adoption action.

The context includes the entire original connected booking baseline and the
separate affected booking IDs. These are a future supersession preview; they do
not mark anything superseded. A replacement must still be explicitly chosen and
approved after a fresh whole-route check.

## Expiry, errors and manual fallback

`current()` rechecks context and policy, then removes expired options. It never
refreshes evidence or queries a provider. Expired options require a new explicit
review. Results are memory-only; restart begins with no reviewed options.

Unavailable, stale, incomplete and unsupported results carry
`manual_fallback=True`. The card explains the outcome and points to live departures or station staff. A no-complete-route response means no candidate
validated in that response; it does not establish that no route exists.

Timeouts and expected input/acquisition failures clear the review. Task
cancellation releases the in-flight guard and clears the searching state; it
cannot replay a previous successful result. Unexpected exceptions still propagate
for diagnosis, while cleanup clears the searching state. Unknown provider status
text is replaced with a stable invalid-response category.

## Validation and next steps

The local suite passed 739 tests with one existing expected failure, including
the local TCP frontend-serving test. Ten card tests passed. The fictional browser
preview verified the form, final destination and affected-leg display, and the
fallback at phone width. Live travel acceptance remains pending.

Scheduled replacement checks and live transfer warnings are the next milestone.
Provider-confirmed cancellation and early termination need a matched evidence
adapter. Routes with more than one change remain a provider capability gap.


## Rechecking a selected route

`journey_guardian.select_recovery` takes the `option_id` and `revision` from a
current option in the status sensor. The ID binds the booked journey and
services. The revision binds predicted times and transfer requirements.
The action skips the cached response and requires fresh provider evidence.
The broker may share an in-flight request for the same search.

The controller rebuilds current booking and preference context around the query.
A result that matches both identifiers is marked as rechecked in the live
preview. When times or services change, the card shows the refreshed options and
asks you to choose again. Expired options require a new review, and revocation
or unloading invalidates the preview. The rechecked option expires with its
route evidence or original recovery context, whichever expires first.


## Approve and track a replacement

Review the affected bookings and select **Approve and track this route** while
the rechecked option is current. Journey Guardian saves one replacement route
per integration entry and presents its current train under **Replacement tracking**.
Original calendar events remain available for comparison. The normal departure
and connection monitors skip the exact affected bookings while the replacement
record is current. Other bookings continue through the existing calendar flow.

Use **Check live train times** for matched Railinfo departure and arrival
predictions. The card labels approved times separately and drops expired
predictions. When you reach the displayed station, use **Confirm arrival** to
advance to the next train or complete the route. Progress survives Home Assistant
restart. A scheduled or predicted arrival alone never advances the route.

**Stop replacement tracking** stops the replacement and resumes normal calendar
selection. A completed or stopped route can be replaced by another explicit
approval. Records expire eight hours after the approved final arrival. The
initial tracking version uses one active route, at most two legs, and no
automatic replacement announcements. Ticket acceptance remains unknown.
