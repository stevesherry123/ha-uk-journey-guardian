import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readDashboard, chartRows, validTime, formatTime, JourneyGuardianCard} from './journey-guardian-card.js';
import {previewData} from './preview-data.js';

test('unavailable, missing and unsupported contracts are not live data',()=>{
  assert.equal(readDashboard({}, {entity:'sensor.example'}),null);
  for(const state of ['unknown','unavailable']) assert.equal(readDashboard({states:{'sensor.example':{state,attributes:{dashboard:{schema_version:1}}}}},{entity:'sensor.example'}),null);
  assert.equal(readDashboard({states:{'sensor.example':{state:'planned',attributes:{dashboard:{schema_version:2}}}}},{entity:'sensor.example'}),null);
});
test('booking warnings render as bounded text without actions or HTML',()=>{
  class Element {
    constructor(tag='div') {this.tag=tag;this.children=[];this.attributes={};}
    append(child) {this.children.push(child);}
    setAttribute(name,value) {this.attributes[name]=value;}
  }
  const prior=globalThis.document;
  globalThis.document={createElement:tag=>new Element(tag)};
  try {
    const root=new Element();
    const card=new JourneyGuardianCard();
    card.config={entity:'sensor.example'};
    card.shadowRoot={querySelector:selector=>selector==='.content'?root:selector==='.status'?new Element():null};
    card._hass={config:{time_zone:'Europe/London'},states:{'sensor.example':{
      state:'planned',attributes:{dashboard:{schema_version:1,healthy:true,
        integrity_warnings:Array(8).fill({message:'<img src=x onerror=alert(1)> Check booking.',recorded_at:'2026-11-06T08:00:00Z'})}
      }}}};
    card.render();
    const nodes=[];const walk=node=>{nodes.push(node);node.children.forEach(walk);};walk(root);
    assert.equal(nodes.filter(node=>node.attributes.role==='status').length,3);
    assert.ok(nodes.some(node=>node.textContent==='<img src=x onerror=alert(1)> Check booking.'));
    assert.ok(nodes.some(node=>node.textContent===' Last failed check: 08:00 GMT.'));
    assert.ok(!nodes.some(node=>['img','button','input'].includes(node.tag)));
  } finally {globalThis.document=prior;}
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

test('connection controls save exact booking IDs and expose failed writes', async()=>{
  class Element {
    constructor(tag='div') { this.tag=tag; this.children=[]; this.listeners={}; }
    append(child) { this.children.push(child); }
    setAttribute() {}
    addEventListener(name, handler) { this.listeners[name]=handler; }
  }
  const prior=globalThis.document;
  globalThis.document={createElement:tag=>new Element(tag)};
  try {
    const root=new Element(); const status=new Element();
    const card=new JourneyGuardianCard();
    card.config={entity:'sensor.example'};
    card.shadowRoot={querySelector:selector=>selector==='.content'?root:selector==='.status'?status:null};
    const calls=[];
    card._hass={states:{'sensor.example':{state:'planned',attributes:{dashboard:{
      schema_version:1,healthy:true,connections:[{station:'Example Junction',
      inbound_id:'a'.repeat(64),outbound_id:'b'.repeat(64),confirmed:false,can_confirm:true,
      allowance_minutes:10,allowance_source:'global_fallback'}]
    }}}},callService:async(...args)=>{calls.push(args);card.render();}};
    card.render();
    const nodes=[]; const walk=node=>{nodes.push(node);node.children.forEach(walk);}; walk(root);
    assert.ok(nodes.some(node=>node.textContent==='Required transfer: 10 minutes / global fallback'));
    const input=nodes.find(node=>node.tag==='input');
    const button=nodes.find(node=>node.tag==='button');
    input.value='12'; await button.listeners.click();
    assert.deepEqual(calls[0],['journey_guardian','confirm_connection',{
      inbound_id:'a'.repeat(64),outbound_id:'b'.repeat(64),override_minutes:12}]);
    assert.ok(nodes.some(node=>node.textContent==='Saved. Connection status will refresh.'));
    card._hass.callService=async()=>{throw new Error('save failed');};
    await button.listeners.click();
    assert.ok(nodes.some(node=>node.textContent==='Could not save. Refresh the calendar and try again.'));
    assert.equal(button.disabled,false);
    const refreshed=[]; const collect=node=>{refreshed.push(node);node.children.forEach(collect);}; collect(root);
    assert.equal(refreshed.filter(node=>node.tag==='button').at(-1).disabled,false);
    input.value='1.5'; await button.listeners.click();
    assert.ok(nodes.some(node=>node.textContent==='Enter whole minutes from 0 to 1440.'));
  } finally { globalThis.document=prior; }
});

test('connection warning previews preserve freshness and receipt uncertainty',()=>{
  const risky=readDashboard(previewData('connection-risk'),{entity:'sensor.example_journey_status'});
  assert.equal(risky.connections[0].assessment.classification,'at_risk');
  assert.equal(risky.connections[0].assessment.minutes_available,7);
  assert.equal(risky.connections[0].last_alert.receipt_confirmed,false);
  const unknown=readDashboard(previewData('connection-unknown'),{entity:'sensor.example_journey_status'});
  assert.equal(unknown.connections[0].assessment.minutes_available,null);
  assert.equal(unknown.connections[0].last_alert.delivery,'claimed');
  assert.equal(readDashboard(previewData('connection-recovered'),{entity:'sensor.example_journey_status'}).connections[0].last_alert.kind,'recovered');
});

test('rendered connection history qualifies stale risk and uncertain handoff',()=>{
  class Element {
    constructor(tag='div') {this.tag=tag;this.children=[];this.style={};}
    append(child) {this.children.push(child);}
    setAttribute() {}
    addEventListener() {}
  }
  const prior=globalThis.document;
  globalThis.document={createElement:tag=>new Element(tag)};
  try {
    for (const scenario of ['connection-risk','connection-recovered','connection-unknown']) {
      const root=new Element();
      const card=new JourneyGuardianCard();
      card.config={entity:'sensor.example_journey_status'};
      card.shadowRoot={querySelector:selector=>selector==='.content'?root:selector==='.status'?new Element():null};
      card._hass=previewData(scenario);
      card.render();
      const texts=[];const walk=node=>{texts.push(node.textContent||'');node.children.forEach(walk);};walk(root);
      const text=texts.join('\n');
      if(scenario==='connection-risk') assert.ok(text.includes('Connection at risk / 7 minutes available / 10 required'));
      if(scenario==='connection-unknown') {
        assert.ok(text.includes('A previous assessment found this connection at risk. Current evidence is unavailable.'));
        assert.ok(text.includes('delivery unconfirmed'));
        assert.ok(!text.includes('7 minutes available'));
        assert.ok(!text.includes('/ claimed /'));
      }
      if(scenario==='connection-recovered') assert.ok(text.includes('Last connection alert attempt: recovered'));
      assert.ok(text.includes('device receipt unconfirmed'));
    }
  } finally {globalThis.document=prior;}
});

test('recovery recheck submits the displayed route and revision', async () => {
  class Element {
    constructor(tag = 'div') { this.tag = tag; this.children = []; this.listeners = {}; this.style = {}; }
    append(child) { this.children.push(child); }
    setAttribute() {}
    addEventListener(name, handler) { this.listeners[name] = handler; }
  }
  const prior = globalThis.document;
  globalThis.document = {createElement: tag => new Element(tag)};
  try {
    const root = new Element();
    const status = new Element();
    const card = new JourneyGuardianCard();
    const entity = 'sensor.example_journey_status';
    card.config = {entity};
    card.shadowRoot = {querySelector: selector =>
      selector === '.content' ? root : selector === '.status' ? status : null};
    const data = previewData('recovery-options');
    const recovery = data.states[entity].attributes.recovery;
    const calls = [];
    card._hass = {...data, callService: async (...args) => {
      calls.push(args);
      recovery.selected_option_id = args[2].option_id;
    }};
    card.render();
    const nodes = [];
    const walk = node => { nodes.push(node); node.children.forEach(walk); };
    walk(root);
    await nodes.find(node => node.textContent === 'Recheck this route').listeners.click();
    assert.deepEqual(calls, [['journey_guardian', 'select_recovery', {
      option_id: recovery.options[0].option_id,
      revision: recovery.options[0].revision,
    }]]);
    nodes.length = 0;
    walk(root);
    assert.ok(nodes.some(node =>
      node.textContent === 'Route rechecked. This is a preview for approval.'));
  } finally { globalThis.document = prior; }
});
