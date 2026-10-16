// Synthetic execution of the real readiness script. No browser is started.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');

async function scenario(mode) {
  const canvas = {clientWidth: 1200, clientHeight: 800, scrollWidth: 1200, scrollHeight: 800,
    getBoundingClientRect: () => ({left: 0, top: 0, right: mode === 'overflow' ? 1202 : 1200, bottom: 800})};
  const root = {dataset: {}, scrollWidth: 1200, scrollHeight: 800};
  const handlers = {};
  const document = {
    documentElement: root, body: {innerText: 'Public specimen'},
    addEventListener: (event, callback) => { handlers[event] = callback; },
    querySelectorAll: () => [canvas],
    fonts: {ready: Promise.resolve(), load: async profile => {
      const [, weight, family] = profile.match(/^(\d+) 24px "(.+)"$/);
      if (mode === 'fallback') return [];
      return [{family, weight, status: mode === 'unloaded' ? 'unloaded' : 'loaded'}];
    }},
    images: [{complete: true, naturalWidth: 33, decode: async () => {
      if (mode === 'decode') throw new Error('decode failed');
    }}],
  };
  const window = {addEventListener: (event, callback) => { handlers[event] = callback; }};
  const context = vm.createContext({window, document, innerWidth: 1200, innerHeight: 800,
    URL, location: {origin: 'http://127.0.0.1:4317'},
    performance: {getEntriesByType: () => [{name: mode === 'remote' ? 'https://invalid.example/font' : 'http://127.0.0.1:4317/font'}]},
    requestAnimationFrame: callback => queueMicrotask(callback),
  });
  await vm.runInContext(source, context, {timeout: 1000});
  assert.equal(root.dataset.renderReady, mode === 'success' ? 'true' : 'false', mode);
  if (mode === 'success') {
    assert.equal(window.SF_RENDER_REPORT.fonts.length, 4);
    assert.equal(window.SF_RENDER_REPORT.images_decoded, true);
  } else {
    assert.ok(window.SF_RENDER_REPORT.failed.length > 0, mode);
  }
}

(async () => {
  for (const mode of ['success', 'fallback', 'unloaded', 'decode', 'overflow', 'remote']) await scenario(mode);
  console.log('6 synthetic readiness scenarios passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
