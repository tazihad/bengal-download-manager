// Bengal DM - Direct (progressive) format capture bridge (MAIN world)
// Reads YouTube's player response and reports muxed formats that need no muxing.
(function () {
  const host = window.location.hostname.toLowerCase();
  const isYouTube = host === 'youtube.com' || host.endsWith('.youtube.com') || host === 'youtu.be';
  if (!isYouTube) return;

  let lastSignature = '';

  function getPlayerResponse() {
    try {
      const player = document.getElementById('movie_player') || document.querySelector('.html5-video-player');
      if (player && typeof player.getPlayerResponse === 'function') {
        const response = player.getPlayerResponse();
        if (response && response.streamingData) return response;
      }
    } catch (e) {}

    try {
      if (window.ytInitialPlayerResponse && window.ytInitialPlayerResponse.streamingData) {
        return window.ytInitialPlayerResponse;
      }
    } catch (e) {}

    try {
      const args = window.ytplayer && window.ytplayer.config && window.ytplayer.config.args;
      if (args && args.player_response) {
        return JSON.parse(args.player_response);
      }
    } catch (e) {}

    return null;
  }

  function getDirectUrl(format) {
    if (format && typeof format.url === 'string' && /^https?:\/\//i.test(format.url)) {
      // Range/segment URLs only fetch a fragment (a few KB), so they are not usable here.
      if (/[?&](range|rn|rbuf|sq|sabr|bytestart|byteend)=/i.test(format.url)) return '';
      return format.url;
    }
    // signatureCipher-only formats require deciphering, which is Standard mode's job.
    return '';
  }

  function collectFormats() {
    const response = getPlayerResponse();
    if (!response || !response.streamingData) return;

    const streaming = response.streamingData;
    const formats = [];

    for (const format of (streaming.formats || [])) {
      const url = getDirectUrl(format);
      if (!url) continue;
      formats.push({
        itag: format.itag || 0,
        url: url,
        mimeType: String(format.mimeType || ''),
        qualityLabel: format.qualityLabel || (format.height ? `${format.height}p` : ''),
        height: Number(format.height || 0),
        contentLength: Number(format.contentLength || 0),
        hasAudio: true,
        isAudioOnly: false
      });
    }

    for (const format of (streaming.adaptiveFormats || [])) {
      const mimeType = String(format.mimeType || '');
      if (!mimeType.toLowerCase().startsWith('audio/')) continue;
      const url = getDirectUrl(format);
      if (!url) continue;
      formats.push({
        itag: format.itag || 0,
        url: url,
        mimeType: mimeType,
        qualityLabel: 'Audio',
        height: 0,
        contentLength: Number(format.contentLength || 0),
        hasAudio: true,
        isAudioOnly: true
      });
    }

    if (!formats.length) return;

    const videoId = (response.videoDetails && response.videoDetails.videoId) || '';
    const signature = videoId + ':' + formats.map(f => f.itag).join(',');
    if (signature === lastSignature) return;
    lastSignature = signature;

    window.postMessage({
      type: '__BDM_DIRECT_FORMATS__',
      videoId: videoId,
      formats: formats
    }, '*');
  }

  window.addEventListener('message', function (event) {
    if (event.source !== window) return;
    if (event.data && event.data.type === '__BDM_GET_DIRECT_FORMATS__') {
      lastSignature = '';
      collectFormats();
    }
  });

  document.addEventListener('yt-navigate-finish', () => setTimeout(collectFormats, 500));
  document.addEventListener('yt-page-data-updated', () => setTimeout(collectFormats, 500));

  setInterval(collectFormats, 4000);
  setTimeout(collectFormats, 800);
})();
