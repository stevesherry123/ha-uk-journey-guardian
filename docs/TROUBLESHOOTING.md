# Troubleshooting

Keep an independent alarm and consult official travel information if a result is
uncertain. Do not reset budgets, delete storage, or disable safeguards to force
provider calls.

| Symptom | Check |
| --- | --- |
| No upcoming journey | Correct source calendar, timed start/end, `Origin to Destination` title, 30-hour lookahead, no active simulation. Press **Refresh calendar and timings**. |
| Booking still missing after refresh | Inspect HA's calendar. If absent there, compare the private upstream feed with its source itinerary. Journey Guardian cannot import unpublished events. Never post a feed URL publicly. |
| Data health on but no live rail | Health is not proof of every feature. Check **Rail data freshness**, **Check live rail now**, selected provider, credentials and budget. Automatic checks are opt-in. |
| Rail status says retained or historical | This is an earlier observation, not a new railway confirmation. Check the last successful live time/error on **Status**. |
| Service missing or ambiguous | Verify station names/codes, event time and operator evidence. Do not widen matching or assume cancellation merely because a service is absent. Early termination remains a known gap. |
| TransportAPI allowance exhausted | Check other users of the same account. The entity cannot count all external consumers. Wait for the provider's reset; do not clear the stored budget. |
| Railinfo timeout or rate limit | Keep conservative timing and allow back-off. Repeated manual taps do not bypass limits. |
| Routing shows fallback or error | Verify selected mode, location, station resolution, Google key/API restrictions and quota. **Test station route now** forces an optional Google request; it can incur usage. |
| No watch alert | Check live-notification opt-in for automatic alerts, selected helper/script, helper maximum 255, and the phone/watch's delivery settings. Manually test a harmless message through the script. Local simulation never buzzes the watch. |
| Wake alarm absent or stops early | Check person/home state, alarm opt-in, awake entity/state, prepare/leave times, safety limit and **Status** attributes beginning `home_wake_`. No independent awake detection exists. |
| Station progress unknown/stale | Check ordered zones, endpoint names, real GPS source, fix age/accuracy and overlapping zones. Missing fixes are not invented. See [station progress](STATION_PROGRESS.md). |
| No nightly report | Read the [safety-net guide](TRAVEL_DAY_REVIEW.md). It only alerts on saved possible claims or unresolved outcomes; no report is not proof of punctuality. |
| HACS shows a newer version than HA | Downloaded files take effect after an HA restart. Check the running integration version afterwards. |

## A useful support report

### Sustained failures in Repairs

From v0.2.9, calendar/source-refresh, routing and live-rail failures can create
an explanatory notice in **Settings > System > Repairs** after at least three
distinct failed checks and a 30-minute failure window. This makes no extra
provider requests. Repeated reads of one retained rail/source error do not count
as fresh failed attempts. Notices clear after a genuinely successful corresponding
check; simulation does not create or clear real notices. Unload/reload clears
the notices and starts a new observation window. These are explanatory notices,
not an automatic credential repair or a guarantee that every outage is detected.

The **Station access routing** error now distinguishes `invalid_request`,
`authentication_failed`, `permission_denied`, `endpoint_unavailable`,
`quota_exceeded`, `timeout`, `provider_unavailable` and malformed responses, with
the `google_routes_` prefix. Google response text and credentials are not shown.
For denied access, check the Routes API, key restrictions, billing and quota in
your own Google project; the category alone does not prove which setting failed.
Conservative fallback timing remains in use until a route succeeds.

The Status attribute `last_successful_calendar_review_at` records successful
calendar reads since startup, not proof of a successful upstream feed refresh.
Inspect the separate source-refresh time/error attributes for that.

Include the integration version, HA version, expected behaviour, what happened,
approximate stage (preparation, departure or arrival), selected provider, and
stable error category. State whether a simulation was active and whether the
issue survives a normal restart. Use fictional examples rather than real routes.

Download diagnostics from the integration entry's menu in **Settings > Devices &
services**, and inspect them before sharing. Do not attach raw configuration
entries, private calendar feeds, full HA logs, backups, credentials, station
history or screenshots containing private travel data to a public issue.
For security concerns, follow [the security policy](../SECURITY.md).
