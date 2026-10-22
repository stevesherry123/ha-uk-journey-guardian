/* Fictional examples only. No Home Assistant connection or personal data. */
export function previewData(scenario, now = Date.now()) {
  const base = scenario === 'overnight' ? Date.parse('2026-10-22T22:00:00Z') :
    scenario === 'clock-change' ? Date.parse('2026-10-25T00:00:00Z') : now;
  const at = minutes => new Date(base + minutes * 60000).toISOString();
  const allowance = scenario === 'constant' ? 60 : scenario === 'google' ? 40 : 30;
  const leave = 65 - allowance;
  const prepare = leave - 45;
  const disabled = scenario === 'disabled';
  const cancelled = scenario === 'cancelled';
  const awake = scenario === 'awake';
  const stale = scenario === 'stale';
  const eligibility = disabled ? 'disabled' : cancelled || stale ? 'suppressed' : 'conditional';
  const reason = disabled ? 'Live notifications are disabled' : cancelled ? 'Service is cancelled' : stale ? 'Journey data needs attention' : null;
  const dashboard = {
    schema_version: 1, checked_at: scenario === 'stale' ? at(-30) : at(0),
    healthy: scenario !== 'stale', simulation: false, phase: cancelled ? 'cancelled' : 'prepare_now',
    planned_delivery: 'announcement_engine', bookings_source: scenario === 'stale' ? 'retained_calendar' : 'calendar_only',
    journey: {
      origin: scenario === 'long' ? 'Example Central International Parkway and Interchange' : 'Example Central',
      destination: 'Sample Harbour', booked_departure: at(90), departure: at(90),
      booked_arrival: at(220), cancelled,
    },
    routing: {
      source: scenario === 'constant' ? 'configured_fallback' : scenario === 'google' ? 'google_routes' : 'waze_sensor',
      mode: 'driving', provider_minutes: scenario === 'constant' ? null : scenario === 'google' ? 40 : 20,
      applied_minutes: allowance, fallback_reason: scenario === 'google' ? 'waze_sensor_unavailable' :
        scenario === 'constant' ? 'waze_sensor_unavailable;google_routes_quota_exceeded' : null,
    },
    segments: [
      {label: 'Preparation', start: at(prepare), end: at(leave)},
      {label: 'Station access', start: at(leave), end: at(65)},
      {label: 'At station', start: at(65), end: at(90)},
      {label: 'Booked train', start: at(90), end: at(220)},
    ],
    notifications: [
      {
        kind: 'wake_alarm', label: 'Home wake-up', due_at: at(prepare),
        eligibility: awake ? 'suppressed' : eligibility,
        eligibility_reason: awake ? 'Awake evidence recorded' : reason,
        repeat_seconds: 6, maximum_minutes: 15,
        condition: 'While home, until awake evidence, safety limit or leave time',
      },
      {
        kind: 'leave_now', label: 'Leave for station', due_at: at(leave),
        eligibility, eligibility_reason: reason,
        condition: 'Subject to live state and deduplication',
      },
    ],
    checks: cancelled ? [] : [
      {kind: 'station_access', label: 'Station routing check', due_at: at(5), notification_promised: false},
      {kind: 'rail', label: 'Live rail check', due_at: at(15), notification_promised: false},
    ],
    latest_notification_record: awake ? {
      kind: 'wake_alarm', recorded_at: at(-5), receipt_confirmed: false,
    } : null,
    bookings: [{origin: 'Sample Harbour', destination: 'Example Central', booked_departure: at(600), booked_arrival: at(730)}],
    bookings_truncated: false,
  };
  if (scenario === 'empty') dashboard.journey = null;
  return {
    states: {'sensor.example_journey_status': {
      state: scenario === 'unavailable' ? 'unavailable' : 'planned', attributes: {dashboard},
    }},
    config: {time_zone: 'Europe/London'}, locale: {language: 'en-GB'},
  };
}
