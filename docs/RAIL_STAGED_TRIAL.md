# Staged rail trial

The v0.3.0-beta.12 staging build supports user-directed, same-day Railinfo
recovery with direct or one-change routes. Each calendar connection and any
replacement require explicit approval. Automatic cancellation and early
termination recovery still need provider acceptance. The separate flight
preview is outside the trial scope.

## Install and rollback rehearsal

1. Record the installed version, integration settings and alert target. Take a
   Home Assistant backup and keep the existing alarms enabled.
2. In a separate test instance, check a fresh install and an upgrade from
   v0.2.13. Where beta.10 is in use, also upgrade a copy of that instance.
   Confirm that settings and previously supported journeys load.
3. Enable connection monitoring for the trial profile. Verify one test
   announcement on the chosen device. Record the handoff and actual device
   receipt separately.
4. Reinstall the prior build or restore the pre-trial backup, restart Home
   Assistant, and verify the previous settings and direct journey workflow.
   Use the backup if the prior version cannot read data written by the beta.

## Direct and split travel checks

1. For a direct outbound and return, check that the correct bookings are
   selected, the preparation and leave windows are sensible, and the alert
   reaches the chosen device.
2. For a split trip, confirm the connection between the two calendar events.
   Check the source of the transfer allowance and set a per-connection override.
3. Use a controlled delay replay if disruption does not occur during travel.
   Confirm that a below-allowance prediction triggers an announcement and
   persistent dashboard warning, and an unchanged prediction does not repeat it.
4. Request recovery from the confirmed current station. Verify that each option
   reaches the final booked destination, recheck the selected option, and approve
   it explicitly. Reload the integration, verify tracking survives, confirm each
   arrival, and check that the original booking and unrelated return remain.
5. Replay a wrong station, missing onward booking and unavailable provider.
   Check that the dashboard explains the issue and that uncertain evidence cannot
   adopt a timetable interpretation or replacement.

Record the build SHA, trip or fixture type, expected and observed results, and
any alert timestamps or failure. Keep personal routes and identifiers out of
shared logs. Staging is complete after the install and rollback rehearsal.
Release-candidate promotion also requires field observation and agreement on
the cancellation and early-termination acceptance scope.
