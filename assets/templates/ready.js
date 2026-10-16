'use strict';

// A loaded named FontFace, decoded pixels and bounded layout are all required.
const failed = [];
const report = {fonts: [], viewport: [innerWidth, innerHeight], overflow: [], failed, images_decoded: false, resources: [], policy_violations: []};
window.SF_RENDER_REPORT = report;
window.addEventListener('error', () => failed.push('resource or script error'), true);
const resourceLabel = value => {
  try {
    const url = new URL(value);
    return url.origin === location.origin ? url.pathname : `${url.protocol}//${url.hostname}`;
  } catch { return String(value).slice(0, 80); }
};
document.addEventListener('securitypolicyviolation', event => {
  failed.push('content security policy violation');
  if (report.policy_violations.length < 8) report.policy_violations.push({directive: event.effectiveDirective, blocked: resourceLabel(event.blockedURI), source: resourceLabel(event.sourceFile), line: event.lineNumber});
});

(async () => {
  try {
    const sample = document.body.innerText;
    const profiles = [['Bricolage', '700'], ['Inter', '400'], ['Inter', '600'], ['JetBrains Mono', '400']];
    for (const [family, weight] of profiles) {
      const faces = await document.fonts.load(`${weight} 24px "${family}"`, sample);
      const matching = faces.filter(face => face.family.replaceAll('"', '').replaceAll("'", '') === family && face.weight === weight && face.status === 'loaded');
      if (!matching.length) throw new Error(`required named font did not load: ${family}:${weight}`);
      report.fonts.push(`${family}:${weight}`);
    }
    await document.fonts.ready;
    await Promise.all([...document.images].map(async image => {
      await image.decode();
      if (!image.complete || !image.naturalWidth) throw new Error('image did not decode');
    }));
    report.images_decoded = true;
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const overflow = [];
    for (const [index, element] of [...document.querySelectorAll('[data-fit]')].entries()) {
      const bounds = element.getBoundingClientRect();
      if (bounds.left < -1 || bounds.top < -1 || bounds.right > innerWidth + 1 || bounds.bottom > innerHeight + 1 || element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1) overflow.push({index, element: `${element.tagName}.${element.className}`, bounds: [bounds.left, bounds.top, bounds.right, bounds.bottom].map(Math.round), client: [element.clientWidth, element.clientHeight], scroll: [element.scrollWidth, element.scrollHeight]});
    }
    if (document.documentElement.scrollWidth > innerWidth || document.documentElement.scrollHeight > innerHeight) overflow.push('document');
    const resources = performance.getEntriesByType('resource').map(entry => new URL(entry.name));
    if (resources.some(url => url.origin !== location.origin)) failed.push('nonlocal resource');
    report.overflow = overflow;
    report.resources = resources.map(url => url.pathname);
    if (failed.length || overflow.length) throw new Error('resource or layout validation failed');
    document.documentElement.dataset.renderReady = 'true';
  } catch (error) {
    failed.push(error.message);
    document.documentElement.dataset.renderReady = 'false';
  } finally {
    // Bounded diagnostic survives failures and is inspectable through ordinary DOM tools.
    document.documentElement.dataset.renderReport = JSON.stringify(report).slice(0, 6000);
  }
})();
