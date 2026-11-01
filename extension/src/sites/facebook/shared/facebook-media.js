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

  /**
   * Facebook's own video id from a page URL (/reel/, /videos/, watch/?v=). Used to bind a
   * captured manifest to the video the user is actually looking at.
   */
  function videoIdFromUrl(value) {
    const raw = String(value || '');
    const match = raw.match(/\/reel(?:s)?\/(\d{5,30})/i) ||
      raw.match(/\/videos\/[^/?#]*?\/?(\d{5,30})/i) ||
      raw.match(/[?&]v=(\d{5,30})/i);
    return match ? match[1] : '';
  }

  function isVideoId(value) {
    return /^\d{5,30}$/.test(String(value || ''));
  }

  /**
   * Facebook's id for a <video> element, read from the closest wrapper that names a
   * single clip. A feed wrapper can list many posts, so a container is only trusted
   * while it holds exactly one <video> (or a single reel/watch permalink next to it).
   */
  function videoIdFromElement(video) {
    if (!video) return '';
    const own = [
      video.dataset && video.dataset.videoFbid,
      video.dataset && video.dataset.videoId,
      video.getAttribute && video.getAttribute('data-video-id'),
      video.getAttribute && video.getAttribute('data-videoid')
    ];
    for (const id of own) if (isVideoId(id)) return String(id);

    let node = video.parentElement;
    for (let depth = 0; depth < 12 && node; depth++, node = node.parentElement) {
      const named = [
        node.getAttribute && node.getAttribute('data-video-id'),
        node.getAttribute && node.getAttribute('data-videoid'),
        node.dataset && node.dataset.videoId,
        node.dataset && node.dataset.videoFbid
      ];
      let videos = null;
      for (const id of named) {
        if (!isVideoId(id)) continue;
        if (!videos) videos = safeQuery(node, 'video');
        if (!videos || videos.length === 1) return String(id);
      }
      if (!node.querySelectorAll) continue;
      const links = safeQuery(node, 'a[href*="/reel/"], a[href*="/videos/"], a[href*="/watch"], a[href*="?v="]');
      if (!links || !links.length) continue;
      const videosInNode = safeQuery(node, 'video');
      if (videosInNode && videosInNode.length > 1) continue;
      for (const link of links) {
        const id = videoIdFromUrl(link.href || (link.getAttribute && link.getAttribute('href')) || '');
        if (id) return id;
      }
    }
    return '';
  }

  function safeQuery(node, selector) {
    try {
      return node.querySelectorAll(selector);
    } catch {
      return null;
    }
  }

  /**
   * How well a manifest describes the clip currently in the player. Facebook preloads
   * neighbouring reels, so the element's own duration (and the rendition it is playing)
   * is what tells two clips apart when no video id could be captured. Returns -1 when
   * the manifest clearly belongs to a different video, 0 when nothing is known yet.
   */
  function manifestScore(manifest, video) {
    if (!manifest || !video) return -1;
    const seconds = Number(video.duration);
    const offered = Number(manifest.duration);
    let score = 0;
    if (isFinite(seconds) && seconds > 0 && offered > 0) {
      const delta = Math.abs(seconds - offered);
      if (delta > 2) return -1;
      score += 100 - Math.round(delta * 10);
    }
    const height = Number(video.height) || 0;
    const heights = new Set((manifest.video || []).map(rep => Number(rep.height) || 0).filter(Boolean));
    if (height && heights.size) {
      if (heights.has(height)) {
        score += 50;
      } else {
        const nearest = Math.min(...Array.from(heights, value => Math.abs(value - height)));
        if (nearest > Math.max(96, Math.round(height * 0.2))) return -1;
        score += 20;
      }
    }
    return score;
  }

  function manifestFits(manifest, video) {
    return manifestScore(manifest, video) >= 0;
  }

  /**
   * Picks the manifest that belongs to the player's clip out of the manifests Facebook
   * preloaded. Candidates should be ordered newest first; two different clips with the
   * same length and rendition cannot be told apart, so that case returns null instead
   * of guessing (which would offer another reel's URLs).
   */
  function pickManifest(candidates, video) {
    let best = null, bestScore = 0;
    let tied = false;
    for (const manifest of candidates || []) {
      if (!manifest || manifest === best) continue;
      const score = manifestScore(manifest, video);
      if (score <= 0) continue;
      if (score > bestScore) {
        best = manifest;
        bestScore = score;
        tied = false;
      } else if (score === bestScore) {
        tied = true;
      }
    }
    if (!tied) return best;
    // Equal score means equal length and rendition: usually the same manifest captured
    // twice, which is safe to use. If the player's length is unknown the clips really
    // cannot be told apart, so report nothing rather than another reel's URLs.
    const known = Number(video && video.duration) > 0;
    return known ? best : null;
  }

  const MANIFEST_KEY_RE = /dash_manifest|dashManifest|dash_manifests|video_dash_manifest|dash_manifest_xml_string/i;
  const MANIFEST_VALUE_RE = /"(dash_manifest|dashManifest|video_dash_manifest|dash_manifest_xml_string)"\s*:\s*"((?:\\.|[^"\\])*)"/g;
  const MANIFEST_LIST_RE = /"dash_manifests"\s*:\s*(\[[\s\S]*?\])/g;
  const ID_KEYS = ['videoFBID', 'video_id', 'videoId', 'video_fbid'];
  // Facebook's DASH payload names the owning video with a plain "id"
  // (media/videoDeliveryLegacyFields -> { dash_manifest_xml_string, id }). It is only
  // trusted on the object that directly holds the manifest: everywhere else "id" names
  // posts, comments and users, and would bind someone else's manifest to this clip.
  const MANIFEST_ID_KEYS = ID_KEYS.concat(['id']);
  const ID_PATTERNS = ID_KEYS.map(key => new RegExp(`"${key}"\\s*:\\s*"?(\\d{5,30})"?`, 'g'));
  const OWNER_ID_PATTERN = /"id"\s*:\s*"?(\d{5,30})"?/g;
  const MANIFEST_KEYS = new Set(['dash_manifest', 'dashManifest', 'video_dash_manifest', 'dash_manifest_xml_string']);
  const MAX_PAYLOAD = 4 * 1024 * 1024, MAX_MANIFESTS = 60, MAX_ID_WINDOW = 12000;
  // GraphQL payloads nest the video ~18 levels deep, so the walk must not stop early.
  const MAX_DEPTH = 48, MAX_JSON_BLOCKS = 200, MAX_JSON_PAYLOADS = 12, OWNER_ID_WINDOW = 2500;
  // After the manifest string the owner object may still list its URLs before its "id".
  const OWNER_ID_AFTER_WINDOW = 8000;

  function decodeJsonString(raw) {
    try {
      return JSON.parse('"' + raw + '"');
    } catch {
      return '';
    }
  }

  function addUnique(list, value) {
    if (!list.includes(value)) list.push(value);
  }

  function idsOf(object, keys = ID_KEYS) {
    const ids = [];
    if (!object || typeof object !== 'object') return ids;
    for (const key of keys) {
      const id = object[key];
      if (isVideoId(id)) addUnique(ids, String(id));
    }
    return ids;
  }

  /** Ids of the object that directly holds a manifest (its plain "id" is the video's). */
  function ownerIdsOf(object) {
    return idsOf(object, MANIFEST_ID_KEYS);
  }

  function collectJson(value, add, depth = 0, inherited = []) {
    if (!value || typeof value !== 'object' || depth > MAX_DEPTH) return;
    const ids = inherited.slice();
    for (const id of idsOf(value)) addUnique(ids, id);
    for (const key of Object.keys(value)) {
      const child = value[key];
      if (MANIFEST_KEYS.has(key) && typeof child === 'string' && child.length > 64) {
        // The object holding the manifest may name its video with a plain "id".
        const ownerIds = ids.slice();
        for (const id of ownerIdsOf(value)) addUnique(ownerIds, id);
        add(child, ownerIds);
      } else if (key === 'dash_manifests' && Array.isArray(child)) {
        for (const entry of child) {
          if (entry && typeof entry.manifest_xml === 'string') {
            const entryIds = ids.slice();
            for (const id of ownerIdsOf(entry)) addUnique(entryIds, id);
            add(entry.manifest_xml, entryIds);
          }
        }
      } else if (child && typeof child === 'object') {
        collectJson(child, add, depth + 1, ids);
      }
    }
  }

  function jsonPayloads(text) {
    const payloads = [];
    const trimmed = text.trim();
    const candidates = [trimmed];
    const prefix = trimmed.match(/^(?:for\s*\(\s*;;\s*\)\s*;|while\s*\(\s*1\s*\)\s*;|\)\]\}',?\s*)/);
    if (prefix) candidates.push(trimmed.slice(prefix[0].length));
    for (const candidate of candidates) {
      if (!candidate.startsWith('{') && !candidate.startsWith('[')) continue;
      try {
        payloads.push(JSON.parse(candidate));
        break;
      } catch {}
    }
    // A watch/reel page embeds dozens of JSON blocks before the one carrying the DASH
    // manifest, so only blocks that mention a manifest are parsed (and counted).
    const scriptRe = /<script[^>]*type=["']application\/json["'][^>]*>([\s\S]*?)<\/script>/gi;
    let match, blocks = 0;
    while ((match = scriptRe.exec(text)) !== null && blocks < MAX_JSON_BLOCKS && payloads.length < MAX_JSON_PAYLOADS) {
      blocks++;
      if (!MANIFEST_KEY_RE.test(match[1])) continue;
      try {
        payloads.push(JSON.parse(match[1]));
      } catch {}
    }
    return payloads;
  }

  /** The id that sits closest to a manifest inside a non-JSON (HTML) payload. */
  function nearestId(text, index) {
    const start = Math.max(0, index - MAX_ID_WINDOW);
    const end = Math.min(text.length, index + MAX_ID_WINDOW);
    const windowText = text.slice(start, end);
    let best = '', bestDistance = Infinity;
    for (const re of ID_PATTERNS) {
      re.lastIndex = 0;
      let match;
      while ((match = re.exec(windowText)) !== null) {
        const distance = Math.abs(start + match.index - index);
        if (distance < bestDistance) {
          best = match[1];
          bestDistance = distance;
        }
      }
    }
    return best;
  }

  /**
   * HTML fallback for payloads the JSON walk cannot parse: explicit video keys first, then
   * the owner object's plain "id" within a short window. `valueEnd` lets the search continue
   * just past the manifest string, where the owner object may place its "id" key.
   */
  function nearestOwnerId(text, index, valueEnd = index) {
    const id = nearestId(text, index);
    if (id) return id;
    let best = '', bestDistance = Infinity;
    const scan = (from, to) => {
      if (to <= from) return;
      const windowText = text.slice(from, to);
      OWNER_ID_PATTERN.lastIndex = 0;
      let match;
      while ((match = OWNER_ID_PATTERN.exec(windowText)) !== null) {
        const distance = Math.abs(from + match.index - index);
        if (distance < bestDistance) {
          best = match[1];
          bestDistance = distance;
        }
      }
    };
    scan(Math.max(0, index - OWNER_ID_WINDOW), index);
    scan(valueEnd, Math.min(text.length, valueEnd + OWNER_ID_AFTER_WINDOW));
    return best;
  }

  /**
   * Finds every embedded MPD in a GraphQL/HTML payload and pairs it with the ids found
   * in the same JSON object. Manifests that cannot be attributed are still returned
   * (with no ids) so the caller can match them to a clip by duration and rendition.
   */
  function manifestsInText(text) {
    if (typeof text !== 'string' || text.length < 64 || text.length > MAX_PAYLOAD) return [];
    if (!MANIFEST_KEY_RE.test(text)) return [];
    const found = [], seen = new Set();
    const add = (xml, ids) => {
      if (typeof xml !== 'string' || xml.length < 64 || found.length >= MAX_MANIFESTS) return;
      // Facebook manifests share a long XML header, so compare the head, tail and length:
      // two different videos must not collapse into one just because their MPDs look alike.
      const key = `${xml.length}:${xml.slice(0, 400)}:${xml.slice(-200)}`;
      if (seen.has(key)) return;
      seen.add(key);
      const clean = [];
      for (const id of ids || []) if (isVideoId(id)) addUnique(clean, String(id));
      found.push({ xml, ids: clean });
    };

    for (const payload of jsonPayloads(text)) collectJson(payload, add);

    MANIFEST_VALUE_RE.lastIndex = 0;
    let match;
    while ((match = MANIFEST_VALUE_RE.exec(text)) !== null && found.length < MAX_MANIFESTS) {
      const xml = decodeJsonString(match[2]);
      const id = xml ? nearestOwnerId(text, match.index, match.index + match[0].length) : '';
      add(xml, id ? [id] : []);
    }
    MANIFEST_LIST_RE.lastIndex = 0;
    while ((match = MANIFEST_LIST_RE.exec(text)) !== null && found.length < MAX_MANIFESTS) {
      let list;
      try {
        list = JSON.parse(match[1]);
      } catch {
        continue;
      }
      const id = nearestOwnerId(text, match.index, match.index + match[0].length);
      for (const entry of Array.isArray(list) ? list : []) {
        if (!entry || typeof entry.manifest_xml !== 'string') continue;
        const entryIds = ownerIdsOf(entry);
        add(entry.manifest_xml, entryIds.length ? entryIds : (id ? [id] : []));
      }
    }
    return found;
  }

  root.bdmFacebook = {
    parseManifest, mergeManifest, variants, audioChoice, bestAudio, wholeFileUrl, formatRate,
    videoIdFromUrl, isVideoId, videoIdFromElement, manifestScore, manifestFits, pickManifest,
    manifestsInText
  };
  if (typeof module !== 'undefined') module.exports = root.bdmFacebook;
})(globalThis);
