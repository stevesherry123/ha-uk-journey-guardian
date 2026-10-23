import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFlights, flightLocalTime} from './journey-guardian-card.js';

test('flight data is opt-in and never read from the rail entity contract',()=>{
  const config={entity:'sensor.example_flights'};
  const data={schema_version:1,source:'calendar_only'};
  const hass=state=>({states:{[config.entity]:{state,attributes:{flight_preview:data}}}});
  assert.equal(readFlights(hass('scheduled'),config),data);
  for(const state of ['unavailable','unknown','calendar_unavailable','simulation_active']) {
    assert.equal(readFlights(hass(state),config),null);
  }
  assert.equal(readFlights({},config),null);
  assert.equal(readFlights({states:{[config.entity]:{state:'idle',attributes:{dashboard:data}}}},config),null);
});

test('airport local time uses IANA rules across separate daylight saving dates',()=>{
  const value='2026-10-31T23:00:00Z';
  assert.match(flightLocalTime(value,'Europe/London'),/23:00/);
  assert.match(flightLocalTime(value,'America/New_York'),/19:00/);
  assert.match(flightLocalTime('2026-11-01T08:00:00Z','America/New_York'),/03:00/);
  assert.match(flightLocalTime(value,null),/23:00/);
  assert.equal(flightLocalTime('2026-10-24T08:00:00',null),'Unknown');
  assert.equal(flightLocalTime(value,'Invalid/Zone'),'Unknown time zone');
});
