const test = require('node:test');
const assert = require('node:assert/strict');
const { parseManifest, mergeManifest, variants, audioChoice, wholeFileUrl, formatRate, videoIdFromUrl, isVideoId, videoIdFromElement, manifestScore, manifestFits, pickManifest, manifestsInText } = require('../../../../extension/src/sites/facebook/shared/facebook-media.js');

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

test('the page URL names the video so a manifest cannot be reused for a neighbour', () => {
  assert.equal(videoIdFromUrl('https://www.facebook.com/reel/1458325679840918/'), '1458325679840918');
  assert.equal(videoIdFromUrl('https://www.facebook.com/reel/1458325679840918/?paipv=0'), '1458325679840918');
  assert.equal(videoIdFromUrl('https://www.facebook.com/watch/?v=9988776655443322'), '9988776655443322');
  assert.equal(videoIdFromUrl('https://www.facebook.com/1000123/videos/1234567890123456/'), '1234567890123456');
  assert.equal(videoIdFromUrl('https://www.facebook.com/story.php?story_fbid=999&id=123'), '');
  assert.equal(videoIdFromUrl('https://www.facebook.com/watch/feed/'), '');
  assert.equal(videoIdFromUrl('https://www.facebook.com/reel/abc'), '');
});

test('only full Facebook video ids are accepted', () => {
  assert.equal(isVideoId('1458325679840918'), true);
  assert.equal(isVideoId(1458325679840917.5), false);
  assert.equal(isVideoId('123'), false);
  assert.equal(isVideoId(''), false);
  assert.equal(isVideoId(undefined), false);
});

const reelManifest = (file, duration, heights = [[1280, 720]]) => parseManifest(manifest(
  heights.map(([width, height], index) => rep(`v${index}`, width, height, 1500000 + index, `${CDN}/${file}_${height}.mp4?oh=abc`)).join(''),
  '',
  duration
));

test('a preloaded manifest is recovered by clip length and rendition', () => {
  const firstReel = reelManifest('first', 'PT0M12.2S');
  const secondReel = reelManifest('second', 'PT0M48.7S');
  // Reels scroll newest last in the payload, so the list is newest-first at report time.
  const candidates = [secondReel, firstReel];

  assert.equal(pickManifest(candidates, { duration: 12.4, width: 1280, height: 720 }), firstReel);
  assert.equal(pickManifest(candidates, { duration: 48.5, width: 1280, height: 720 }), secondReel);
  // A manifest whose length disagrees must never be offered for this element.
  assert.equal(pickManifest([secondReel], { duration: 12.4, height: 720 }), null);
  assert.equal(manifestFits(secondReel, { duration: 12.4, height: 720 }), false);
  // Same rendition but no metadata yet: two preloads cannot be told apart, so no guess.
  assert.equal(pickManifest(candidates, { duration: 0, height: 720 }), null);
  assert.equal(pickManifest([secondReel], { duration: 0, height: 720 }), secondReel);

  // The rendition the player shows breaks a duration tie between two clips.
  const tall = reelManifest('tall', 'PT0M30S', [[720, 1280], [360, 640]]);
  const wide = reelManifest('wide', 'PT0M30S', [[1280, 720]]);
  assert.equal(pickManifest([wide, tall], { duration: 30, width: 720, height: 1280 }), tall);
  assert.equal(pickManifest([tall, wide], { duration: 30, width: 1280, height: 720 }), wide);
});

test('manifest score rejects the wrong clip and rewards the playing rendition', () => {
  const sixty = reelManifest('sixty', 'PT0M60S');
  assert.equal(manifestScore(sixty, { duration: 60, height: 720 }), 150);
  assert.equal(manifestScore(sixty, { duration: 60, height: 640 }) > 0, true);
  assert.equal(manifestScore(sixty, { duration: 60, height: 360 }), -1);
  assert.equal(manifestScore(sixty, { duration: 30, height: 720 }), -1);
  assert.equal(manifestScore(null, { duration: 60 }), -1);
});

test('GraphQL payloads bind every manifest to its own video id', () => {
  const first = manifest(video720low + video360);
  const second = manifest(video1080);
  const body = JSON.stringify({
    data: {
      reels: {
        edges: [
          { node: { video: { videoFBID: '1458325679840918', dash_manifest: first } } },
          { node: { video: { video_id: '9988776655443322', dash_manifest: second } } }
        ]
      }
    }
  });
  const found = manifestsInText(body);
  assert.equal(found.length, 2);
  assert.deepEqual(found.map(item => item.ids), [['1458325679840918'], ['9988776655443322']]);
  assert.equal(manifestsInText('{"nothing":"here"}').length, 0);
});

test('HTML payloads find the id nearest to an embedded manifest', () => {
  const xml = manifest(video1080);
  const body = `<!DOCTYPE html><html><body><script>window.__data = ${JSON.stringify({
    videoFBID: '1458325679840918',
    dash_manifest: xml,
    preload: 'x'.repeat(20000)
  })};</script></body></html>`;
  const found = manifestsInText(body);
  assert.equal(found.length, 1);
  assert.deepEqual(found[0].ids, ['1458325679840918']);
  assert.equal(parseManifest(found[0].xml) !== null, true);
});

test('a manifest with no id nearby is still returned so it can be matched later', () => {
  const xml = manifest(video720high);
  const body = `<!DOCTYPE html><html><body><script>window.__data = ${JSON.stringify({ dash_manifest: xml })};</script></body></html>`;
  const found = manifestsInText(body);
  assert.equal(found.length, 1);
  assert.deepEqual(found[0].ids, []);
});

test('deep GraphQL payloads bind the manifest to the owner object plain id', () => {
  // Real watch/reel payload: the manifest sits ~18 levels down under
  // .../media/videoDeliveryLegacyFields, whose only id is a plain "id".
  const xml = manifest(video1080 + video720high);
  const payload = { data: {} };
  let cursor = payload.data;
  for (let level = 0; level < 16; level++) {
    cursor.nested = {};
    cursor = cursor.nested;
  }
  cursor.media = {
    videoDeliveryLegacyFields: {
      dash_manifest_xml_string: xml,
      dash_manifest_url: 'https://www.facebook.com/dash_mpd_debug.mpd?v=1915341995784351',
      browser_native_sd_url: `${CDN}/sd.mp4?oh=abc`,
      browser_native_hd_url: `${CDN}/hd.mp4?oh=abc`,
      id: '1915341995784351'
    }
  };
  const found = manifestsInText(JSON.stringify(payload));
  assert.equal(found.length, 1);
  assert.deepEqual(found[0].ids, ['1915341995784351']);
  assert.equal(parseManifest(found[0].xml).video.length, 2);
});

test('a manifest in a late application/json block is still found', () => {
  const xml = manifest(video360);
  const blocks = [];
  for (let index = 0; index < 30; index++) {
    blocks.push(`<script type="application/json">{"noise":${index},"filler":"${'x'.repeat(50)}"}</script>`);
  }
  blocks.push(`<script type="application/json" data-sjs>${JSON.stringify({
    require: [null, null, null, [{
      __bbox: {
        require: [null, null, null, [null, {
          __bbox: { result: { data: { video: { story: { attachments: [{ media: {
            videoDeliveryLegacyFields: { dash_manifest_xml_string: xml, id: '1458325679840918' }
          } }] } } } } }
        }]]
      }
    }]]
  })}</script>`);
  const found = manifestsInText(`<!DOCTYPE html><html><body>${blocks.join('')}</body></html>`);
  assert.equal(found.length, 1);
  assert.deepEqual(found[0].ids, ['1458325679840918']);
});

test('dash_manifests entries keep their own ids', () => {
  const first = manifest(video720low);
  const second = manifest(video1080);
  const body = JSON.stringify({
    data: {
      dash_manifests: [
        { id: '1458325679840918', manifest_xml: first },
        { id: '9988776655443322', manifest_xml: second }
      ]
    }
  });
  const found = manifestsInText(body);
  assert.deepEqual(found.map(item => item.ids), [['1458325679840918'], ['9988776655443322']]);
});

test('plain id is only trusted on the object that holds the manifest', () => {
  const xml = manifest(video360);
  const body = JSON.stringify({
    id: '1111111111111111',
    node: { story: { videoDeliveryLegacyFields: { dash_manifest_xml_string: xml } } }
  });
  const found = manifestsInText(body);
  assert.equal(found.length, 1);
  assert.deepEqual(found[0].ids, []);
});

test('HTML payloads use the owner plain id when no video-specific key exists', () => {
  const xml = manifest(video1080);
  const body = `<html><body><script>window.__data = ${JSON.stringify({
    videoDeliveryLegacyFields: {
      dash_manifest_xml_string: xml,
      dash_manifest_url: '',
      browser_native_sd_url: '',
      browser_native_hd_url: '',
      id: '1915341995784351'
    },
    preload: 'x'.repeat(20000)
  })};</script></body></html>`;
  const found = manifestsInText(body);
  assert.equal(found.length, 1);
  assert.deepEqual(found[0].ids, ['1915341995784351']);
});

function fakeElement({ attrs = {}, videos = [], links = [], parent = null } = {}) {
  return {
    dataset: attrs.dataset || {},
    getAttribute: name => (name in attrs ? attrs[name] : null),
    querySelectorAll: selector => (selector === 'video' ? videos : links),
    parentElement: parent
  };
}

test('the element wrapper names the scrolled-to reel without a URL change', () => {
  const permalink = { href: 'https://www.facebook.com/reel/1458325679840918/' };
  const wrapper = fakeElement({ links: [permalink] });
  const video = fakeElement({ parent: wrapper });
  assert.equal(videoIdFromElement(video), '1458325679840918');

  const tagged = fakeElement({ attrs: { dataset: { videoFbid: '9988776655443322' } } });
  assert.equal(videoIdFromElement(tagged), '9988776655443322');

  // Feed wrappers hold many videos: their first permalink must not leak into this clip.
  const feed = fakeElement({ links: [permalink], videos: [video, fakeElement()] });
  assert.equal(videoIdFromElement(fakeElement({ parent: feed })), '');
});
