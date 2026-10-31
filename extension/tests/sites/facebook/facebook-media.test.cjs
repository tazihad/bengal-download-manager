const test = require('node:test');
const assert = require('node:assert/strict');
const { parseManifest, mergeManifest, variants, audioChoice, wholeFileUrl, formatRate } = require('../../../src/sites/facebook/shared/facebook-media.js');

const CDN = 'https://video.fbcdn.net/v/t39.24130-6';

const manifest = (videoReps, audioReps = '', duration = 'PT1M30.5S') => `<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="${duration}">
  <Period>
    <AdaptationSet mimeType="video/mp4">
${videoReps}
    </AdaptationSet>
    ${audioReps ? `<AdaptationSet mimeType="audio/mp4">${audioReps}</AdaptationSet>` : ''}
  </Period>
</MPD>`;

const rep = (id, width, height, bandwidth, file, codecs = 'avc1.4d401f') => `
      <Representation id="${id}" width="${width}" height="${height}" bandwidth="${bandwidth}" codecs="${codecs}">
        <BaseURL>${file}</BaseURL>
      </Representation>`;

const video720low = rep('v720low', 1280, 720, 1500000, `${CDN}/low_720.mp4?bytestart=0&byteend=123&oh=abc`);
const video720high = rep('v720high', 1280, 720, 3500000, `${CDN}/high_720.mp4?oh=abc`);
const video1080 = rep('v1080', 1920, 1080, 5000000, `${CDN}/full_1080.mp4?oh=abc`, 'avc1.640028');
const video360 = rep('v360', 640, 360, 500000, `//video.fbcdn.net/v/t39.24130-6/low_360.mp4?oh=abc`);
const audio128 = rep('a128', 0, 0, 128000, `${CDN}/audio_128.m4a?oh=abc`, 'mp4a.40.2');
const audio64 = rep('a64', 0, 0, 64000, `${CDN}/audio_64.m4a?oh=abc`, 'mp4a.40.2');
const audioOpus = `
      <Representation id="aopus" bandwidth="256000" codecs="opus" mimeType="audio/webm">
        <BaseURL>${CDN}/audio_opus.webm?oh=abc</BaseURL>
      </Representation>`;

const audioSet = audio64 + audio128 + audioOpus;
const fullManifest = manifest(video720low + video720high + video1080 + video360, audioSet);

test('keeps every representation, including two 720p renditions with different bitrates', () => {
  const parsed = parseManifest(fullManifest);
  assert.ok(parsed);
  assert.equal(parsed.duration, 90.5);
  assert.deepEqual(parsed.video.map(r => r.id), ['v1080', 'v720high', 'v720low', 'v360']);
  assert.deepEqual(parsed.video.filter(r => r.height === 720).map(r => r.bandwidth), [3500000, 1500000]);
  assert.equal(parsed.video[3].url.startsWith('https://'), true);
  assert.equal(new URL(parsed.video[2].url).searchParams.has('bytestart'), false);
  assert.equal(new URL(parsed.video[2].url).searchParams.has('byteend'), false);
});

test('variants list resolution with bitrate and pair the best audio track', () => {
  const rows = variants(parseManifest(fullManifest));
  assert.equal(rows.length, 4);
  assert.deepEqual(rows.map(r => r.quality), [
    '1080p · 5 Mbps',
    '720p · 3.5 Mbps',
    '720p · 1.5 Mbps',
    '360p · 500 kbps'
  ]);
  assert.deepEqual(rows.map(r => r.label), [
    '1920×1080 · 5 Mbps',
    '1280×720 · 3.5 Mbps',
    '1280×720 · 1.5 Mbps',
    '640×360 · 500 kbps'
  ]);
  assert.equal(rows.every(r => r.audioUrl.endsWith('/audio_128.m4a?oh=abc')), true);
  assert.equal(rows.every(r => r.audioState === 'Video + audio'), true);
  assert.equal(rows.filter(r => r.height === 720).length, 2);
});

test('video without an audio representation stays marked video-only', () => {
  const rows = variants(parseManifest(manifest(video720high)));
  assert.equal(rows.length, 1);
  assert.equal(rows[0].audioUrl, '');
  assert.equal(rows[0].audioState, 'Video only');
});

test('audio choice prefers MP4 over WebM and labels the bitrate', () => {
  const choice = audioChoice(parseManifest(fullManifest));
  assert.equal(choice.url.endsWith('/audio_128.m4a?oh=abc'), true);
  assert.equal(choice.ext, '.m4a');
  assert.equal(choice.quality, 'Audio only · 128 kbps');
  assert.equal(choice.badge, 'AUDIO');
  const webm = audioChoice(parseManifest(manifest(video360, audioOpus)));
  assert.equal(webm.ext, '.webm');
  assert.equal(webm.bitrate, 256000);
});

test('only complete progressive URLs are accepted', () => {
  assert.equal(wholeFileUrl(`${CDN}/clip.m3u8?oh=abc`), null);
  assert.equal(wholeFileUrl(`${CDN}/manifest.mpd`), null);
  assert.equal(wholeFileUrl(`${CDN}/segment.m4s`), null);
  assert.equal(wholeFileUrl('https://user:pass@video.fbcdn.net/clip.mp4'), null);
  assert.equal(wholeFileUrl('not a url'), null);
  const clean = wholeFileUrl(`${CDN}/clip.mp4?range=0-100&sq=2&oh=abc`);
  assert.equal(clean, `${CDN}/clip.mp4?oh=abc`);
  assert.equal(wholeFileUrl('//video.fbcdn.net/clip.mp4?oh=abc'), 'https://video.fbcdn.net/clip.mp4?oh=abc');
});

test('a manifest without whole-file BaseURLs is rejected', () => {
  const segmentTemplate = manifest(`
      <Representation id="v720" width="1280" height="720" bandwidth="1500000">
        <SegmentTemplate media="${CDN}/seg-$Number$.m4s" initialization="${CDN}/init.mp4"/>
      </Representation>`);
  assert.equal(parseManifest(segmentTemplate), null);
  assert.equal(parseManifest('<html><body>no manifest</body></html>'), null);
  assert.equal(parseManifest(''), null);
});

test('merged manifests accumulate renditions without duplicating URLs', () => {
  const first = parseManifest(manifest(video720low + video360));
  const second = parseManifest(manifest(video1080 + video720high + video720low));
  const merged = mergeManifest(mergeManifest(null, first), second);
  assert.deepEqual(merged.video.map(r => r.id), ['v1080', 'v720high', 'v720low', 'v360']);
  assert.equal(merged.duration, 90.5);
  assert.equal(mergeManifest(null, null), null);
});

test('formatRate renders Mbps and kbps without inventing precision', () => {
  assert.equal(formatRate(5000000), '5 Mbps');
  assert.equal(formatRate(3500000), '3.5 Mbps');
  assert.equal(formatRate(128000), '128 kbps');
  assert.equal(formatRate(0), '');
});
