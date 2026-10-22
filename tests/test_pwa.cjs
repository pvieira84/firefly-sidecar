'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
(async () => {
  for (const mount of ['/', '/sidecar/']) {
    const scope = 'https://firefly.example' + mount;
    const events = {};
    const cached = new Map();
    const removed = [];
    const offline = {offline: true};
    let fail = false;
    let networkResult = {status: 200};
    const cache = {
      add: async request => cached.set(request.url, offline),
      match: async url => cached.get(url)
    };
    const cachePrefix = 'firefly-sidecar-' + encodeURIComponent(scope) + '-';
    const context = {
      URL, Request, Response,
      self: {registration: {scope}, location: {origin: 'https://firefly.example'},
        addEventListener: (name, fn) => events[name] = fn,
        skipWaiting: async () => {}, clients: {claim: async () => {}}},
      caches: {open: async () => cache,
        keys: async () => ['firefly-main-cache', cachePrefix+'old', cachePrefix+'offline-v1'],
        delete: async name => removed.push(name)},
      fetch: async () => {if (fail) throw Error('offline'); return networkResult;}
    };
    vm.runInNewContext(fs.readFileSync('sidecar/static/sw.js','utf8'), context);
    let pending;
    events.install({waitUntil: promise => pending = promise}); await pending;
    assert.deepEqual([...cached.keys()], [scope+'offline.html']);
    events.activate({waitUntil: promise => pending = promise}); await pending;
    assert.deepEqual(removed, [cachePrefix+'old']);
    async function request(path, method = 'GET', mode = 'navigate') {
      let response;
      events.fetch({request: {url: 'https://firefly.example'+path, method, mode},
        respondWith: promise => response = promise});
      return response === undefined ? undefined : await response;
    }
    assert.equal(await request(mount+'api/validation'), undefined);
    assert.equal(await request(mount+'api/validation/complete', 'POST'), undefined);
    assert.equal(await request(mount+'app.js', 'GET', 'cors'), undefined);
    if (mount !== '/') assert.equal(await request('/transactions/show/123'), undefined);
    assert.equal(await request(mount), networkResult);
    networkResult = {status: 401};
    assert.equal(await request(mount), networkResult, 'Authentication errors must stay visible');
    fail = true;
    assert.equal(await request(mount), offline);
  }
  console.log('PWA scope, offline fallback, authentication, API/write bypass and isolated cache cleanup passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
