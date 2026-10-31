// Bengal DM - Facebook DASH manifest parser
// Facebook publishes every rendition of a video as a DASH <Representation>. Several
// entries can share the same height (e.g. two 720p streams at different bitrates), so
// the chooser lists each representation with its real resolution and bandwidth instead
// of inventing fixed 1080/720/480 tiers.
(function (root) {
  const MAX_URL = 16384, MAX_ATTRIBUTES = 64, MAX_REPRESENTATIONS = 200;
  const WHOLE_FILE_PARAMS = ['range', 'rn', 'rbuf', 'sq', 'sabr', 'bytestart', 'byteend'];

  const text = (value, max = 200) => String(value || '').slice(0, max);
  const integer = value => {
    const n = Number(value);
    return Number.isSafeInteger(n) && n > 0 ? n : 0;
  };

  function decodeEntities(value) {
    return String(value || '')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"')
      .replace(/&#39;|&apos;/g, "'");
  }

  function attributes(raw) {
    const attrs = {};
    if (!raw) return attrs;
    const re = /([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')/g;
    let match, count = 0;
    while ((match = re.exec(raw)) !== null && count < MAX_ATTRIBUTES) {
      attrs[match[1]] = decodeEntities(match[2] !== undefined ? match[2] : match[3]);
      count++;
    }
    return attrs;
  }

  function wholeFileUrl(value) {
    let raw = decodeEntities(value).trim();
    if (!raw) return null;
    if (raw.startsWith('//')) raw = 'https:' + raw;
    try {
      const url = new URL(raw);
      if (url.protocol !== 'https:' && url.protocol !== 'http:') return null;
      if (!url.hostname || url.username || url.password) return null;
      if (/\.(m3u8|mpd|m4s|ts|m2ts|html?)$/i.test(url.pathname)) return null;
      for (const key of WHOLE_FILE_PARAMS) url.searchParams.delete(key);
      const href = url.href;
      return href.length <= MAX_URL ? href : null;
    } catch {
      return null;
    }
  }

  function durationSeconds(value) {
    const match = String(value || '').match(/^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?)?$/i);
    if (!match) return 0;
    return integer(match[1]) * 86400 + integer(match[2]) * 3600 + integer(match[3]) * 60 + Number(match[4] || 0);
  }

  function representationKind(attrs) {
    const mime = text(attrs.mimeType || attrs.contentType, 120).toLowerCase();
    const codecs = text(attrs.codecs, 200).toLowerCase();
    if (mime.startsWith('video/')) return 'video';
    if (mime.startsWith('audio/')) return 'audio';
    if (attrs.height || attrs.width) return 'video';
    if (/^(avc|hev|hvc|vp0?8|vp0?9|av01|dvh|dva)/.test(codecs)) return 'video';
    if (/^(mp4a|opus|vorbis|ac-3|ec-3|flac)/.test(codecs)) return 'audio';
    return '';
  }

  function cleanRepresentation(attrs, body, kind) {
    const baseMatch = body.match(/<BaseURL[^>]*>([\s\S]*?)<\/BaseURL>/i);
    const url = wholeFileUrl(baseMatch ? baseMatch[1] : '');
    if (!url) return null;
    const width = integer(attrs.width);
    const height = integer(attrs.height);
    const bandwidth = integer(attrs.bandwidth);
    return {
      id: text(attrs.id, 80),
      url,
      width,
      height,
      bandwidth,
      mimeType: text(attrs.mimeType || attrs.contentType, 120),
      codecs: text(attrs.codecs, 200),
      kind
    };
  }

  function pushUnique(list, item) {
    if (!item || list.some(existing => existing.url === item.url)) return;
    if (list.length < MAX_REPRESENTATIONS) list.push(item);
  }

  /**
   * Parses a Facebook MPD string. Returns {video, audio, duration} with one entry per
   * usable <Representation>, or null when the document carries no whole-file streams
   * (segment-template manifests cannot be fetched as a single file).
   */
  function parseManifest(xml) {
    if (typeof xml !== 'string' || xml.length < 64 || !/<MPD[\s>]/i.test(xml)) return null;
    const mpdAttrs = attributes((xml.match(/<MPD\b([^>]*)>/i) || [])[1]);
    const video = [], audio = [];
    const consume = (setAttrs, block) => {
      const re = /<Representation\b([^>]*?)(?:\/>|>([\s\S]*?)<\/Representation>)/gi;
      let match;
      while ((match = re.exec(block)) !== null) {
        const attrs = Object.assign({}, setAttrs, attributes(match[1]));
        const kind = representationKind(attrs);
        if (!kind) continue;
        pushUnique(kind === 'video' ? video : audio, cleanRepresentation(attrs, match[2] || '', kind));
      }
    };

    const setRe = /<AdaptationSet\b([^>]*)>([\s\S]*?)<\/AdaptationSet>/gi;
    let setMatch, sets = 0;
    while ((setMatch = setRe.exec(xml)) !== null) {
      sets++;
      consume(attributes(setMatch[1]), setMatch[2]);
    }
    if (sets === 0) consume({}, xml);

    video.sort((a, b) => b.height - a.height || b.bandwidth - a.bandwidth || b.width - a.width);
    audio.sort((a, b) => b.bandwidth - a.bandwidth);
    if (!video.length && !audio.length) return null;
    return { video, audio, duration: durationSeconds(mpdAttrs.mediaPresentationDuration) };
  }

  function mergeManifest(target, parsed) {
    if (!parsed) return target;
    if (!target) target = { video: [], audio: [], duration: 0 };
    for (const rep of parsed.video) pushUnique(target.video, rep);
    for (const rep of parsed.audio) pushUnique(target.audio, rep);
    if (!target.duration && parsed.duration) target.duration = parsed.duration;
    target.video.sort((a, b) => b.height - a.height || b.bandwidth - a.bandwidth || b.width - a.width);
    target.audio.sort((a, b) => b.bandwidth - a.bandwidth);
    return target.video.length || target.audio.length ? target : null;
  }

  function bestAudio(manifest) {
    if (!manifest || !Array.isArray(manifest.audio) || !manifest.audio.length) return null;
    const ranked = manifest.audio.slice().sort((a, b) => {
      const aMp4 = /^audio\/mp4/i.test(a.mimeType) ? 1 : 0;
      const bMp4 = /^audio\/mp4/i.test(b.mimeType) ? 1 : 0;
      return bMp4 - aMp4 || b.bandwidth - a.bandwidth;
    });
    return ranked[0];
  }

  function formatRate(bitsPerSecond) {
    const bps = integer(bitsPerSecond);
    if (!bps) return '';
    if (bps >= 1000000) return `${String(Number((bps / 1000000).toFixed(2)))} Mbps`;
    return `${Math.round(bps / 1000)} kbps`;
  }

  function videoLabel(rep) {
    const size = rep.width && rep.height ? `${rep.width}\u00d7${rep.height}` : (rep.height ? `${rep.height}p` : '');
    const rate = formatRate(rep.bandwidth);
    return [size, rate].filter(Boolean).join(' \u00b7 ');
  }

  /**
   * One download choice per video representation. Every choice carries the best audio
   * track so the desktop can mux it and never saves a silent video.
   */
  function variants(manifest) {
    if (!manifest || !Array.isArray(manifest.video) || !manifest.video.length) return null;
    const audio = bestAudio(manifest);
    return manifest.video.map(rep => {
      const rate = formatRate(rep.bandwidth);
      const heightLabel = rep.height ? `${rep.height}p` : 'MP4';
      return {
        id: rep.id,
        url: rep.url,
        width: rep.width,
        height: rep.height,
        bandwidth: rep.bandwidth,
        bitrate: rep.bandwidth,
        mimeType: rep.mimeType,
        codecs: rep.codecs,
        audioUrl: audio ? audio.url : '',
        audioBitrate: audio ? audio.bandwidth : 0,
        audioCodecs: audio ? audio.codecs : '',
        badge: heightLabel,
        quality: [heightLabel, rate].filter(Boolean).join(' \u00b7 '),
        label: videoLabel(rep),
        audioState: audio ? 'Video + audio' : 'Video only'
      };
    });
  }

  function audioChoice(manifest) {
    const audio = bestAudio(manifest);
    if (!audio) return null;
    const rate = formatRate(audio.bandwidth);
    const ext = /webm/i.test(audio.mimeType) ? '.webm' : '.m4a';
    return {
      url: audio.url,
      bitrate: audio.bandwidth,
      badge: 'AUDIO',
      quality: ['Audio only', rate].filter(Boolean).join(' \u00b7 '),
      label: ['Audio only', rate].filter(Boolean).join(' \u00b7 '),
      mimeType: audio.mimeType,
      codecs: audio.codecs,
      ext
    };
  }

  root.bdmFacebook = {
    parseManifest, mergeManifest, variants, audioChoice, bestAudio, wholeFileUrl, formatRate
  };
  if (typeof module !== 'undefined') module.exports = root.bdmFacebook;
})(globalThis);
