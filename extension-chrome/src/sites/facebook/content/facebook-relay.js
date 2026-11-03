// Bengal DM - Facebook media relay (content script)
// Validates and forwards the page's DASH variants to the in-page download widget.
(() => {
  const MAX_URL = 16384, MAX_VARIANTS = 100;
  const text = (value, max = 200) => String(value || '').slice(0, max);
  const number = value => {
    const n = Number(value);
    return Number.isFinite(n) && n > 0 ? n : 0;
  };
  const safeUrl = value => {
    const raw = typeof value === 'string' ? value : '';
    if (!raw || raw.length > MAX_URL) return '';
    try {
      const url = new URL(raw);
      return /^https?:$/.test(url.protocol) && url.hostname ? url.href : '';
    } catch {
      return '';
    }
  };

  function cleanVariant(item) {
    if (!item || typeof item !== 'object') return null;
    const url = safeUrl(item.url);
    if (!url) return null;
    return {
      id: text(item.id, 80),
      url,
      width: number(item.width),
      height: number(item.height),
      bandwidth: number(item.bandwidth) || number(item.bitrate),
      bitrate: number(item.bitrate) || number(item.bandwidth),
      mimeType: text(item.mimeType, 120),
      codecs: text(item.codecs, 200),
      audioUrl: safeUrl(item.audioUrl),
      audioBitrate: number(item.audioBitrate),
      badge: text(item.badge, 40),
      quality: text(item.quality, 160),
      label: text(item.label, 160),
      audioState: text(item.audioState, 40)
    };
  }

  function clean(data) {
    if (!data || typeof data !== 'object' || data.platform !== 'facebook') return null;
    const variants = [];
    for (const item of (Array.isArray(data.variants) ? data.variants : [])) {
      const variant = cleanVariant(item);
      if (variant) variants.push(variant);
      if (variants.length >= MAX_VARIANTS) break;
    }
    const audioUrl = safeUrl(data.audioUrl);
    const rawAudio = data.audio && typeof data.audio === 'object' ? data.audio : null;
    const audio = audioUrl ? {
      url: audioUrl,
      bitrate: number(rawAudio && rawAudio.bitrate),
      quality: text(rawAudio && rawAudio.quality, 160),
      label: text(rawAudio && rawAudio.label, 160),
      mimeType: text(rawAudio && rawAudio.mimeType, 120),
      codecs: text(rawAudio && rawAudio.codecs, 200),
      ext: text(rawAudio && rawAudio.ext, 12)
    } : null;
    return {
      platform: 'facebook',
      videoId: /^\d{5,30}$/.test(String(data.videoId || '')) ? String(data.videoId) : '',
      canonicalUrl: safeUrl(data.canonicalUrl),
      title: text(data.title, 300),
      duration: number(data.duration),
      width: number(data.width),
      height: number(data.height),
      isHD: !!data.isHD,
      maxHeight: number(data.maxHeight),
      resolutions: variants.map(v => v.height).filter(Boolean),
      variants,
      audio,
      audioUrl,
      hdUrl: safeUrl(data.hdUrl),
      sdUrl: safeUrl(data.sdUrl)
    };
  }

  window.addEventListener('message', event => {
    if (event.source !== window || !event.data || event.data.type !== 'bdm-facebook-media') return;
    const data = clean(event.data.data);
    if (!data) return;
    window.postMessage({ type: '__BDM_MEDIA_INFO__', data }, '*');
  }, true);
})();
