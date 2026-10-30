const test = require('node:test');
const assert = require('node:assert/strict');
const { mediaUrl, playerData, choices, sabrSession } = require('./youtube-media.js');

const url = (itag, id = 'asset') => `https://r1.googlevideo.com/videoplayback?id=${id}&itag=${itag}&expire=9999999999`;
const player = (formats, extra = {}) => playerData({
  videoDetails: { videoId: 'wLdZWyLOJCI', title: 'Test video' },
  streamingData: { adaptiveFormats: formats, ...extra },
  playerConfig: { mediaCommonConfig: { mediaUstreamerRequestConfig: { videoPlaybackUstreamerConfig: 'AQID' } } }
});
const audio = { itag: 140, url: url(140), mimeType: 'audio/mp4; codecs="mp4a.40.2"', bitrate: 128000 };

test('reject fragments, lookalike hosts and signed partial ranges', () => {
  assert.equal(mediaUrl('https://googlevideo.com.evil.test/videoplayback'), null);
  assert.equal(mediaUrl(url(137) + '&sq=2'), null);
  assert.equal(mediaUrl(url(137) + '&range=0-100&sparams=id,range'), null);
  assert.equal(new URL(mediaUrl(url(137) + '&range=0-100')).searchParams.has('range'), false);
});

test('an observed resolved URL must match both asset and itag', () => {
  const data = player([{ itag: 137, signatureCipher: new URLSearchParams({ url: url(137), s: 'unresolved' }).toString(), mimeType: 'video/mp4', height: 1080 }, audio]);
  assert.equal(choices(data, [url(137, 'wrong')]).some(x => x.format === 'MP4'), false);
  assert.equal(choices(data, [url(137) + '&sig=resolved'])[0].format, 'MP4');
});

test('captured adaptive video is paired with audio, never silently offered alone', () => {
  const video = { itag: 137, url: url(137), mimeType: 'video/mp4; codecs="avc1"', height: 1080 };
  assert.deepEqual(choices(player([video])), []);
  const result = choices(player([video, audio]));
  assert.equal(result[0].audioUrl, url(140));
  assert.equal(result[0].quality, '1080p');
  assert.equal(result[1].format, 'MP3');
});

test('expired formats are not selectable', () => {
  assert.equal(choices(player([{ ...audio, url: url(140).replace('9999999999', '1') }])).length, 0);
});

test('SABR metadata produces only sabrSelection rows without observed URLs', () => {
  const data = player([
    { itag: 137, url: url(137), mimeType: 'video/mp4; codecs="avc1"', height: 1080, bitrate: 3000000, lastModified: '1', approxDurationMs: '10000' },
    { itag: 140, url: url(140), mimeType: 'audio/mp4; codecs="mp4a.40.2"', audioQuality: 'AUDIO_QUALITY_MEDIUM', bitrate: 128000, lastModified: '1', approxDurationMs: '10000' }
  ], { serverAbrStreamingUrl: 'https://r1.googlevideo.com/videoplayback?id=asset&sabr=1&expire=9999999999' });
  assert.equal(data.sabr, true);
  const result = choices(data);
  assert.ok(result.length);
  assert.equal(result.every(x => x.sabrSelection), true);
  assert.equal(mediaUrl(url(137) + '&sabr=1'), null);
});

test('observed video and audio itags yield instant rows instead of SABR ones', () => {
  const data = player([
    { itag: 137, url: url(137), mimeType: 'video/mp4; codecs="avc1"', height: 1080, bitrate: 3000000, lastModified: '1', approxDurationMs: '10000' },
    { itag: 140, url: url(140), mimeType: 'audio/mp4; codecs="mp4a.40.2"', audioQuality: 'AUDIO_QUALITY_MEDIUM', bitrate: 128000, lastModified: '1', approxDurationMs: '10000' }
  ], { serverAbrStreamingUrl: 'https://r1.googlevideo.com/videoplayback?id=asset&sabr=1&expire=9999999999' });
  const result = choices(data, [url(140), url(137)]);
  const row = result.find(x => x.quality === '1080p');
  assert.equal(row.url, url(137));
  assert.equal(row.audioUrl, url(140));
  assert.equal(row.sabrSelection, undefined);
});

test('SABR avoids unobserved direct URLs and does not treat muxed itags as adaptive', () => {
  const data = { ...player([
    { itag: 18, url: url(18), mimeType: 'video/mp4; codecs="avc1, mp4a"', height: 360, audioQuality: 'AUDIO_QUALITY_LOW' },
    { itag: 134, url: url(134), mimeType: 'video/mp4; codecs="avc1"', height: 360 }, audio
  ]), sabrUrl: 'https://r1.googlevideo.com/videoplayback?id=asset&sabr=1', ustreamerConfig: 'AQID' };
  const result = choices(data);
  assert.equal(result.filter(x => x.format === 'MP4').length, 1);
  assert.deepEqual(result[0].sabrSelection, { videoItag: 134, audioItag: 140 });
  assert.equal(choices(data, [url(18)])[0].url, url(18));
  assert.equal(choices(data, [url(18)])[0].sabrSelection, undefined);
});

const sabrStreamUrl = 'https://r1.googlevideo.com/videoplayback?id=asset&sabr=1&expire=9999999999';
const sabrPlayer = player([
  { itag: 137, url: url(137), mimeType: 'video/mp4; codecs="avc1"', height: 1080, contentLength: '9000000' },
  { itag: 140, url: url(140), mimeType: 'audio/mp4; codecs="mp4a.40.2"', bitrate: 128000, contentLength: '1200000' },
  { itag: 140, url: url(140, 'drc'), mimeType: 'audio/mp4; codecs="mp4a.40.2"', bitrate: 96000, contentLength: '900000', isDrc: true }
], { serverAbrStreamingUrl: sabrStreamUrl });

test('sabrSession pairs the captured ABR request with the selected itags', () => {
  const capture = { url: sabrStreamUrl, requestBody: 'AAED' };
  const session = sabrSession(sabrPlayer, capture, { videoItag: '137', audioItag: '140' });
  assert.equal(session.serverAbrStreamingUrl, sabrStreamUrl);
  assert.equal(session.videoPlaybackUstreamerConfig, 'AQID');
  assert.deepEqual(session.formats.map(f => f.itag), [137, 140]);
  assert.equal(session.formats[1].contentLength, '1200000');
  assert.equal(session.videoItag, 137);
  assert.equal(session.audioItag, 140);
  assert.equal(session.requestBody, 'AAED');
  assert.equal(session.sizeBytes, 10200000);
});

test('sabrSession supports audio-only selections and rejects unusable ones', () => {
  const capture = { url: sabrStreamUrl };
  const audio = sabrSession(sabrPlayer, capture, { audioItag: 140 });
  assert.equal(audio.videoItag, undefined);
  assert.deepEqual(audio.formats.map(f => f.itag), [140]);
  assert.equal(audio.requestBody, undefined);
  assert.equal(sabrSession(sabrPlayer, capture, { videoItag: 137, audioItag: 999 }), null);
  assert.equal(sabrSession(sabrPlayer, capture, { videoItag: 999, audioItag: 140 }), null);
  assert.equal(sabrSession(sabrPlayer, null, { audioItag: 140 }), null);
  assert.equal(sabrSession({ ...sabrPlayer, ustreamerConfig: '' }, capture, { audioItag: 140 }), null);
  assert.equal(sabrSession({ ...sabrPlayer, videoId: 'bad!' }, capture, { audioItag: 140 }), null);
  const drcOnly = { ...sabrPlayer, formats: sabrPlayer.formats.filter(f => !(f.itag === 140 && !f.isDrc)) };
  assert.equal(sabrSession(drcOnly, capture, { audioItag: 140 }), null);
});
