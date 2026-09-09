# Shadow-test review tools

These tools are intentionally not wired into the Home Assistant integration.
They let us review a real journey after the fact without changing its live
decisions.

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
