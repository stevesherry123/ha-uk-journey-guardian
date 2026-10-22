import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readDashboard, chartRows, validTime, formatTime, JourneyGuardianCard} from './journey-guardian-card.js';
import {previewData} from './preview-data.js';

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

test('clock-change labels distinguish repeated local times',()=>{
  assert.equal(formatTime('2026-10-25T00:30:00Z'), '01:30 BST');
  assert.equal(formatTime('2026-10-25T01:30:00Z'), '01:30 GMT');
});
test('timezone-free dates and malformed zones cannot invent a local time',()=>{
  assert.equal(validTime('2026-10-25T01:30:00'),false);
  assert.equal(validTime('2026-10-25'),false);
  assert.equal(formatTime('2026-10-25T01:30:00Z','not-a-zone'),'Unknown');
});
test('preview suppression states match the backend contract',()=>{
  for (const scenario of ['cancelled','stale']) {
    const data = readDashboard(previewData(scenario), {entity:'sensor.example_journey_status'});
    assert.ok(data.notifications.every(event=>event.eligibility==='suppressed'));
    assert.ok(data.notifications.every(event=>event.eligibility_reason));
  }
  const awake = readDashboard(previewData('awake'), {entity:'sensor.example_journey_status'});
  assert.equal(awake.notifications[0].eligibility,'suppressed');
  assert.equal(awake.latest_notification_record.receipt_confirmed,false);
  assert.equal(readDashboard(previewData('empty'),{entity:'sensor.example_journey_status'}).journey,null);
});
