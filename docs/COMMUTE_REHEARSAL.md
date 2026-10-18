# Isolated Commute Rehearsal

`tests/test_commute_rehearsal.py` loads the real integration into Home
Assistant's isolated test instance. It is not the live simulation action and
does not connect to an installed Home Assistant server.

## Boundaries

Real code runs for config-entry setup/unload, all entity platforms, the
coordinator and engine, provider parsing and request broker, notification and
rail timers, GPS progress, storage APIs, arrival collection and nightly review.

Only these inputs/outputs are fictional:

- Calendar source service responses and upstream-refresh acknowledgement.
- Railinfo and Google Routes HTTP responses at the clients' session boundary.
- Person, device-tracker, zone and awake-evidence states.
- The final announcement script, which captures messages rather than delivering
  them to a mobile device. The text helper is a real HA helper with its 255
  character limit, and persistent notifications run inside the test instance.
- Clock advancement and wake-loop sleeping. Six-second intervals are logical
  test-clock intervals, not a measurement of phone/watch delivery latency.

The simulated bookings and coordinates are generic. Tests cannot establish
whether a live provider returns an equivalent early-termination response, or
whether mobile operating systems deliver every notification or GPS fix.

## Coverage

- Calendar-driven preparation, repeating home wake-up and leave-now timing.
- Ten wake deliveries at logical six-second intervals, including an integration
  reload while the alarm is ringing; awake evidence ends the loop.
- Leave-time and safety-limit termination without awake evidence.
- The three-reminder away pattern, including simultaneous periodic refresh and
  reminder boundaries, reloads, and duplicate prevention.
- On-time, seven-minute-late and eighteen-minute-late destination arrivals,
  the fifteen-minute possible-claim threshold, and quiet below-threshold review.
- Separate outbound/return evidence and review grouping.
- GPS diversion selection, unavailable/inaccurate/stale fixes, calendar outage,
  post-booked-end monitoring and persisted-state recovery.
- Provider timeout and HTTP 429 recovery without repeated startup requests.
- Live station-access estimate parsing, forced route-button checks, conservative
  fallback during a route-provider outage, and recovery.
- Cancellation reporting, announcement failure/local fallback, and actual
  button-service delivery with repeated-tap suppression.
- Provider-free nightly review and reload without repeating a completed review.

Reload tests reconstruct the integration runtime against HA's mock persistent
storage. They are not a full OS reboot or a fresh Home Assistant process test.

## Open Acceptance Case

The shortened-service scenario is an explicit expected failure: a response
ending before the booked destination is rejected as an unmatched service, not
turned into a definitive early-termination cancellation/recovery workflow.
Its nightly review is unresolved, with no invented destination arrival.

Only the dedicated `EarlyTerminationAcceptanceGap` exception is expected.
Other errors in that test fail normally; a future passing acceptance case also
requires updating its strict expected-failure marker. Do not count it as a pass.
Reliable provider evidence and a bounded recovery-search design remain required.

## Run

Install the repository's pinned test dependencies, then run:

```sh
pytest tests/test_commute_rehearsal.py --disable-socket --allow-unix-socket --timeout=30
```

The socket guard blocks IP networking; Unix sockets are allowed for the local
test event loop. CI runs this guarded rehearsal in addition to the full suite.

To retain fictional message, request and timeline evidence in a local directory:

```sh
JG_REHEARSAL_OUTPUT=/tmp/commute-rehearsal pytest tests/test_commute_rehearsal.py \
  --disable-socket --allow-unix-socket --timeout=30 \
  --junitxml=/tmp/commute-rehearsal/results.xml
```

Artifacts are generated only when that environment variable is supplied. The
reporting directory is not part of HA runtime configuration or a public upload.
