# Booked connection controls (unreleased development)

These actions are implemented locally and are not in stable v0.2.13. They save
explicit booking-pair confirmation. Monitoring and warnings require their
separate opt-in settings; recurring templates and recovery searches remain pending.

In the development dashboard, use the Booked connections section to confirm a
suggestion, optionally enter a whole-minute allowance, or remove confirmation.
Controls are hidden in simulation and confirmation is disabled when the current
review is unhealthy or confirmation storage could not be loaded. The backend
revalidates every action. For direct action access, after a healthy real calendar
review, inspect the Status entity's
`retained_booked_legs` attribute and identify the two `booking_id` values.
In Home Assistant Developer Tools → Actions, use
`journey_guardian.confirm_connection` with `inbound_id` and `outbound_id`.
An optional `override_minutes` saves the pair-specific allowance (0–1440 minutes).
Omit it when confirming again to clear that pair's saved override. Station/global
preferences are available in the development options form.

The bookings must be adjacent in the current calendar response, connect at the
same station name, have non-overlapping booked times, and have an onward departure
in the future. The incoming booking needs a booked arrival time. Unsupported or
changed pairs are rejected. Cross-station transfers require later design work.
Simulation cannot change real confirmations. Confirmation is not evidence of a
shared ticket, guaranteed transfer or railway arrival.

Use `journey_guardian.revoke_connection` with the same IDs to remove confirmation.
This also works for an old pair after a calendar edit. Both actions return a
`confirmed` boolean when a service response is requested. A failed write raises
an error; it does not commit the change in memory. Each confirmation expires with
the onward booking's existing bounded retained-intent expiry. Confirmations have
no automatic provider calls, background tasks or announcement side effects.

Original calendar events are preserved. A booking edit changes its exact identity
and therefore requires confirmation of the new pair. Retained old records may
remain for evidence, but cannot be confirmed as current connections when absent
from the latest response. The development dashboard shows candidate connections with Confirm connection,
Save allowance and Remove confirmation controls. It displays saved confirmation
status and reports failed saves. Confirmation remains separate from live risk;
no prediction or warning is implied by a confirmed connection.

## Transfer defaults

In the integration's Configure/options form, set **Default connection transfer
allowance** (initially 10 minutes) and optionally **Station transfer allowances**.
Use one exact station display name per line, for example:

```text
Example Junction=15
Sample Harbour=12
```

Names match case-insensitively with whitespace normalized; the optional `zzz `
zone display prefix is ignored. Use the station name shown in the booking, not
a station code or fuzzy alias. Duplicate normalized names and values outside
0–1440 whole minutes are rejected. A zero-minute preference is permitted but
provides no transfer buffer. These values are your preferences, not official
minimum interchange times or guarantees.

The dashboard labels the applied source: this connection, station default, or
global fallback. A booked-pair override wins over station and global settings.
To clear an override, leave its dashboard input blank and save the allowance.
Saving options uses the existing integration reload flow; schedule changes
outside active travel or wake alarms. These settings do not change home-to-station
routing or preparation buffers. Connection monitoring and warnings require the
separate opt-in monitoring and live-notification settings.

## Connection-risk development status

A local evidence assessor now defines how fresh incoming arrival and onward
departure observations will produce risk and margin. It deliberately returns
unknown for stale, missing, retained or timetable-only evidence. The existing
departure prediction can be mapped without refreshing its original timestamp.
An opt-in development scheduler now uses verified arrival/departure mappings;
see [bounded monitoring](CONNECTION_MONITORING.md). Confirmation alone does not
enable it. See [connection warnings](CONNECTION_ALERTS.md) for the live-notification
setting, suppression policy and delivery limits.
