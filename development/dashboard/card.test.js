import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readDashboard, chartRows, validTime, JourneyGuardianCard} from './journey-guardian-card.js';

test('unavailable, missing and unsupported contracts are not live data',()=>{
  assert.equal(readDashboard({}, {entity:'sensor.example'}),null);
  for(const state of ['unknown','unavailable']) assert.equal(readDashboard({states:{'sensor.example':{state,attributes:{dashboard:{schema_version:1}}}}},{entity:'sensor.example'}),null);
  assert.equal(readDashboard({states:{'sensor.example':{state:'planned',attributes:{dashboard:{schema_version:2}}}}},{entity:'sensor.example'}),null);
});
test('only increasing finite segments can enter the chart',()=>{
  assert.equal(validTime(null),false);
  assert.equal(validTime('invalid'),false);
  assert.deepEqual(chartRows({segments:[{start:'invalid',end:'invalid'},{start:'2026-10-22T10:00:00Z',end:'2026-10-22T09:00:00Z'}]}),[]);
  assert.equal(chartRows({segments:Array(20).fill({start:'2026-10-22T10:00:00Z',end:'2026-10-22T11:00:00Z'})}).length,4);
});
test('configuration requires an explicit status sensor',()=>{
  assert.throws(()=>new JourneyGuardianCard().setConfig({entity:'switch.example'}));
});
