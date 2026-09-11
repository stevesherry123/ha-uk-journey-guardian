# Prerequisites

UK Journey Guardian is designed to be configured entirely through Home
Assistant. Never add API keys, addresses, calendar exports, entity IDs, or
notification targets to this repository or an issue report.

## Required Home Assistant components

- Home Assistant 2026.8 or newer
- HACS for update management during the alpha period
- one calendar entity containing timed journey events
- one person entity with a usable location source
- a home zone
- at least one notification route before operational alerts are enabled

Destination zones and customised announcement scripts are optional. The setup
health check will identify unavailable optional features without preventing the
core calendar review from running.

Each traveller selects two independent safety margins:

- **preparation buffer** — time to get ready before leaving the current location
- **station buffer** — time to arrive before the scheduled rail departure

They can also edit an **early-warning margin** and a conservative
**station-access fallback**. The fallback is used when Google Routes is not
configured or cannot return a trustworthy route and is always labelled as
inferred in Journey Guardian entities.

They also select a default station-access mode: automatic, walking, driving, or
cycling. These settings remain in Home Assistant and are not published.
Automatic mode uses driving while the traveller is home and public transport
while away. Live routing also requires a restricted Google Routes API key.

## Calendar source

[TripIt](https://www.tripit.com/) is the preferred source used during development.
Its free plan supports itinerary organisation and calendar synchronisation.

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

Create a TransportAPI developer account and obtain the `app_id` and `app_key`
for an application. The free plan currently advertises 30 calls per day, so the
integration enforces a daily budget and preserves an urgent reserve.

- [TransportAPI signup](https://developer.transportapi.com/signup)
- [TransportAPI developer portal](https://developer.transportapi.com/)
- [TransportAPI rail documentation](https://developer.transportapi.com/docs)

The credentials are entered into Home Assistant's integration setup when the
manual live-rail check is required; they can be deferred during calendar-only
setup. They must not be placed in YAML examples, source files, logs, screenshots,
or issue reports.

## Walking and road estimates

Create a Google Cloud project, enable billing and the **Routes API**, then create
a dedicated API key for UK Journey Guardian. The integration will use Compute
Routes for walking, cycling, and road duration/distance estimates. This includes
the home-to-station leg when the traveller chooses to walk.

- [Set up the Routes API](https://developers.google.com/maps/documentation/routes/get-api-key)
- [Compute Routes documentation](https://developers.google.com/maps/documentation/routes/compute_route_directions)
- [Routes API usage and billing](https://developers.google.com/maps/documentation/routes/usage-and-billing)
- [Google Maps Platform key-security guidance](https://developers.google.com/maps/api-security-best-practices)

Restrict the key to the Routes API. Where the Home Assistant host has a stable
public egress address, also apply an IP-address application restriction. Set a
Google Cloud quota appropriate for the household's expected usage and budget.

## Notifications and customised Home Assistant elements

Operational alerts require a configured notification route. The public
integration will not hard-code private service or entity names. Instead, it will
support adapters for:

- Home Assistant Companion App notifications
- a user-selected notification action or script
- an optional text-to-speech or announcement script
- an optional wearable/manual-review trigger

Existing customised scripts must accept plain title/message inputs or be wrapped
by a small local adapter. Their names and implementation stay solely within the
user's Home Assistant installation.

## Destination profiles

The planned profile model supports any number of destinations. Each profile can
contain a private display label, rail station name/code, optional zone, final
waypoint, travel-mode preferences, buffer time, and notification adapter. These
values are stored in Home Assistant and redacted from diagnostics.

## Affiliate links

No verified public affiliate or referral programmes were found for the required
services at the time this guide was written, so all links above are direct
official links. If an affiliate programme is used later, the relationship and
link will be clearly disclosed.
