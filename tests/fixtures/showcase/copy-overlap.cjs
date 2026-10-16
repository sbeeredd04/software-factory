'use strict';
// Synthetic unit adapter: executes the real page script, without a browser or network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');

function harness() {
  const state = {focus: null, selection: null};
  function element(id) {
    return {id, dataset: {}, attributes: {}, events: {}, textContent: '', value: '', open: false,
      addEventListener(type, callback) { this.events[type] = callback; },
      setAttribute(name, value) { this.attributes[name] = value; },
      getAttribute(name) { return this.attributes[name] ?? null; },
      focus() { state.focus = this.id; },
      select() { state.selection = this.id; }
    };
  }
  const names = ['install-command', 'host-invocation', 'prompt-text', 'prompt-details',
    'copy-status', 'copy-prompt', 'host-panel', 'motion-toggle'];
  const elements = new Map(names.map(name => [name, element(name)]));
  const keys = ['claude-code', 'cursor', 'codex'];
  const tabs = keys.map(key => { const tab = element(`tab-${key}`); tab.dataset.host = key; return tab; });
  const data = Object.fromEntries(keys.map((key, index) => [key, {label: `Host ${index + 1}`,
    command: `preview ${key}`, invocation: `invoke ${key}`, prompt: `Reviewed ${key} prompt\n`}]));
  const writes = [];
  const clipboard = {writeText(prompt) { return new Promise((resolve, reject) => writes.push({prompt, resolve, reject})); }};
  vm.runInNewContext(source, {window: {SF_SETUP: data}, navigator: {clipboard},
    document: {querySelectorAll() { return tabs; }, getElementById(id) { return elements.get(id); }, documentElement: {dataset: {}}}});
  function snapshot() {
    return {label: elements.get('copy-prompt').textContent, status: elements.get('copy-status').textContent,
      fallback: elements.get('prompt-details').open, prompt: elements.get('prompt-text').value,
      command: elements.get('install-command').textContent, invocation: elements.get('host-invocation').textContent,
      focus: state.focus, selection: state.selection};
  }
  function copy() { return elements.get('copy-prompt').events.click(); }
  function assertPending() {
    assert.equal(elements.get('copy-prompt').textContent, 'Copying…');
    assert.equal(elements.get('copy-status').textContent, '');
  }
  return {elements, tabs, writes, snapshot, copy, assertPending};
}

async function newestFailureSurvivesOldSuccess() {
  const h = harness();
  h.elements.get('copy-status').textContent = 'Earlier status';
  h.elements.get('copy-prompt').textContent = 'Copied';
  const old = h.copy(); h.assertPending();
  h.elements.get('copy-status').textContent = 'Status between attempts';
  const latest = h.copy(); h.assertPending();
  assert.equal(h.writes.length, 2);
  h.writes[1].reject(new Error('Clipboard denied'));
  await latest;
  const settled = h.snapshot();
  assert.equal(settled.label, 'Copy setup prompt');
  assert.equal(settled.status, 'Copy unavailable. Select the prompt below and copy it manually.');
  assert.equal(settled.fallback, true);
  assert.equal(settled.focus, 'prompt-text');
  assert.equal(settled.selection, 'prompt-text');
  h.writes[0].resolve(); await old;
  assert.deepEqual(h.snapshot(), settled, 'Older success replaced the latest failed attempt');
}

async function newestSuccessSurvivesOldFailure() {
  const h = harness();
  const old = h.copy(); h.assertPending();
  const latest = h.copy(); h.assertPending();
  h.writes[1].resolve(); await latest;
  const settled = h.snapshot();
  assert.equal(settled.label, 'Copied');
  assert.equal(settled.status, 'Host 1 setup prompt copied.');
  assert.equal(settled.fallback, false);
  assert.equal(settled.focus, null);
  assert.equal(settled.selection, null);
  h.writes[0].reject(new Error('Earlier clipboard denied')); await old;
  assert.deepEqual(h.snapshot(), settled, 'Older failure replaced or focused over the latest success');
}

async function hostChangeInvalidatesPending() {
  for (const reject of [false, true]) {
    const h = harness();
    const old = h.copy(); h.assertPending();
    h.tabs[1].events.click();
    const selected = h.snapshot();
    assert.equal(selected.command, 'preview cursor');
    assert.equal(selected.prompt, 'Reviewed cursor prompt\n');
    assert.equal(selected.label, 'Copy setup prompt');
    assert.equal(selected.status, '');
    if (reject) h.writes[0].reject(new Error('Old host denied')); else h.writes[0].resolve();
    await old;
    assert.deepEqual(h.snapshot(), selected, 'A prior host attempt changed the new host or fallback focus');
  }
}

async function main() {
  const cases = [newestFailureSurvivesOldSuccess, newestSuccessSurvivesOldFailure, hostChangeInvalidatesPending];
  let failed = 0;
  console.log(`Synthetic copy unit runtime: Node ${process.version}, V8 ${process.versions.v8}`);
  for (const run of cases) {
    try { await run(); console.log(`PASS ${run.name}`); }
    catch (error) { failed += 1; console.error(`FAIL ${run.name}: ${error.message}`); }
  }
  console.log(`copy overlap: ${cases.length} cases, ${failed} failed`);
  process.exitCode = failed ? 1 : 0;
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
