// Bengal DM - YouTube & Facebook Media Bridge (Main World)
(function() {
  const host = window.location.hostname.toLowerCase();
  const isFacebook = host.includes('facebook.com') || host.includes('fb.watch') || host.includes('fb.com');

  // --- YouTube Media Info (Preserved as is) ---
  function getYouTubeMediaInfo() {
    try {
      const player = document.getElementById('movie_player') || document.querySelector('.html5-video-player');
      if (!player) return null;

      const levels = (typeof player.getAvailableQualityLevels === 'function') 
        ? player.getAvailableQualityLevels() 
        : [];

      const videoData = (typeof player.getVideoData === 'function') 
        ? player.getVideoData() 
        : {};

      const duration = (typeof player.getDuration === 'function') 
        ? player.getDuration() 
        : 0;

      return {
        levels: Array.isArray(levels) ? levels : [],
        title: videoData.title || document.title,
        author: videoData.author || "",
        videoId: videoData.video_id || "",
        duration: duration || 0
      };
    } catch (e) {
      return null;
    }
  }

  // --- Facebook Media & Resolution Detection (Special Facebook Case - IDM Method) ---
  let fbMetadataCache = new Map(); // videoId -> metadata

  function parseDashManifestHeights(xmlText) {
    if (!xmlText || typeof xmlText !== 'string' || !xmlText.includes('<Representation')) return null;
    const heights = new Set();
    const heightRegex = /height=["'](\d+)["']/gi;
    let match;
    while ((match = heightRegex.exec(xmlText)) !== null) {
      const h = parseInt(match[1], 10);
      if (h && h >= 144 && h <= 4320) heights.add(h);
    }
    if (heights.size === 0) return null;
    return Array.from(heights).sort((a, b) => b - a);
  }

  function getReactFiber(element) {
    if (!element) return null;
    for (const key of Object.keys(element)) {
      if (key.startsWith('__reactFiber$') || key.startsWith('__reactInternalInstance$')) {
        return element[key];
      }
    }
    return null;
  }

  // Only hook network calls if on Facebook
  if (isFacebook) {
    // Intercept Facebook GraphQL responses for video metadata & DASH manifests
    function inspectFacebookResponse(url, text) {
      if (!text || typeof text !== 'string') return;
      if (text.includes('dash_manifest') || url.includes('/api/graphql/')) {
        try {
          const json = JSON.parse(text);
          const queue = [json];
          let depth = 0;
          while (queue.length > 0 && depth < 100) {
            depth++;
            const curr = queue.shift();
            if (!curr || typeof curr !== 'object') continue;

            if (typeof curr.dash_manifest === 'string') {
              const heights = parseDashManifestHeights(curr.dash_manifest);
              const vId = curr.id || curr.video_id || curr.videoFBID;
              if (heights && vId) {
                fbMetadataCache.set(String(vId), {
                  resolutions: heights,
                  maxHeight: heights[0],
                  isHD: heights.some(h => h >= 720),
                  hdUrl: curr.playable_url_quality_hd || curr.browser_native_hd_url,
                  sdUrl: curr.playable_url_quality_sd || curr.browser_native_sd_url
                });
              }
            }
            for (const k of Object.keys(curr)) {
              if (curr[k] && typeof curr[k] === 'object') queue.push(curr[k]);
            }
          }
        } catch (e) {}
      }
    }

    if (typeof window.fetch === 'function') {
      const origFetch = window.fetch;
      window.fetch = function(...args) {
        const promise = origFetch.apply(this, args);
        try {
          const url = (args[0] instanceof Request) ? args[0].url : String(args[0] || '');
          if (url.includes('/api/graphql/') || url.includes('video') || url.includes('manifest')) {
            promise.then(response => {
              try {
                if (response && response.ok) {
                  const clone = response.clone();
                  clone.text().then(text => inspectFacebookResponse(url, text)).catch(() => {});
                }
              } catch (e) {}
            }).catch(() => {});
          }
        } catch (e) {}
        return promise;
      };
    }

    if (typeof window.XMLHttpRequest === 'function') {
      const origOpen = XMLHttpRequest.prototype.open;
      const origSend = XMLHttpRequest.prototype.send;
      XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        this.__bdm_url = String(url || '');
        return origOpen.apply(this, [method, url, ...rest]);
      };
      XMLHttpRequest.prototype.send = function(...args) {
        const url = this.__bdm_url;
        if (url && (url.includes('/api/graphql/') || url.includes('video'))) {
          this.addEventListener('load', function() {
            try {
              if (this.status >= 200 && this.status < 300 && this.responseText) {
                inspectFacebookResponse(url, this.responseText);
              }
            } catch (e) {}
          });
        }
        return origSend.apply(this, args);
      };
    }
  }

  function getFacebookMediaInfo(video) {
    if (!video) return null;
    let videoFBID = null;
    let dashManifest = null;
    let isHD = false;
    let dimensions = null;
    let hdUrl = null;
    let sdUrl = null;
    let duration = video.duration || 0;

    try {
      // Traverse React Fiber nodes up to 15 levels (the exact IDM coreVideoPlayerMetaData pattern)
      let curr = video;
      for (let depth = 0; depth < 15 && curr; depth++) {
        const fiber = getReactFiber(curr);
        if (fiber) {
          let f = fiber;
          for (let fDepth = 0; fDepth < 12 && f; fDepth++) {
            const props = f.memoizedProps;
            if (props) {
              const meta = props.coreVideoPlayerMetaData ||
                           (props.videoPlayerConfig && props.videoPlayerConfig.coreVideoPlayerMetaData) ||
                           (props.videoData && props.videoData.coreVideoPlayerMetaData);

              if (meta) {
                if (meta.videoFBID) videoFBID = String(meta.videoFBID);
                if (meta.dash_manifest || meta.dashManifest) dashManifest = meta.dash_manifest || meta.dashManifest;
                if (meta.isHD || meta.hdSrc || meta.playableUrlQualityHD || meta.playable_url_quality_hd) isHD = true;
                if (meta.hdSrc || meta.playableUrlQualityHD || meta.playable_url_quality_hd) {
                  hdUrl = meta.hdSrc || meta.playableUrlQualityHD || meta.playable_url_quality_hd;
                }
                if (meta.sdSrc || meta.playableUrlQualitySD || meta.playable_url_quality_sd) {
                  sdUrl = meta.sdSrc || meta.playableUrlQualitySD || meta.playable_url_quality_sd;
                }
                if (meta.dimensions) dimensions = meta.dimensions;
                if (meta.duration && !duration) duration = meta.duration;
                break;
              }

              if (props.videoFBID && !videoFBID) videoFBID = String(props.videoFBID);
              if (props.video_id && !videoFBID) videoFBID = String(props.video_id);
              if (props.playableUrlQualityHD || props.playable_url_quality_hd || props.hdSrc) isHD = true;
            }
            f = f.return;
          }
        }
        if (videoFBID && (dashManifest || isHD)) break;
        curr = curr.parentElement;
      }
    } catch (e) {}

    // Check cached network metadata if videoFBID was found
    let parsedHeights = null;
    if (dashManifest) {
      parsedHeights = parseDashManifestHeights(dashManifest);
    } else if (videoFBID && fbMetadataCache.has(videoFBID)) {
      const cached = fbMetadataCache.get(videoFBID);
      parsedHeights = cached.resolutions;
      if (cached.isHD) isHD = true;
      if (cached.hdUrl && !hdUrl) hdUrl = cached.hdUrl;
      if (cached.sdUrl && !sdUrl) sdUrl = cached.sdUrl;
    }

    const resSet = new Set();
    if (Array.isArray(parsedHeights)) {
      parsedHeights.forEach(h => resSet.add(h));
      if (parsedHeights.some(h => h >= 720)) isHD = true;
    }

    const dimHeight = (dimensions && (dimensions.height || dimensions.videoHeight)) ||
                      Math.max(video.videoHeight, video.videoWidth) || 0;
    if (dimHeight >= 720) isHD = true;

    // Ensure full tiers if HD is detected
    if (isHD || dimHeight >= 720) {
      if (dimHeight >= 1080 || !dimHeight) resSet.add(1080);
      resSet.add(720);
      resSet.add(480);
      resSet.add(360);
    } else if (resSet.size === 0) {
      resSet.add(480);
      resSet.add(360);
    }

    const resolutions = Array.from(resSet).sort((a, b) => b - a);
    return {
      platform: 'facebook',
      videoId: videoFBID || "",
      canonicalUrl: videoFBID ? `https://www.facebook.com/watch/?v=${videoFBID}` : null,
      resolutions: resolutions,
      maxHeight: resolutions[0] || (isHD ? 1080 : 720),
      isHD: isHD || (resolutions[0] >= 720),
      duration: duration || 0,
      title: document.title,
      hdUrl: hdUrl,
      sdUrl: sdUrl
    };
  }

  // --- Master Reporting Function ---
  function reportMediaInfo() {
    let info = null;
    if (host.includes('youtube.com') || host.includes('youtu.be')) {
      info = getYouTubeMediaInfo();
    } else if (isFacebook) {
      const activeVideo = document.querySelector('video[data-bdm-active="true"]') ||
                          Array.from(document.querySelectorAll('video')).find(v => !v.paused && !v.ended && v.readyState > 1) ||
                          document.querySelector('video');
      info = getFacebookMediaInfo(activeVideo);
    }

    if (info) {
      window.postMessage({
        type: '__BDM_MEDIA_INFO__',
        data: info
      }, '*');
    }
  }

  window.addEventListener('message', function(event) {
    if (event.source !== window) return;
    if (event.data && event.data.type === '__BDM_GET_MEDIA_INFO__') {
      reportMediaInfo();
    }
  });

  // Watch for player events or state changes
  setInterval(reportMediaInfo, 2500);
})();
