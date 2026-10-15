'use strict';
(() => {
  const data = window.SF_SETUP;
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const command = document.getElementById('install-command');
  const invocation = document.getElementById('host-invocation');
  const text = document.getElementById('prompt-text');
  const details = document.getElementById('prompt-details');
  const status = document.getElementById('copy-status');
  const copy = document.getElementById('copy-prompt');
  let selected = tabs[0].dataset.host;
  let generation = 0;
  text.readOnly = true;

  function selectTab(tab, focus = false) {
    selected = tab.dataset.host;
    generation += 1;
    tabs.forEach(item => {
      const active = item === tab;
      item.setAttribute('aria-selected', String(active));
      item.tabIndex = active ? 0 : -1;
    });
    command.textContent = data[selected].command;
    invocation.textContent = data[selected].invocation;
    text.value = data[selected].prompt;
    copy.textContent = 'Copy setup prompt';
    status.textContent = '';
    document.getElementById('host-panel').setAttribute('aria-labelledby', tab.id);
    if (focus) tab.focus();
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectTab(tab));
    tab.addEventListener('keydown', event => {
      let target;
      if (event.key === 'ArrowRight') target = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') target = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') target = 0;
      if (event.key === 'End') target = tabs.length - 1;
      if (target !== undefined) {
        event.preventDefault();
        selectTab(tabs[target], true);
      }
    });
  });
  copy.addEventListener('click', async () => {
    const subject = generation;
    const prompt = data[selected].prompt;
    copy.textContent = 'Copying…';
    status.textContent = '';
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(prompt);
      if (subject !== generation) return;
      copy.textContent = 'Copied';
      status.textContent = `${data[selected].label} setup prompt copied.`;
    } catch {
      if (subject !== generation) return;
      copy.textContent = 'Copy setup prompt';
      details.open = true;
      text.focus();
      text.select();
      status.textContent = 'Copy unavailable. Select the prompt below and copy it manually.';
    }
  });
  selectTab(tabs[0]);
  const motion = document.getElementById('motion-toggle');
  motion.addEventListener('click', () => {
    const off = motion.getAttribute('aria-pressed') !== 'true';
    motion.setAttribute('aria-pressed', String(off));
    motion.textContent = off ? 'Motion off' : 'Turn motion off';
    document.documentElement.dataset.motion = off ? 'off' : 'on';
  });
})();
