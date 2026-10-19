# Setup and first journey

Journey Guardian assists with commuting bookings. Keep an independent alarm and
check station/operator advice while validating it. It cannot guarantee boarding,
identify every disruption, or automatically find a replacement train yet.

## 1. Install and configure

1. Back up Home Assistant. You need Home Assistant 2026.8 or newer.
2. In HACS, open its menu, choose **Custom repositories**, and add
   `https://github.com/stevesherry123/ha-uk-journey-guardian` as **Integration**.
   If it is already in the default catalogue, search for **UK Journey Guardian**
   instead. Download the latest release and restart Home Assistant.
3. Open **Settings > Devices & services > Add integration**, then select
   **UK Journey Guardian**. Only one integration entry is supported.
4. Select your existing calendar, person and home zone. Choose conservative
   preparation, station-arrival and access allowances. Provider credentials and
   destination zones are optional for calendar-only setup.
5. Open the integration's **Configure** options for later changes. Leave automatic
   rail checks, live notifications and the home wake-up alarm off initially.

Read [prerequisites](../PREREQUISITES.md) before enabling optional providers.
Railinfo is keyless; TransportAPI needs its own credentials and a suitable
budget. Google Routes is optional and can incur charges. Its fallback is not a
live traffic estimate.

## 2. Confirm the calendar and timing

Each booked train needs a separate timed event with both a departure and an
arrival time. Use a title such as:

```text
Rail operator - Example Central to Example Junction
```

Put the departure station in the event location. The ` to ` separator is
required. All-day trip summaries are ignored. Use your actual station names;
the example is fictional. Avoid duplicate copies of the same booking.

Press **Refresh calendar and timings** on the integration's device page. Check
**Next departure**, **Prepare at**, **Leave home at**, and **Station arrival at**.
For a 09:00 train, a 10-minute station buffer, 20-minute access allowance,
30-minute preparation buffer and 10-minute early warning produce:

```text
07:50 prepare ---- 08:30 leave ---- 08:50 station ---- 09:00 train
```

The default source refresh is daily. Change **Force calendar source refresh**
to suit your calendar; the refresh button always requests a source update.
Opening the calendar is not the intended refresh mechanism. An upstream feed
that has not published a booking cannot be repaired by refreshing HA.

## 3. Try a local simulation

In **Developer tools > Actions**, choose `journey_guardian.simulate_journey`:
use `on_time`, departure in `6` minutes and **Accelerated timeline** enabled.
Expect local preparation after one minute, leave after three, station after
five and active travel after six. Try delayed/cancelled scenarios separately.

Simulations bypass live calendar/provider work and never call the announcement
script. They do not prove phone/watch delivery or real-world cancellation
detection. They clear on restart. Afterwards call
`journey_guardian.clear_simulation` and confirm **Simulation active** is off.

## 4. Configure phone or watch delivery

Create a Text helper under **Settings > Devices & services > Helpers**. Set its
maximum length to **255**. Create a script that reads that helper and delivers
through your chosen notification route. For example, in a script's YAML editor:

```yaml
alias: Journey Guardian delivery
mode: queued
sequence:
  - action: notify.mobile_app_example_phone
    data:
      title: Journey Guardian
      message: "{{ states('input_text.journey_guardian_message') }}"
```

Replace both example entity/action names with your own. Select that helper and
script in Journey Guardian options. Automatic alerts write the helper and call
the script without message variables; reading the helper supports both automatic
alerts and manual briefings.

First put a harmless test message into the helper and run the script manually.
Then press **Travel review now**: it sends an actual briefing and can use live
provider allowance. This explicit request can deliver even with automatic live
notifications off. The full report is retained in HA's notification panel.
See [manual review](MANUAL_TRAVEL_REVIEW.md) for a response-only option.

Only after delivery works should you select **Enable live journey notifications**
and, if wanted, **Enable automatic live rail checkpoints**. A successful HA script call does not
prove that a phone or watch displayed or buzzed for every message; check the
device's own notification and Focus settings.

## 5. Enable the home wake-up alarm deliberately

The home-only repeating alarm needs live notifications enabled and the selected
person at the configured home zone. For phone/watch delivery, the helper/script
must also work. The default interval is six seconds, with a 15-minute safety
limit; the leave boundary can stop it sooner. Away from home, the normal three
preparation reminders remain in use.

Select an awake-evidence entity and the exact state meaning "awake" (default
`on`) if you want early acknowledgement. Journey Guardian does not independently
detect that you woke up. A helper used for acknowledgement must be reset before
the next alarm; a stale awake state can suppress it. Test the stop signal while
you are awake, and retain your independent alarm.

## 6. First travel day and upgrades

- Check the correct booking, leave time, healthy data and simulation-off state.
- Review live rail manually, then compare with the operator's information.
- Optional [station progress](STATION_PROGRESS.md) uses GPS, not railway evidence.
- After travel, review [arrival collection and the safety net](TRAVEL_DAY_REVIEW.md).
- Keep legacy automations until a real travel-day observation period succeeds.

For upgrades, back up HA, read the [changelog](../CHANGELOG.md), download the
release in HACS, then restart HA when convenient. Downloaded version and running
version can differ until restart. Verify the integration's running version and
device health afterwards. If a problem occurs, keep fallback alarms, capture
redacted diagnostics, and use HACS to select a previous release followed by a
restart; do not delete private integration storage as a troubleshooting shortcut.
