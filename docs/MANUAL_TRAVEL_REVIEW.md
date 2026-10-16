# Travel review now

Use the **Travel review now** button on the Journey Guardian device or call
`journey_guardian.travel_review_now` from a script, automation, or watch shortcut.
This is the successor to the legacy independent manual travel-review script.

An explicit review refreshes the selected calendar source and forces a fresh
station-access calculation using the configured traveller, travel modes, station
profiles, and provider credentials. Missing routing data retains the configured
fallback, which is identified in the report. A future departure within three
hours is checked through the selected rail provider and the existing shared
budget, cache, matching rules, and provider back-off. The urgent reserve is not
bypassed. Calls may be needed to resolve stations as well as retrieve a board.

For a departure further away, the report explains that live checking is deferred.
Once the effective departure time passes, it reports that the calendar journey
window is underway; it does not infer actual departure or boarding from the clock
or request an obsolete departure board. Destination arrival monitoring continues
under its existing collector. A retained observation is explicitly identified as
an earlier report, never a current confirmation. This action does not search for
replacement trains or change the current journey grouping model.

The briefing covers no journey in the configured 30-hour lookahead, unavailable
calendar, uncertain station or service matching, provider/timetable failures,
cancellation, delay, expected departure, platform when reported, and access/leave
timing. Labels omit the leading `zzz ` map-sort prefix. Provider exception text,
credentials, private entity IDs, and calendar descriptions are not rendered.

## Delivery

The full report replaces one local **Travel review** persistent notification.
A summary of at most 255 characters is passed through the configured announcement
script and helper. Scripts that accept a `message` variable receive it directly;
older scripts can still read the helper. Phone/watch delivery depends on that
script. If delivery fails or takes more than 20 seconds, the full local report
remains available. Automatic-notification preferences do not suppress an explicit
request; simulations never call a live announcement script.

Set `notify: false` for response-only use. The response includes `message`,
`summary`, `checked_at`, `status`, `rail_check`, `simulation_active`, `cached`,
and `delivery`. Reports include private journey names/times and should stay inside
the user's HA installation. They are not included in integration diagnostics.
Existing third-party announcement scripts remain responsible for their delivery
destinations and notification settings.

Completed results are reused for 30 seconds while the coordinator snapshot stays
the same. Repeated taps share provider work and deliver only once during that
window. A silent review can subsequently be delivered once by a normal request.
The provider/calendar stage times out after 60 seconds and gives an explanatory
response. Runtime caches clear on reload or restart.

## Existing watch script

To retain an existing watch shortcut calling a legacy script, keep that script's
entity ID and replace its sequence with:

```yaml
alias: Travel review now
mode: single
sequence:
  - action: journey_guardian.travel_review_now
```

The integration also exposes a native button with the same review behaviour.
Watch shortcuts configured as Companion custom events need an automation routing
that specific event to the action; a script does not itself subscribe to events.
