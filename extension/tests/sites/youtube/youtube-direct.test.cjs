const test = require('node:test');
const assert = require('node:assert/strict');

const eventStub = () => ({ addListener() {} });
const fakeChrome = {
  runtime: { id: 'test' },
  webRequest: { onHeadersReceived: eventStub(), onBeforeRequest: eventStub() },
  tabs: { onRemoved: eventStub(), onUpdated: eventStub() }
};
globalThis.chrome = fakeChrome;

// youtube-media.js must be loaded first: youtube-direct.js reads bdmYouTube.mediaUrl.
require('../../../src/sites/youtube/shared/youtube-media.js');
const { observe, observeAbrRequest, getObserved, getCapture, clear } = require('../../../src/sites/youtube/background/youtube-direct.js');

const playback = (itag, extra = '') => `https://r1.googlevideo.com/videoplayback?id=asset&itag=${itag}&expire=9999999999${extra}`;
const details = (tabId, url, statusCode = 200, mime = 'video/mp4; codecs="avc1"') => ({
  tabId,
  url,
  statusCode,
  responseHeaders: [{ name: 'Content-Type', value: mime }]
});

test('successful media responses are recorded newest first', () => {
  const t = 1;
  clear(t);
  observe(details(t, playback(137)));
  observe(details(t, playback(140), 206, 'audio/mp4'));
  assert.deepEqual(getObserved(t), [playback(140), playback(137)]);
  observe(details(t, playback(137)));
  assert.equal(getObserved(t).length, 2);
});

test('non-media, failed, malformed and fragment responses are ignored', () => {
  const t = 2;
  clear(t);
  observe(details(t, playback(137), 403));
  observe(details(t, playback(137), 200, 'text/html'));
  observe(details(t, playback(137, '&sabr=1')));
  observe(details(t, playback(137, '&sq=2')));
  observe(details(t, 'https://example.com/videoplayback'));
  observe(details(-1, playback(137)));
  observe(null);
  assert.deepEqual(getObserved(t), []);
});

test('range parameters are stripped unless the signature binds them', () => {
  const t = 3;
  clear(t);
  observe(details(t, playback(137, '&range=0-100')));
  observe(details(t, playback(140, '&range=0-100&sparams=id,range')));
  assert.deepEqual(getObserved(t), [playback(137).replace('&range=0-100', '')]);
});

test('tab list is capped and clear() drops the tab', () => {
  const t = 4;
  clear(t);
  for (let i = 0; i < 110; i++) observe(details(t, `https://r1.googlevideo.com/videoplayback?id=a${i}&itag=137&expire=9999999999`));
  const list = getObserved(t);
  assert.equal(list.length, 100);
  assert.equal(list[0].includes('id=a109'), true);
  clear(t);
  assert.deepEqual(getObserved(t), []);
});

const sabr = 'https://r1.googlevideo.com/videoplayback?id=asset&sabr=1';
const abrRequest = (requestId, tabId, bytes) => ({
  requestId,
  tabId,
  url: sabr,
  requestBody: { raw: bytes ? [{ type: 'raw', bytes }] : [] }
});
const abrResponse = (requestId, tabId, statusCode) => ({
  requestId,
  tabId,
  url: sabr,
  statusCode,
  responseHeaders: [{ name: 'Content-Type', value: 'application/vnd.yt-ump' }]
});

test('SABR seed is promoted to a capture only after a successful response', () => {
  const t = 5;
  clear(t);
  observeAbrRequest(abrRequest('r1', t, new Uint8Array([1, 2, 3])));
  assert.equal(getCapture(t), null);
  observe(abrResponse('r999', t, 200));
  assert.equal(getCapture(t), null);
  observe(abrResponse('r1', t, 403));
  assert.equal(getCapture(t), null);
  observeAbrRequest(abrRequest('r2', t, new Uint8Array([4, 5, 6])));
  observe(abrResponse('r2', t, 206));
  const capture = getCapture(t);
  assert.equal(capture.url, sabr);
  assert.deepEqual(Buffer.from(capture.requestBody, 'base64'), Buffer.from([4, 5, 6]));
  clear(t);
  assert.equal(getCapture(t), null);
});

test('oversized, empty and non-SABR ABR bodies are never seeded', () => {
  const t = 6;
  clear(t);
  observeAbrRequest(abrRequest('r1', t, new Uint8Array(262145)));
  observe(abrResponse('r1', t, 200));
  observeAbrRequest(abrRequest('r2', t, new Uint8Array(0)));
  observe(abrResponse('r2', t, 200));
  observeAbrRequest({ requestId: 'r3', tabId: t, url: sabr.replace('sabr=1', 'sabr=1&id=x'), requestBody: null });
  observeAbrRequest({ requestId: 'r4', tabId: t, url: 'https://r1.googlevideo.com/videoplayback?id=asset&itag=137', requestBody: { raw: [{ type: 'raw', bytes: new Uint8Array([1]) }] } });
  observe(details(t, 'https://r1.googlevideo.com/videoplayback?id=asset&itag=137', 200, 'video/mp4'));
  assert.equal(getCapture(t), null);
});
