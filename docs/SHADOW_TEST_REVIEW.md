# Shadow-test review tools

These tools are intentionally not wired into the Home Assistant integration.
They let us review a real journey after the fact without changing its live
decisions.

## Notification timeline preview

`notification_preview.build_notification_preview(snapshot)` returns the nominal
journey-detected, wake-up, and leave-now sequence as read-only data. It does not
register a timer, call a notify service, create a persistent notification, or
change a coordinator state. A future UI can safely use it to show a traveller
what would happen before notification delivery is enabled.

## Rail replay

`scripts/replay_rail_match.py` accepts a locally saved TransportAPI station-board
JSON response and prints only a sanitized match result. It is useful when a
diagnostic record reports `rail_schedule_mismatch`: replaying the board reveals
whether the candidate was early, late, or accepted, without calling a provider.

## Connection assessment

`connection.assess_connection` is a pure planning helper for a future split-leg
feature. It classifies a predicted inbound arrival against the next departure as
`viable`, `at_risk`, or `missed`; it currently has no Home Assistant entities,
notifications, or side effects.

## Diagnostic explanation

`diagnostic_explainer.explain_live_checks` converts sanitized check-history
records into short review notes. It is deliberately kept out of the live
notification path until its advice and wording are validated in shadow tests.
