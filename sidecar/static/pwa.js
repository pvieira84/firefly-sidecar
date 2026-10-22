'use strict';
(() => {
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
  const base = document.documentElement.dataset.basePath || '';
  window.addEventListener('load', () => {
    navigator.serviceWorker.register(base + '/sw.js', {scope: base + '/', updateViaCache: 'none'})
      .catch(error => console.warn('Sidecar PWA registration failed:', error));
  });
  const button = document.getElementById('install-app');
  let prompt;
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    prompt = event;
    button.hidden = false;
  });
  button.addEventListener('click', async () => {
    if (!prompt) return;
    const pending = prompt;
    prompt = undefined;
    button.hidden = true;
    await pending.prompt();
  });
  window.addEventListener('appinstalled', () => {
    prompt = undefined;
    button.hidden = true;
  });
})();
