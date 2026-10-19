# Prerequisites

UK Journey Guardian is designed to be configured entirely through Home
Assistant. Never add API keys, addresses, calendar exports, entity IDs, or
notification targets to this repository or an issue report.

## Required Home Assistant components

- Home Assistant 2026.8 or newer
- HACS for installation and update management
- one calendar entity containing timed journey events
- one person entity with a usable location source
- a home zone
- a tested delivery script before phone/watch alerts are relied upon

Destination zones and announcement scripts are optional. Calendar review works
without a script; notifications then stay inside Home Assistant. A healthy
calendar result does not prove that routing, live rail, or watch delivery works.

Each traveller selects two independent safety margins:

- **preparation buffer** — time to get ready before leaving the current location
- **station buffer** — time to arrive before the scheduled rail departure

They can also edit an **early-warning margin** and a conservative
**station-access fallback**. The fallback is used when Google Routes is not
configured or cannot return a trustworthy route and is always labelled as
inferred in Journey Guardian entities.

They also select a default station-access mode: automatic, walking, driving,
cycling, or public transport. Settings remain in Home Assistant and are not
published.
Automatic mode uses driving while the traveller is home and public transport
while away. Live routing also requires a restricted Google Routes API key.

## Calendar source

[TripIt](https://www.tripit.com/) is the preferred source used during development.
Configure its calendar feed as a Home Assistant calendar before selecting it in
Journey Guardian. Keep the feed URL private: it can grant access to itinerary data.

- [TripIt getting started](https://help.tripit.com/en/support/solutions/articles/103000063304-getting-started)
- [TripIt calendar-feed setup](https://help.tripit.com/en/support/solutions/articles/103000063280-calendar-feed-setup-and-sync)
- [Home Assistant calendar documentation](https://www.home-assistant.io/integrations/calendar/)

The integration expects each journey leg to be a timed event with an `Origin to
Destination` title. An optional operator prefix ending in ` - ` is supported.
The departure station should also be placed in the event location when possible.
All-day trip-summary events are ignored.

## UK rail information

Choose one live rail provider in the integration options. Railinfo is keyless
and is the simplest option for personal use; it uses a separate fair-use limit
and does not decrement the TransportAPI budget entity.

- [Railinfo developer information](https://railinfo.uk/developers)

If choosing TransportAPI instead, create a developer account and obtain the
`app_id` and `app_key` for an application. Its developer portal advertises a free
30-hit daily plan as checked on 19 October 2026; check your account's current
terms and allowance. The integration enforces its configured budget and urgent
reserve. Railinfo does not require a TransportAPI account.

- [TransportAPI signup](https://developer.transportapi.com/signup)
- [TransportAPI developer portal](https://developer.transportapi.com/)
- [TransportAPI rail documentation](https://developer.transportapi.com/docs)

The credentials are entered into Home Assistant's integration setup when the
manual live-rail check is required; they can be deferred during calendar-only
setup. They must not be placed in YAML examples, source files, logs, screenshots,
or issue reports.

## Walking and road estimates

Create a Google Cloud project, enable billing and the **Routes API**, then create
a dedicated API key for UK Journey Guardian. The integration uses Compute
Routes for walking, cycling, road, and public-transport estimates. This includes
the home-to-station leg when the traveller chooses to walk.

- [Set up the Routes API](https://developers.google.com/maps/documentation/routes/get-api-key)
- [Compute Routes documentation](https://developers.google.com/maps/documentation/routes/compute_route_directions)
- [Routes API usage and billing](https://developers.google.com/maps/documentation/routes/usage-and-billing)
- [Google Maps Platform key-security guidance](https://developers.google.com/maps/api-security-best-practices)

Restrict the key to the Routes API. Where the Home Assistant host has a stable
public egress address, also apply an IP-address application restriction. Set a
Google Cloud quota appropriate for the household's expected usage and budget.

## Notifications and customised Home Assistant elements

The current delivery route uses a selected Text helper (`input_text`, maximum
length 255) and a selected script. Journey Guardian writes the message to that
helper before calling the script. The script should read the helper; automatic
alerts do not supply title/message variables. Manual review also supplies a
`message` variable, but the helper-based contract works for both paths.

The script can deliver through the Companion App, an existing announcement
system, or another chosen route. Dedicated mobile adapters and per-event
preferences are future work. See the [setup guide](docs/GETTING_STARTED.md) for
an example and a safe test sequence. Delivery destinations remain private.

## Destination profiles

Current options support multiple destination zones and CRS-based station-access
mode overrides. The richer per-destination profile model, including separate
buffers, final waypoints and delivery preferences, is planned, not implemented.

## Data sent to providers

Rail checks send station identifiers and journey dates/times to the selected
rail provider. Optional Google routing sends the traveller's current coordinates,
station destination and travel timing to Google. Disabling live routing avoids
those Google requests and uses conservative timing instead. Local entity states,
notifications, history and backups may still contain private journey details;
redacted diagnostics do not make those other records anonymous.
