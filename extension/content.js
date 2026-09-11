// Tonec IDM Pattern: Content scripts do NOT hijack or preventDefault anchor link clicks.
// Direct downloads and navigations are cleanly handled at the network level in background.js
// via HTTP response headers (webRequest.onHeadersReceived) and browser download events
// (chrome.downloads.onCreated / onDeterminingFilename). This guarantees that web pages,
// landing pages with captchas/countdowns (e.g. datanodes.to, rapidgator), and single-page apps
// navigate naturally without opening blank tabs or triggering popup blockers.

// =========================================================================
// Bengal DM - IDM-Style Floating Video Downloader System
// =========================================================================
(function initBengalDMVideoWidget() {
  if (window.__bengalDmVideoWidgetLoaded) return;
  window.__bengalDmVideoWidgetLoaded = true;

  let activeVideo = null;
  let isUserPositioned = false;
  let userCoords = { left: 0, top: 0 };
  let isDropdownOpen = false;
  let ytMediaInfo = null;
  const dismissedVideos = new Set();
  let activeIframeVideo = null;
  let activeIframeData = null;
  let isTopHandlingWidget = false;
  let isAppConnected = true;
  let enableMediaSniffing = true;
  let enableInterception = true;
  let blacklistUrls = [];
  let videoPanelPosition = 'top-right';

  const POPULAR_MEDIA_HOSTS = [
    'youtube.com', 'youtu.be',
    'facebook.com', 'fb.watch', 'fb.com',
    'instagram.com',
    'tiktok.com',
    'twitter.com', 'x.com',
    'reddit.com',
    'redgifs.com',
    'vimeo.com',
    'dailymotion.com',
    'twitch.tv',
    'bilibili.com',
    'soundcloud.com',
    'rumble.com',
    'kick.com',
    'streamable.com',
    'pinterest.com'
  ];

  function isPopularMediaHost(hostname) {
    const host = (hostname || window.location.hostname).toLowerCase();
    return POPULAR_MEDIA_HOSTS.some(h => host === h || host.endsWith('.' + h));
  }

  function isSiteBlacklisted() {
    if (!enableInterception) return true;
    if (!Array.isArray(blacklistUrls) || blacklistUrls.length === 0) return false;

    const candidates = [];
    if (window.location && window.location.hostname) {
      candidates.push({
        host: window.location.hostname.toLowerCase(),
        url: (window.location.href || '').toLowerCase()
      });
    }
    if (document.referrer && typeof document.referrer === 'string' && document.referrer.startsWith('http')) {
      try {
        const refUrl = new URL(document.referrer);
        candidates.push({
          host: refUrl.hostname.toLowerCase(),
          url: document.referrer.toLowerCase()
        });
      } catch (e) {}
    }

    for (const item of blacklistUrls) {
      if (!item || typeof item !== 'string') continue;
      let p = item.trim().toLowerCase();
      p = p.replace(/^https?:\/\//, '');
      if (p.startsWith('*.')) p = p.substring(2);
      else if (p.startsWith('*')) p = p.substring(1);

      const slashIdx = p.indexOf('/');
      let pHost = slashIdx !== -1 ? p.substring(0, slashIdx) : p;
      let pPath = slashIdx !== -1 ? p.substring(slashIdx + 1) : '';
      if (pHost.endsWith('/')) pHost = pHost.slice(0, -1);
      if (pHost.includes(':')) pHost = pHost.split(':')[0];

      if (!pHost) continue;

      for (const cand of candidates) {
        const hostMatches = (cand.host === pHost || cand.host.endsWith('.' + pHost));
        if (hostMatches) {
          if (pPath) {
            try {
              const parsed = new URL(cand.url);
              const pathPart = parsed.pathname.toLowerCase().replace(/^\//, '');
              if (pathPart.startsWith(pPath)) return true;
            } catch (e) {
              if (cand.url.includes('/' + pPath)) return true;
            }
          } else {
            return true;
          }
        }
      }
    }
    return false;
  }

  function getPlatformName() {
    const host = window.location.hostname.toLowerCase();
    if (host.includes('youtube.com') || host.includes('youtu.be')) return 'YouTube';
    if (host.includes('facebook.com') || host.includes('fb.watch') || host.includes('fb.com')) return 'Facebook';
    if (host.includes('instagram.com')) return 'Instagram';
    if (host.includes('tiktok.com')) return 'TikTok';
    if (host.includes('twitter.com') || host.includes('x.com')) return 'X / Twitter';
    if (host.includes('reddit.com')) return 'Reddit';
    if (host.includes('vimeo.com')) return 'Vimeo';
    if (host.includes('dailymotion.com')) return 'Dailymotion';
    if (host.includes('twitch.tv')) return 'Twitch';
    if (host.includes('bilibili.com')) return 'Bilibili';
    return 'Media';
  }

  const GENERIC_TITLES = new Set([
    'facebook', 'youtube', 'instagram', 'tiktok', 'twitter', 'x', 'reddit',
    'redgifs', 'redgif', 'vimeo', 'dailymotion', 'twitch', 'bilibili', 'video stream', 'media stream',
    'media', 'untitled', 'untitled media', 'video', 'videos', 'watch', 'index', 'master',
    'videoplayback', 'stream', 'unknown', 'post', 'status', 'clip', 'reels', 'reel'
  ]);

  function isGenericTitle(str) {
    if (!str || typeof str !== 'string') return true;
    const s = str.trim().toLowerCase();
    if (!s || s.length < 2) return true;
    if (GENERIC_TITLES.has(s)) return true;
    if (/^\(\d+\)\s*(facebook|twitter|x|instagram|notifications|reddit|redgifs)/i.test(s)) return true;
    if (/^(facebook|twitter|instagram|redgifs)\s*[-–—|]/i.test(s)) return true;
    return false;
  }

  function notifyTopFrameVideo(video, state = 'playing') {
    if (!isAppConnected || !enableMediaSniffing || isSiteBlacklisted()) return;
    if (window.self === window.top) return;
    if (dismissedVideos.has(video) || dismissedVideos.has(getVideoKey(video))) return;
    try {
      let streamUrl = '';
      if (sniffedMediaStreams.length > 0) {
        const masterStream = sniffedMediaStreams.find(s => s.url.includes('master.m3u8') || s.url.includes('master.mpd'));
        const m3u8 = masterStream || sniffedMediaStreams.find(s => s.url.includes('.m3u8') || s.url.includes('.mpd'));
        const direct = sniffedMediaStreams.slice().reverse().find(s => /\.(mp4|webm|vid)(\?|$)/i.test(s.url));
        streamUrl = m3u8 ? m3u8.url : (direct ? direct.url : sniffedMediaStreams[0].url);
      } else if (video.currentSrc && video.currentSrc.startsWith('http')) {
        streamUrl = video.currentSrc;
      } else if (video.src && video.src.startsWith('http')) {
        streamUrl = video.src;
      }

      window.top.postMessage({
        type: '__BDM_IFRAME_VIDEO_STATE__',
        state: state,
        duration: video.duration || 0,
        currentTime: video.currentTime || 0,
        currentSrc: video.currentSrc || video.src || '',
        streamUrl: streamUrl,
        videoWidth: video.videoWidth || 0,
        videoHeight: video.videoHeight || 0,
        title: getVideoTitle(video),
        frameUrl: window.location.href
      }, '*');
    } catch (e) {}
  }

  // Cross-frame coordination: allow top window to host widget so user can drag icon anywhere on page
  window.addEventListener('message', (event) => {
    if (!event.data || typeof event.data !== 'object') return;

    if (event.data.type === '__BDM_IFRAME_VIDEO_STATE__') {
      if (!isAppConnected || !enableMediaSniffing || isSiteBlacklisted()) return;
      const data = event.data;
      const iframes = document.querySelectorAll('iframe');
      let targetIframe = null;
      for (const f of iframes) {
        if (f.contentWindow === event.source) {
          targetIframe = f;
          break;
        }
      }

      if (!targetIframe && data.frameUrl) {
        try {
          const frameParsed = new URL(data.frameUrl);
          for (const f of iframes) {
            if (!f.src) continue;
            try {
              const srcParsed = new URL(f.src, window.location.href);
              if (srcParsed.host === frameParsed.host || f.src.includes(frameParsed.pathname) || data.frameUrl.includes(srcParsed.pathname)) {
                targetIframe = f;
                break;
              }
            } catch (e) {}
          }
        } catch (e) {}
      }

      if (!targetIframe) {
        // Check if there is an iframe inside recognized player containers (common on CMS / movie embed sites)
        const playerSelectors = [
          '#player iframe', '.player iframe', '.movieplayer iframe',
          '.videocontainer iframe', '.playcontainer iframe', '#playex iframe',
          '#vplayer iframe', '#player_el iframe', '.jwplayer iframe',
          '.video-player iframe', '.player-wrapper iframe', '.clappr-player iframe'
        ];
        for (const sel of playerSelectors) {
          const candidate = document.querySelector(sel);
          if (candidate) {
            targetIframe = candidate;
            break;
          }
        }
      }

      if (!targetIframe) {
        // Fallback: match largest visible iframe with video player dimensions (width >= 280, height >= 160)
        let largestArea = 0;
        for (const f of iframes) {
          const rect = f.getBoundingClientRect();
          if (rect.width >= 280 && rect.height >= 160) {
            const area = rect.width * rect.height;
            if (area > largestArea) {
              largestArea = area;
              targetIframe = f;
            }
          }
        }
      }

      if (!targetIframe && iframes.length === 1) {
        targetIframe = iframes[0];
      }

      if (targetIframe) {
        const isDismissed = dismissedVideos.has(targetIframe) ||
          dismissedVideos.has(getVideoKey(targetIframe)) ||
          (data.currentSrc && dismissedVideos.has(data.currentSrc)) ||
          (data.frameUrl && dismissedVideos.has(data.frameUrl)) ||
          (data.streamUrl && dismissedVideos.has(data.streamUrl));

        if (isDismissed) {
          try {
            event.source.postMessage({ type: '__BDM_TOP_HANDLING_VIDEO__' }, '*');
            event.source.postMessage({ type: '__BDM_DISMISS_VIDEO__' }, '*');
          } catch (e) {}
          return;
        }

        try {
          event.source.postMessage({ type: '__BDM_TOP_HANDLING_VIDEO__' }, '*');
        } catch (e) {}

        if (data.state === 'playing') {
          activeIframeVideo = targetIframe;
          activeIframeData = data;
          activeVideo = targetIframe;
          if (data.title && titleEl) {
            titleEl.textContent = data.title;
            titleEl.title = data.title;
          }
          showWidget();
        } else if (data.state === 'paused') {
          if (activeVideo === targetIframe) {
            updateWidgetPosition();
          }
        } else if (data.state === 'ended') {
          if (activeVideo === targetIframe) {
            hideWidget();
            activeVideo = null;
            activeIframeVideo = null;
            activeIframeData = null;
          }
        }
      }
    } else if (event.data.type === '__BDM_DISMISS_VIDEO__') {
      if (activeVideo) {
        dismissedVideos.add(activeVideo);
        dismissedVideos.add(getVideoKey(activeVideo));
      }
      if (activeIframeVideo) {
        dismissedVideos.add(activeIframeVideo);
        dismissedVideos.add(getVideoKey(activeIframeVideo));
      }
      const iframes = document.querySelectorAll('iframe');
      for (const f of iframes) {
        if (f.contentWindow === event.source) {
          dismissedVideos.add(f);
          dismissedVideos.add(getVideoKey(f));
          break;
        }
      }
      hideWidget('dismiss_message');
      activeVideo = null;
      activeIframeVideo = null;
      activeIframeData = null;
    } else if (event.data.type === '__BDM_TOP_HANDLING_VIDEO__') {
      isTopHandlingWidget = true;
      if (!document.fullscreenElement) {
        hideWidget('top_is_handling');
      }
    }
  });

  // 1. Inject inject.js into main world to access YouTube/HTML5 player APIs
  try {
    if (chrome.runtime && chrome.runtime.getURL) {
      const script = document.createElement('script');
      script.src = chrome.runtime.getURL('inject.js');
      script.async = true;
      (document.head || document.documentElement).appendChild(script);
      script.onload = () => script.remove();
    }
  } catch (e) {}

  // Listen for media info from main world
  window.addEventListener('message', (event) => {
    if (event.source !== window || !event.data) return;
    if (event.data.type === '__BDM_MEDIA_INFO__' && event.data.data) {
      ytMediaInfo = event.data.data;
      if (activeVideo && isDropdownOpen) {
        populateDropdown();
      }
    }
  });

  // Track parent tab info (essential for iframes like vidara.so)
  let cachedTabInfo = { title: "", url: "" };
  let sniffedMediaStreams = [];

  function fetchTabInfo() {
    try {
      chrome.runtime.sendMessage({ action: "get_tab_info" }, (res) => {
        if (chrome.runtime.lastError) return;
        if (res && res.title) {
          cachedTabInfo = res;
          if (titleEl && activeVideo) {
            const t = getVideoTitle(activeVideo);
            titleEl.textContent = t;
            titleEl.title = t;
          }
        }
      });
    } catch {}
  }
  fetchTabInfo();

  function fetchSniffedMedia() {
    try {
      chrome.runtime.sendMessage({ action: "get_sniffed_media" }, (res) => {
        if (chrome.runtime.lastError) return;
        if (res && Array.isArray(res.streams)) {
          sniffedMediaStreams = res.streams;
          if (activeVideo && isDropdownOpen) {
            populateDropdown();
          }
        }
      });
    } catch {}
  }
  function checkConnectionStatus(callback) {
    try {
      chrome.runtime.sendMessage({ action: "get_connection_status" }, (res) => {
        if (chrome.runtime.lastError) {
          isAppConnected = false;
          hideWidget();
          if (callback) callback(false);
          return;
        }
        const wasConnected = isAppConnected;
        isAppConnected = Boolean(res && res.online);
        host.dataset.bgOnline = String(res && res.online);
        if (!isAppConnected) {
          hideWidget('checkConnection_offline');
        } else if (!wasConnected && enableMediaSniffing) {
          if (activeVideo) {
            showWidget();
          } else {
            const v = document.querySelector('video');
            if (v && (!v.paused || v.currentTime > 0)) {
              onVideoState(v);
            }
          }
        }
        if (callback) callback(isAppConnected);
      });
    } catch (err) {
      isAppConnected = false;
      host.dataset.bgOnline = 'error_' + err.message;
      hideWidget('checkConnection_catch');
      if (callback) callback(false);
    }
  }
  checkConnectionStatus();

  try {
    chrome.storage.local.get({
      enableInterception: true,
      enableMediaSniffing: true,
      videoPanelPosition: 'top-right',
      blacklistUrls: []
    }, (items) => {
      if (chrome.runtime.lastError) return;
      enableInterception = items.enableInterception !== false;
      enableMediaSniffing = items.enableMediaSniffing !== false;
      blacklistUrls = Array.isArray(items.blacklistUrls) ? items.blacklistUrls : [];
      if (items.videoPanelPosition) videoPanelPosition = items.videoPanelPosition;
      if (!enableMediaSniffing || !isAppConnected || isSiteBlacklisted()) {
        hideWidget('init_disabled_or_blacklisted');
      }
    });

    chrome.storage.onChanged.addListener((changes, areaName) => {
      if (areaName === 'local') {
        let shouldCheckVisibility = false;

        if (changes.blacklistUrls !== undefined) {
          blacklistUrls = Array.isArray(changes.blacklistUrls.newValue) ? changes.blacklistUrls.newValue : [];
          shouldCheckVisibility = true;
        }
        if (changes.enableInterception !== undefined) {
          enableInterception = changes.enableInterception.newValue !== false;
          shouldCheckVisibility = true;
        }
        if (changes.enableMediaSniffing !== undefined) {
          enableMediaSniffing = changes.enableMediaSniffing.newValue !== false;
          shouldCheckVisibility = true;
        }
        if (changes.videoPanelPosition !== undefined) {
          videoPanelPosition = changes.videoPanelPosition.newValue || 'top-right';
          updateWidgetPosition();
        }

        if (shouldCheckVisibility) {
          if (!enableMediaSniffing || !isAppConnected || isSiteBlacklisted()) {
            hideWidget('storage_changed_disabled_or_blacklisted');
          } else if (activeVideo && isAppConnected && enableMediaSniffing) {
            showWidget();
          }
        }
      }
    });
  } catch {}

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.action === "connection_status_changed") {
      const wasConnected = isAppConnected;
      isAppConnected = Boolean(msg.online);
      if (!isAppConnected || isSiteBlacklisted()) {
        hideWidget('connection_status_changed');
      } else if (!wasConnected && enableMediaSniffing) {
        if (activeVideo) {
          showWidget();
        } else {
          const v = document.querySelector('video');
          if (v && (!v.paused || v.currentTime > 0)) {
            onVideoState(v);
          }
        }
      }
      return;
    }
    if (msg && msg.action === "media_stream_detected" && msg.stream) {
      if (!isAppConnected || !enableMediaSniffing || isSiteBlacklisted()) return;
      if (!sniffedMediaStreams.some(s => s.url === msg.stream.url)) {
        sniffedMediaStreams.unshift(msg.stream);
        if (sniffedMediaStreams.length > 30) sniffedMediaStreams.pop();
        if (activeVideo && isDropdownOpen) {
          populateDropdown();
        }
        if (window.self !== window.top && activeVideo) {
          notifyTopFrameVideo(activeVideo, 'playing');
        }
      }
    }
  });

  // Request fresh media info periodically
  function requestMediaInfo() {
    if (isSiteBlacklisted()) return;
    try {
      window.postMessage({ type: '__BDM_GET_MEDIA_INFO__' }, '*');
    } catch (e) {}
    fetchTabInfo();
    fetchSniffedMedia();
  }

  // 2. Create Shadow DOM Container on document.documentElement
  function cleanupDuplicateHosts() {
    try {
      const docks = document.querySelectorAll('bdm-video-dock');
      docks.forEach(d => {
        if (d !== host && d.parentNode) {
          d.parentNode.removeChild(d);
        }
      });
    } catch (e) {}
  }

  const host = document.createElement('bdm-video-dock');
  host.style.cssText = 'position: fixed; z-index: 2147483647; pointer-events: none; top: 0; left: 0;';
  const shadow = host.attachShadow({ mode: 'open' });
  cleanupDuplicateHosts();

  function ensureAttached() {
    cleanupDuplicateHosts();
    let targetParent = document.fullscreenElement || document.documentElement || document.body;
    if (targetParent && (targetParent instanceof HTMLVideoElement || targetParent.tagName === 'VIDEO')) {
      targetParent = targetParent.parentElement || document.documentElement || document.body;
    }
    if (!targetParent) return;
    if (host.parentNode !== targetParent) {
      targetParent.appendChild(host);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureAttached);
  } else {
    ensureAttached();
  }

  ['fullscreenchange', 'webkitfullscreenchange', 'mozfullscreenchange', 'MSFullscreenChange'].forEach((evt) => {
    document.addEventListener(evt, () => {
      ensureAttached();
      setTimeout(() => {
        ensureAttached();
        if (document.fullscreenElement) {
          const fsVideo = (document.fullscreenElement instanceof HTMLVideoElement || document.fullscreenElement.tagName === 'VIDEO')
            ? document.fullscreenElement
            : document.fullscreenElement.querySelector('video');
          if (fsVideo && isValidPlayedVideo(fsVideo, true)) {
            activeVideo = fsVideo;
            showWidget();
            return;
          }
        } else if (window.self !== window.top && isTopHandlingWidget) {
          hideWidget('exit_fullscreen_iframe');
          activeVideo = null;
          return;
        }
        updateWidgetPosition();
      }, 100);
      setTimeout(() => {
        ensureAttached();
        if (window.self !== window.top && isTopHandlingWidget && !document.fullscreenElement) {
          hideWidget('exit_fullscreen_iframe');
          activeVideo = null;
          return;
        }
        updateWidgetPosition();
      }, 400);
    }, true);
  });

  // 3. Inject Component Styles
  const style = document.createElement('style');
  style.textContent = `
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      user-select: none;
      -webkit-user-select: none;
    }

    .bdm-root {
      position: fixed;
      display: none;
      flex-direction: column;
      align-items: flex-end;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      font-feature-settings: "tnum" 1;
      font-variant-numeric: tabular-nums;
      pointer-events: auto;
      z-index: 2147483647;
      opacity: 0.95;
      transition: opacity 0.25s ease, transform 0.2s ease;
    }

    .bdm-root.visible {
      display: flex;
    }

    .bdm-root.idle {
      opacity: 0.4;
    }

    /* If hovered, active, open, or dragging, show up completely */
    .bdm-root:hover,
    .bdm-root.open,
    .bdm-root.dragging,
    .bdm-root:focus-within {
      opacity: 1 !important;
    }

    /* Bengal DM Dark Tray Pill Icon Button */
    .bdm-pill {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 34px;
      height: 34px;
      padding: 0;
      background: linear-gradient(145deg, #242932 0%, #15181f 100%);
      color: #f9fafb;
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 8px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.55), 0 1px 3px rgba(0, 0, 0, 0.35);
      cursor: grab;
      transition: background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
    }

    .bdm-pill:hover {
      background: linear-gradient(145deg, #2c323d 0%, #1a1e27 100%);
      border-color: rgba(255, 255, 255, 0.32);
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.65), 0 2px 5px rgba(0, 0, 0, 0.4);
      transform: scale(1.05);
    }

    .bdm-pill:active {
      cursor: grabbing;
      transform: scale(0.96);
    }

    /* Tray icon badge */
    .bdm-icon-wrap {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 22px;
      height: 22px;
      flex-shrink: 0;
      pointer-events: none;
    }

    .bdm-logo-img {
      width: 22px;
      height: 22px;
      object-fit: contain;
      user-select: none;
      -webkit-user-drag: none;
      display: block;
      pointer-events: none;
    }

    /* Corner close cross button: HOVER TO VIEW */
    .bdm-close-btn {
      position: absolute;
      top: -7px;
      right: -7px;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: #1e2229;
      border: 1px solid rgba(255, 255, 255, 0.24);
      color: #d1d5db;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      line-height: 1;
      cursor: pointer;
      opacity: 0;
      pointer-events: none;
      transform: scale(0.85);
      transition: opacity 0.2s cubic-bezier(0.4, 0, 0.2, 1), transform 0.15s ease, background 0.15s ease;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.45);
      z-index: 5;
    }

    /* Show cross button only when hovering over the widget */
    .bdm-root:hover .bdm-close-btn {
      opacity: 1;
      pointer-events: auto;
      transform: scale(1);
    }

    .bdm-close-btn:hover {
      background: #ef4444;
      border-color: #ef4444;
      color: #ffffff;
      transform: scale(1.1);
    }

    /* Dropdown panel */
    .bdm-dropdown {
      display: none;
      position: absolute;
      top: calc(100% + 6px);
      right: 0;
      width: 320px;
      max-width: 90vw;
      background: #14171d;
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-radius: 8px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.75), 0 2px 6px rgba(0, 0, 0, 0.4);
      overflow: hidden;
      animation: bdmFadeIn 0.15s ease-out;
      z-index: 10;
    }

    @keyframes bdmFadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }

    .bdm-root.open .bdm-dropdown {
      display: block;
    }

    .bdm-root.pos-top-left .bdm-dropdown {
      left: 0;
      right: auto;
      top: calc(100% + 6px);
      bottom: auto;
    }

    .bdm-root.pos-top-right .bdm-dropdown {
      right: 0;
      left: auto;
      top: calc(100% + 6px);
      bottom: auto;
    }

    .bdm-root.pos-top-center .bdm-dropdown,
    .bdm-root.pos-center .bdm-dropdown {
      left: 50%;
      right: auto;
      transform: translateX(-50%);
      top: calc(100% + 6px);
      bottom: auto;
    }

    .bdm-root.pos-bottom-left .bdm-dropdown {
      left: 0;
      right: auto;
      bottom: calc(100% + 6px);
      top: auto;
    }

    .bdm-root.pos-bottom-right .bdm-dropdown {
      right: 0;
      left: auto;
      bottom: calc(100% + 6px);
      top: auto;
    }

    .bdm-root.pos-bottom-center .bdm-dropdown {
      left: 50%;
      right: auto;
      transform: translateX(-50%);
      bottom: calc(100% + 6px);
      top: auto;
    }

    .bdm-root.pos-top-center .bdm-header,
    .bdm-root.pos-center .bdm-header,
    .bdm-root.pos-bottom-center .bdm-header {
      text-align: center;
    }

    .bdm-root.pos-top-center .bdm-meta,
    .bdm-root.pos-center .bdm-meta,
    .bdm-root.pos-bottom-center .bdm-meta {
      justify-content: center;
    }

    /* Dropdown Header */
    .bdm-header {
      padding: 10px 12px;
      background: #1a1e26;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    }

    .bdm-title {
      font-size: 12.5px;
      font-weight: 600;
      color: #f3f4f6;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      line-height: 1.3;
    }

    .bdm-meta {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 4px;
      font-size: 11px;
      color: #9ca3af;
    }

    .bdm-meta-badge {
      display: inline-block;
      padding: 1px 5px;
      border-radius: 3px;
      background: rgba(61, 174, 233, 0.18);
      color: #3daee9;
      font-weight: 600;
      font-size: 10px;
      letter-spacing: 0.3px;
      text-transform: uppercase;
    }

    /* Resolution list */
    .bdm-list {
      max-height: 250px;
      overflow-y: auto;
      padding: 4px 0;
    }

    .bdm-list::-webkit-scrollbar {
      width: 5px;
    }

    .bdm-list::-webkit-scrollbar-thumb {
      background: rgba(255, 255, 255, 0.18);
      border-radius: 3px;
    }

    .bdm-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 12px;
      cursor: pointer;
      transition: background 0.12s ease;
    }

    .bdm-item:hover {
      background: rgba(61, 174, 233, 0.12);
    }

    .bdm-item:active {
      background: rgba(61, 174, 233, 0.22);
    }

    .bdm-item-left {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .bdm-res-badge {
      font-size: 10.5px;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 4px;
      background: #222730;
      color: #e5e7eb;
      border: 1px solid rgba(255, 255, 255, 0.1);
      min-width: 44px;
      text-align: center;
    }

    .bdm-res-badge.uhd {
      background: rgba(245, 158, 11, 0.2);
      color: #fbbf24;
      border-color: rgba(245, 158, 11, 0.4);
    }

    .bdm-res-badge.hd {
      background: rgba(61, 174, 233, 0.2);
      color: #60a5fa;
      border-color: rgba(61, 174, 233, 0.4);
    }

    .bdm-res-badge.audio {
      background: rgba(16, 185, 129, 0.2);
      color: #34d399;
      border-color: rgba(16, 185, 129, 0.4);
    }

    .bdm-res-label {
      font-size: 12px;
      color: #d1d5db;
    }

    .bdm-item-right {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .bdm-res-size {
      font-size: 11.5px;
      color: #9ca3af;
      font-variant-numeric: tabular-nums;
    }

    .bdm-dl-icon {
      width: 14px;
      height: 14px;
      color: #60a5fa;
      opacity: 0.8;
      transition: transform 0.15s ease, opacity 0.15s ease;
    }

    .bdm-item:hover .bdm-dl-icon {
      opacity: 1;
      transform: translateY(1px);
    }

    /* Footer */
    .bdm-footer {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 7px 12px;
      background: #101317;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      font-size: 11px;
      color: #6b7280;
      min-height: 28px;
      text-align: center;
      transition: background 0.2s ease, color 0.2s ease;
    }

    .bdm-footer.opening {
      background: rgba(16, 185, 129, 0.12);
      color: #34d399;
      font-weight: 500;
    }
  `;
  shadow.appendChild(style);

  // 4. Create DOM Structure
  const root = document.createElement('div');
  root.className = 'bdm-root';
  root.id = 'bdmRoot';

  const logoHtml = `
    <svg class="bdm-logo-img" viewBox="0 0 1177.38 1013.61" width="22" height="22" xmlns="http://www.w3.org/2000/svg">
      <g transform="translate(-435.32, 1559.90) scale(0.1, -0.1)" fill="#FFFFFF">
        <path d="M7435 15553 c-198 -64 -668 -223 -808 -273 -100 -36 -120 -47 -128 -69 -44 -114 -187 -735 -229 -994 -98 -603 -129 -978 -130 -1558 0 -506 23 -825 96 -1324 165 -1127 557 -2197 1196 -3268 301 -503 739 -1084 1076 -1427 124 -126 131 -132 113 -90 -10 25 -59 140 -109 255 -373 867 -657 1738 -856 2625 -209 930 -320 1822 -357 2860 -35 967 65 2197 254 3148 18 89 30 162 27 161 -3 0 -68 -21 -145 -46z M12893 15583 c24 -83 124 -668 161 -943 166 -1232 177 -2361 35 -3610 -83 -733 -169 -1222 -334 -1895 -190 -777 -466 -1594 -802 -2375 -42 -96 -82 -191 -90 -210 l-15 -35 43 40 c236 215 685 783 1001 1265 901 1373 1388 2908 1449 4565 24 660 -36 1350 -181 2080 -38 193 -158 692 -178 746 -9 22 -30 33 -134 71 -96 35 -823 278 -936 313 -20 6 -23 4 -19 -12z M9075 15310 c-115 -21 -270 -51 -343 -66 -156 -32 -139 -15 -200 -209 -321 -1026 -413 -2106 -271 -3185 161 -1230 619 -2458 1352 -3627 116 -186 323 -470 334 -459 3 2 -7 39 -20 83 -158 498 -446 1681 -532 2178 -14 83 -39 227 -55 320 -146 860 -230 1822 -230 2630 1 758 66 1507 190 2180 16 90 30 171 30 180 0 20 -11 19 -255 -25z M11150 15339 c0 -6 18 -110 39 -232 78 -439 136 -946 163 -1417 21 -392 15 -1227 -12 -1615 -74 -1042 -197 -1865 -429 -2866 -94 -406 -212 -863 -326 -1259 -30 -101 -52 -186 -51 -188 2 -1 49 57 103 130 330 438 793 1291 1039 1910 459 1158 651 2261 594 3413 -18 364 -62 736 -126 1054 -52 262 -154 645 -226 850 -30 86 -36 96 -63 103 -61 17 -663 128 -692 128 -7 0 -13 -5 -13 -11z M5445 14495 c-435 -130 -679 -207 -688 -215 -20 -17 -172 -672 -221 -950 -93 -525 -133 -870 -166 -1425 -57 -980 31 -1944 265 -2910 306 -1267 886 -2398 1690 -3300 111 -124 217 -236 221 -232 2 2 -26 75 -62 163 -426 1032 -709 2179 -853 3454 -96 843 -116 1281 -108 2329 7 874 21 1151 97 1906 34 330 98 853 135 1089 29 185 29 186 13 185 -7 -1 -152 -43 -323 -94z M14700 14585 c0 -2 20 -145 45 -317 91 -643 137 -1085 179 -1753 55 -855 51 -2011 -10 -2785 -76 -988 -237 -1951 -459 -2760 -136 -495 -242 -807 -439 -1295 -47 -115 -84 -211 -82 -212 6 -6 187 189 312 335 526 614 951 1328 1261 2117 235 596 382 1150 497 1865 185 1152 161 2387 -70 3620 -40 210 -194 863 -207 877 -15 14 -987 313 -1019 313 -4 0 -8 -2 -8 -5z"/>
      </g>
    </svg>
  `;

  root.innerHTML = `
    <div class="bdm-pill" id="bdmPill" title="Bengal Download Manager (Click to download, drag to reposition)">
      <button class="bdm-close-btn" id="bdmCloseBtn" title="Dismiss">&times;</button>
      <div class="bdm-icon-wrap">
        ${logoHtml}
      </div>
    </div>
    <div class="bdm-dropdown" id="bdmDropdown">
      <div class="bdm-header">
        <div class="bdm-title" id="bdmTitle">Video Title</div>
        <div class="bdm-meta">
          <span class="bdm-meta-badge" id="bdmSourceBadge">VIDEO</span>
          <span id="bdmDuration">00:00</span>
        </div>
      </div>
      <div class="bdm-list" id="bdmList"></div>
      <div class="bdm-footer" id="bdmFooter">
        <span id="bdmFooterText">Bengal Download Manager</span>
      </div>
    </div>
  `;
  shadow.appendChild(root);

  const pill = shadow.getElementById('bdmPill');
  const closeBtn = shadow.getElementById('bdmCloseBtn');
  const dropdown = shadow.getElementById('bdmDropdown');
  const titleEl = shadow.getElementById('bdmTitle');
  const badgeEl = shadow.getElementById('bdmSourceBadge');
  const durationEl = shadow.getElementById('bdmDuration');
  const listEl = shadow.getElementById('bdmList');
  const footerEl = shadow.getElementById('bdmFooter');
  const footerTextEl = shadow.getElementById('bdmFooterText');

  // 5. Inactivity & Idle Transparency Management
  let isHovered = false;
  let idleTimer = null;
  const IDLE_DELAY_MS = 3200;

  function resetIdleTimer() {
    clearTimeout(idleTimer);
    if (!root) return;
    root.classList.remove('idle');
    if (!isDropdownOpen && !isPointerDown && !isHovered) {
      idleTimer = setTimeout(() => {
        if (!isDropdownOpen && !isPointerDown && !isHovered) {
          root.classList.add('idle');
        }
      }, IDLE_DELAY_MS);
    }
  }

  function clearIdleTimer() {
    clearTimeout(idleTimer);
    if (root) {
      root.classList.remove('idle');
    }
  }

  root.addEventListener('mouseenter', () => {
    isHovered = true;
    clearIdleTimer();
  });

  root.addEventListener('mouseleave', () => {
    isHovered = false;
    resetIdleTimer();
  });

  ['mousedown', 'mouseup', 'pointerdown', 'pointerup', 'click'].forEach((evtName) => {
    root.addEventListener(evtName, (e) => e.stopPropagation());
    dropdown.addEventListener(evtName, (e) => e.stopPropagation());
  });

  // 6. Draggable / Movable Behavior
  let isPointerDown = false;
  let hasDragged = false;
  let isCapturing = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let initialLeft = 0;
  let initialTop = 0;

  let justDragged = false;

  pill.addEventListener('pointerdown', (e) => {
    e.stopPropagation();
    if (e.target.closest('#bdmCloseBtn')) return;

    clearIdleTimer();

    isPointerDown = true;
    hasDragged = false;
    justDragged = false;
    isCapturing = false;
    dragStartX = e.clientX;
    dragStartY = e.clientY;

    const rect = root.getBoundingClientRect();
    initialLeft = rect.left;
    initialTop = rect.top;
  });

  pill.addEventListener('pointermove', (e) => {
    if (!isPointerDown) return;
    const dx = e.clientX - dragStartX;
    const dy = e.clientY - dragStartY;

    if (!hasDragged && Math.hypot(dx, dy) > 6) {
      hasDragged = true;
      justDragged = true;
      isUserPositioned = true;
      root.classList.add('dragging');
      try {
        pill.setPointerCapture(e.pointerId);
        isCapturing = true;
      } catch (err) {}
    }

    if (hasDragged) {
      let newLeft = initialLeft + dx;
      let newTop = initialTop + dy;

      const pad = 8;
      const rootW = pill.offsetWidth || 34;
      const rootH = pill.offsetHeight || 34;
      newLeft = Math.max(pad, Math.min(window.innerWidth - rootW - pad, newLeft));
      newTop = Math.max(pad, Math.min(window.innerHeight - rootH - pad, newTop));

      userCoords = { left: newLeft, top: newTop };
      root.style.left = `${newLeft}px`;
      root.style.top = `${newTop}px`;
      root.style.right = 'auto';
      root.style.bottom = 'auto';
    }
  });

  pill.addEventListener('pointerup', (e) => {
    e.stopPropagation();
    if (!isPointerDown) return;
    isPointerDown = false;
    root.classList.remove('dragging');
    if (isCapturing) {
      try {
        pill.releasePointerCapture(e.pointerId);
      } catch (err) {}
      isCapturing = false;
    }

    if (hasDragged) {
      justDragged = true;
      setTimeout(() => { justDragged = false; }, 200);
      if (!isDropdownOpen) {
        resetIdleTimer();
      }
    }
  });

  pill.addEventListener('click', (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (justDragged || hasDragged) {
      hasDragged = false;
      return;
    }
    toggleDropdown();
  });

  // 6. Cross Button in Corner (Hover-to-view dismissal)
  closeBtn.addEventListener('pointerdown', (e) => {
    e.stopPropagation();
  });

  closeBtn.addEventListener('mousedown', (e) => {
    e.stopPropagation();
  });

  closeBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (activeVideo) {
      dismissedVideos.add(activeVideo);
      dismissedVideos.add(getVideoKey(activeVideo));
      if (activeVideo.currentSrc) dismissedVideos.add(activeVideo.currentSrc);
      if (activeVideo.src) dismissedVideos.add(activeVideo.src);
      if (activeVideo.tagName === 'IFRAME') {
        try {
          if (activeVideo.contentWindow) {
            activeVideo.contentWindow.postMessage({ type: '__BDM_DISMISS_VIDEO__' }, '*');
          }
        } catch (err) {}
      }
    }
    if (activeIframeVideo) {
      dismissedVideos.add(activeIframeVideo);
      dismissedVideos.add(getVideoKey(activeIframeVideo));
      if (activeIframeData) {
        if (activeIframeData.currentSrc) dismissedVideos.add(activeIframeData.currentSrc);
        if (activeIframeData.frameUrl) dismissedVideos.add(activeIframeData.frameUrl);
      }
      try {
        if (activeIframeVideo.contentWindow) {
          activeIframeVideo.contentWindow.postMessage({ type: '__BDM_DISMISS_VIDEO__' }, '*');
        }
      } catch (err) {}
    }
    if (window.self !== window.top) {
      try {
        window.top.postMessage({ type: '__BDM_DISMISS_VIDEO__' }, '*');
      } catch (err) {}
    }
    hideWidget('user_dismissed');
    activeVideo = null;
    activeIframeVideo = null;
    activeIframeData = null;
  });

  function getVideoKey(video) {
    if (!video) return window.location.href;
    if (video.tagName === 'IFRAME') {
      return (activeIframeData && (activeIframeData.currentSrc || activeIframeData.frameUrl)) || video.src || window.location.href;
    }
    if (window.location.hostname.includes('youtube.com') || window.location.hostname.includes('youtu.be')) {
      const v = new URLSearchParams(window.location.search).get('v');
      if (v) return `yt_${v}`;
      const mShorts = window.location.pathname.match(/\/shorts\/([A-Za-z0-9_-]+)/);
      if (mShorts) return `yt_${mShorts[1]}`;
    }
    return video.currentSrc || video.src || window.location.href;
  }

  const playedVideos = new WeakSet();

  // 7. Video Validation: Exclude thumbnails, previews, and unplayed elements
  function isValidPlayedVideo(video, allowPaused = false) {
    if (!video || !(video instanceof HTMLVideoElement || video.tagName === 'VIDEO')) {
      return false;
    }

    // Dismissed for this session
    if (dismissedVideos.has(video) || dismissedVideos.has(getVideoKey(video))) {
      return false;
    }

    const isPopular = isPopularMediaHost(window.location.hostname);

    // Navigational link check: reject if anchor is a thumbnail card, but preserve legitimate players
    const anchor = video.closest('a[href]');
    if (anchor) {
      const isExplicitThumb = video.matches('.hvp_player, .vidthumb, .video-thumb, [data-hvp]') ||
                              video.closest('.post_vid_thumb, .thumb, .video-thumb, .vidthumb') ||
                              (video.currentSrc || video.src || '').toLowerCase().includes('vidthumb') ||
                              (!isPopular && video.loop && video.muted && (!video.duration || video.duration < 15));
      if (isExplicitThumb) {
        return false;
      }
    }

    // Thumbnail / preview classes or data attributes on the video element itself (e.g. .hvp_player on sxyprn)
    const previewClassesOrAttrs = [
      '.hvp_player',
      '.vidthumb',
      '.video-thumb',
      '.thumb-video',
      '.hover-video',
      '.preview-video',
      '.video-preview',
      '.thumbnail-video',
      '.trailer-video',
      '.preview-player',
      '.preview_player',
      '[data-hvp]',
      '[data-preview]',
      '[data-thumb]',
      '[data-thumbnail]',
      '[data-trailer]'
    ];
    if (video.matches && !isPopular) {
      for (const sel of previewClassesOrAttrs) {
        if (video.matches(sel)) return false;
      }
    }

    // Inline event handlers for thumbnail/hover video players (e.g. onplay="hvponplay(this)")
    const onplayAttr = (video.getAttribute('onplay') || '').toLowerCase();
    if (!isPopular && (onplayAttr.includes('hvp') || onplayAttr.includes('preview') || onplayAttr.includes('thumb'))) {
      return false;
    }

    // Exclude thumbnail / preview media source URLs
    const srcLower = (video.currentSrc || video.src || '').toLowerCase();
    if (
      srcLower.includes('vidthumb') ||
      srcLower.includes('thumb_preview') ||
      srcLower.includes('hover_preview') ||
      srcLower.includes('preview_video') ||
      srcLower.includes('preview.mp4') ||
      srcLower.includes('trailer_preview') ||
      srcLower.includes('storyboard') ||
      srcLower.includes('_preview.') ||
      srcLower.includes('/preview/') ||
      srcLower.includes('/preview_clip/') ||
      srcLower.includes('/thumbnails/')
    ) {
      return false;
    }

    // If it hasn't been played yet, must not be paused
    if (!allowPaused && !playedVideos.has(video)) {
      if (video.paused || video.ended) {
        return false;
      }
    }

    // Exclude short preview loops / ad gifs (< 3.5 seconds) if duration is known & finite
    if (video.duration && isFinite(video.duration) && video.duration > 0 && video.duration < 3.5) {
      return false;
    }

    // Exclude muted looping preview clips without native or player controls (GIF replacements)
    // Only on generic sites. Popular platforms (Facebook, X, Instagram, TikTok) loop and start muted by design!
    if (!isPopular && video.loop && video.muted && !video.controls) {
      if (!video.duration || !isFinite(video.duration) || video.duration < 45) {
        const hasCustomPlayer = video.closest('.jwplayer, .video-js, .plyr, .dplayer, .artplayer, #movie_player, .html5-video-player');
        if (!hasCustomPlayer) {
          return false;
        }
      }
    }

    const rect = video.getBoundingClientRect();
    // Video must intersect the visible viewport (prevents scrolled-past feed videos from hijacking activeVideo)
    if (rect.bottom <= 0 || rect.top >= window.innerHeight || rect.right <= 0 || rect.left >= window.innerWidth) {
      return false;
    }

    const isInIframe = window.self !== window.top;
    const minW = isPopular ? 120 : (isInIframe ? 160 : 260);
    const minH = isPopular ? 100 : (isInIframe ? 90 : 140);

    // Dimensions check
    if ((rect.width < minW || rect.height < minH) && (video.videoWidth < 120 || video.videoHeight < 100)) {
      return false;
    }

    // Check display / visibility styles
    const style = window.getComputedStyle(video);
    if (style.display === 'none' || style.visibility === 'hidden') {
      return false;
    }
    // Only exclude opacity: '0' on generic sites. Popular sites (TikTok, WebGL/canvas players) may animate or render with opacity: 0
    if (!isPopular && style.opacity === '0') {
      return false;
    }

    // Strict preview containers exclusion
    const isYouTube = window.location.hostname.includes('youtube.com');
    if (isYouTube) {
      const isMainPlayer = video.closest('#movie_player, ytd-watch-flexy, ytd-shorts, #ytd-player, .html5-main-video');
      if (!isMainPlayer) {
        return false;
      }
      const isPreview = video.closest('ytd-thumbnail, #inline-preview-player, ytd-video-preview, ytd-rich-grid-media #thumbnail, .ytd-compact-video-renderer #thumbnail');
      if (isPreview) {
        return false;
      }
    } else if (isPopular) {
      const isExplicitAd = video.closest('.ad-container, .advertisement, [data-ad-container]');
      if (isExplicitAd) {
        return false;
      }
    } else {
      const isRecognizedMain = video.closest([
        '#player_el', '.player_el', '#vid_container_id', '.yps_player_wrap',
        '.jwplayer', '.video-js', '.plyr', '.dplayer', '.artplayer',
        '#player', '#vplayer', '#player-holder', '.playcontainer', '.videocontainer',
        '.movieplayer', '.video-player', '.player-wrapper', '.clappr-player',
        '.fluid_video_wrapper', '.flowplayer', '[data-player]'
      ].join(','));
      if (!isRecognizedMain) {
        // If the video is actively playing or has controls or duration > 30s, do not reject as preview card
        const isLegitPlayback = (!video.paused && video.currentTime > 0) || video.controls || (video.duration > 30);
        if (!isLegitPlayback) {
          const genericPreview = video.closest([
            'ytd-thumbnail',
            '#inline-preview-player',
            'ytd-video-preview',
            '.feed-video-preview',
            '.shorts-carousel',
            '.thumb-preview',
            '.post_vid_thumb',
            '.video_thumb',
            '.thumb_video',
            '.video-card',
            '.thumbnail-card',
            '.thumb-container',
            '.preview-container',
            '.video-preview-container',
            '.hover-preview',
            '.media-card',
            '.thumb',
            '.thumbnail',
            '.ad-container',
            '.advertisement',
            '[data-hvp]',
            '[data-preview]'
          ].join(','));
          if (genericPreview) {
            return false;
          }
        }
      }
    }

    return true;
  }

  // 8. Video Title & Duration Extraction
  function cleanTitleString(str) {
    if (!str || typeof str !== 'string') return "";
    let clean = str.trim();
    // Strip common leading noise
    clean = clean.replace(/^(Watch\s*[:-]?\s*|Streaming\s*[:-]?\s*|Play\s*[:-]?\s*)/i, '');
    // Strip trailing site brandings like "- Vidara", "| Vidara", "- YouTube", "- Vidara.so", " | 123movies", etc.
    clean = clean.replace(/\s*[-–—|]\s*([a-zA-Z0-9.-]+\.(com|org|net|so|to|is|io|me|tv|cc|cx)|Vidara|YouTube|Vimeo|Dailymotion|StreamTape|SuperStream|Flixtor|Fmovies|123movies|BiliBili|Twitch|SoundCloud|Facebook|Twitter|TikTok|Reddit|RedGifs)[^|\-–—]*$/i, '');
    clean = clean.replace(/\s*[-–—|]\s*Watch\s+.*$/i, '');
    clean = clean.replace(/\s*[-–—|]\s*Official\s+(Website|Site|Stream|Video).*$/i, '');
    return clean.trim();
  }

  function isCanonicalMediaPage(url) {
    if (!url) return false;
    try {
      const u = new URL(url);
      const path = u.pathname.toLowerCase().replace(/\/+$/, '');
      const host = u.hostname.toLowerCase();
      if (!path || ['', '/', '/foryou', '/following', '/explore', '/live', '/home', '/feed'].includes(path)) {
        if (!u.searchParams.has('v') && !u.searchParams.has('video_id')) return false;
      }
      if (host.includes('vt.tiktok.com') || host.includes('vm.tiktok.com') || host.includes('fb.watch') || host.includes('youtu.be') || host.includes('dai.ly')) {
        return path.length > 1;
      }
      if (host.includes('tiktok.com')) {
        return path.includes('/video/') || path.includes('/v/') || /\/\d{18,20}/.test(path);
      }
      if (host.includes('facebook.com')) {
        return path.includes('/reel/') || path.includes('/watch') || path.includes('/videos/') || u.searchParams.has('v');
      }
      if (host.includes('instagram.com')) {
        return path.includes('/reel/') || path.includes('/p/') || path.includes('/tv/') || path.includes('/reels/');
      }
      if (host.includes('twitter.com') || host.includes('x.com')) {
        return path.includes('/status/');
      }
      if (host.includes('youtube.com')) {
        return u.searchParams.has('v') || path.includes('/shorts/') || path.includes('/embed/') || path.includes('/watch');
      }
      if (host.includes('reddit.com')) {
        return path.includes('/comments/');
      }
      if (host.includes('redgifs.com')) {
        return path.includes('/watch/') || path.includes('/ifr/') || path.length > 1;
      }
      if (isPopularMediaHost(host)) {
        return path.length > 1;
      }
      return path.length > 1;
    } catch (e) {
      return false;
    }
  }

  function getMediaPageUrl(video) {
    const host = window.location.hostname.toLowerCase();
    const currentUrl = window.location.href;

    // Facebook & Reels
    if (host.includes('facebook.com') || host.includes('fb.watch') || host.includes('fb.com')) {
      if (isCanonicalMediaPage(currentUrl)) {
        return currentUrl;
      }
      if (video) {
        try {
          const container = video.closest('[role="article"], [data-pagelet*="FeedUnit"], [data-pagelet*="Reel"], div[role="main"]') || video.parentElement;
          if (container) {
            const permalinkEl = container.querySelector('a[href*="/reel/"], a[href*="/watch"], a[href*="/videos/"]');
            if (permalinkEl && permalinkEl.href && isCanonicalMediaPage(permalinkEl.href)) {
              return permalinkEl.href;
            }
          }
        } catch (e) {}
      }
      return null;
    }

    // Instagram & Reels
    if (host.includes('instagram.com')) {
      if (isCanonicalMediaPage(currentUrl)) {
        return currentUrl;
      }
      if (video) {
        try {
          const container = video.closest('article, [role="presentation"]') || video.parentElement;
          if (container) {
            const permalinkEl = container.querySelector('a[href*="/reel/"], a[href*="/p/"]');
            if (permalinkEl && permalinkEl.href && isCanonicalMediaPage(permalinkEl.href)) {
              return permalinkEl.href;
            }
          }
        } catch (e) {}
      }
      return null;
    }

    // TikTok
    if (host.includes('tiktok.com')) {
      if (isCanonicalMediaPage(currentUrl)) {
        return currentUrl;
      }
      if (video) {
        try {
          const container = video.closest('[data-e2e="recommend-list-item-container"], [data-e2e="feed-item"], [data-e2e="user-post-item"], div[id*="xgwrapper"], section, article') || video.parentElement;
          if (container) {
            const permalinkEl = container.querySelector('a[href*="/video/"], a[href*="/v/"]');
            if (permalinkEl && permalinkEl.href && isCanonicalMediaPage(permalinkEl.href)) {
              return permalinkEl.href;
            }
          }
          // Search up the DOM tree for any container or link or element with video ID
          let curr = video.parentElement;
          for (let i = 0; i < 15 && curr; i++) {
            const link = curr.querySelector('a[href*="/video/"], a[href*="/v/"]');
            if (link && link.href && isCanonicalMediaPage(link.href)) {
              return link.href;
            }
            if (curr.id) {
              const m = curr.id.match(/\d{18,20}/);
              if (m) {
                return `https://www.tiktok.com/@video/video/${m[0]}`;
              }
            }
            curr = curr.parentElement;
          }
        } catch (e) {}
      }
      return null;
    }

    // Twitter / X
    if (host.includes('twitter.com') || host.includes('x.com')) {
      if (isCanonicalMediaPage(currentUrl)) {
        return currentUrl;
      }
      if (video) {
        try {
          const container = video.closest('article') || video.parentElement;
          if (container) {
            const permalinkEl = container.querySelector('a[href*="/status/"]');
            if (permalinkEl && permalinkEl.href && isCanonicalMediaPage(permalinkEl.href)) {
              return permalinkEl.href;
            }
          }
        } catch (e) {}
      }
      return null;
    }

    // RedGifs
    if (host.includes('redgifs.com')) {
      if (isCanonicalMediaPage(currentUrl)) {
        const m = currentUrl.match(/redgifs\.com\/(?:watch|ifr)\/([a-zA-Z0-9_-]+)/i);
        if (m) {
          return `https://www.redgifs.com/watch/${m[1]}`;
        }
        return currentUrl;
      }
      return null;
    }

    // Reddit
    if (host.includes('reddit.com')) {
      if (isCanonicalMediaPage(currentUrl)) {
        return currentUrl;
      }
      if (video) {
        try {
          // If video is an iframe or activeIframeData exists for RedGifs embed
          if (activeIframeData && activeIframeData.frameUrl && activeIframeData.frameUrl.includes('redgifs.com')) {
            const m = activeIframeData.frameUrl.match(/redgifs\.com\/(?:watch|ifr)\/([a-zA-Z0-9_-]+)/i);
            if (m) return `https://www.redgifs.com/watch/${m[1]}`;
          }

          // Traverse out of shadow DOM if necessary to find the post container
          let container = null;
          let curr = video;
          while (curr) {
            if (curr.matches && curr.matches('shreddit-post, [data-test-id="post-container"], .Post, .thing, article')) {
              container = curr;
              break;
            }
            if (curr.parentElement) {
              curr = curr.parentElement;
            } else {
              const root = curr.getRootNode ? curr.getRootNode() : null;
              if (root && root instanceof ShadowRoot && root.host) {
                curr = root.host;
              } else {
                break;
              }
            }
          }
          if (!container && video.closest) {
            container = video.closest('shreddit-post, [data-test-id="post-container"], .Post, .thing, article') || video.parentElement;
          }

          if (container) {
            // A. Check for external media embed (e.g. RedGifs, YouTube, Streamable)
            const contentHref = container.getAttribute('content-href');
            if (contentHref) {
              const lowerHref = contentHref.toLowerCase();
              if (lowerHref.includes('redgifs.com')) {
                const m = contentHref.match(/redgifs\.com\/(?:watch|ifr)\/([a-zA-Z0-9_-]+)/i);
                if (m) return `https://www.redgifs.com/watch/${m[1]}`;
                return contentHref;
              }
              if (isPopularMediaHost(lowerHref) && isCanonicalMediaPage(contentHref)) {
                return contentHref;
              }
            }

            // Check if post contains an iframe or anchor to redgifs
            const redgifsIframe = container.querySelector('iframe[src*="redgifs.com"], iframe[data-src*="redgifs.com"]');
            if (redgifsIframe) {
              const src = redgifsIframe.getAttribute('src') || redgifsIframe.getAttribute('data-src') || redgifsIframe.src;
              if (src) {
                const m = src.match(/redgifs\.com\/(?:watch|ifr)\/([a-zA-Z0-9_-]+)/i);
                if (m) return `https://www.redgifs.com/watch/${m[1]}`;
                return src;
              }
            }
            const redgifsLink = container.querySelector('a[href*="redgifs.com"]');
            if (redgifsLink && redgifsLink.href) {
              const m = redgifsLink.href.match(/redgifs\.com\/(?:watch|ifr)\/([a-zA-Z0-9_-]+)/i);
              if (m) return `https://www.redgifs.com/watch/${m[1]}`;
              return redgifsLink.href;
            }

            // B. Canonical post permalink on shreddit-post or legacy post
            let permalink = container.getAttribute('permalink') || container.getAttribute('data-permalink');
            if (permalink) {
              try {
                const fullUrl = new URL(permalink, window.location.origin).href;
                if (isCanonicalMediaPage(fullUrl)) {
                  return fullUrl;
                }
              } catch (e) {}
            }

            // Fallback link selectors for comments page
            const permalinkEl = container.querySelector('a[slot="full-post-link"], a[slot="title"], a.post-title, a[data-click-id="body"], a[href*="/comments/"]');
            if (permalinkEl && permalinkEl.href && isCanonicalMediaPage(permalinkEl.href)) {
              return permalinkEl.href;
            }

            // C. Old reddit data-url
            const dataUrl = container.getAttribute('data-url');
            if (dataUrl) {
              if (dataUrl.includes('redgifs.com')) {
                const m = dataUrl.match(/redgifs\.com\/(?:watch|ifr)\/([a-zA-Z0-9_-]+)/i);
                if (m) return `https://www.redgifs.com/watch/${m[1]}`;
                return dataUrl;
              }
              if (isCanonicalMediaPage(dataUrl)) {
                return dataUrl;
              }
            }
          }
        } catch (e) {}
      }
      return null;
    }

    // YouTube
    if (host.includes('youtube.com') || host.includes('youtu.be')) {
      if (isCanonicalMediaPage(currentUrl)) {
        return currentUrl;
      }
      if (video) {
        try {
          const container = video.closest('ytd-rich-item-renderer, ytd-video-renderer, ytd-compact-video-renderer, ytd-reel-item-renderer') || video.parentElement;
          if (container) {
            const permalinkEl = container.querySelector('a#thumbnail[href*="/watch"], a[href*="/watch"], a[href*="/shorts/"]');
            if (permalinkEl && permalinkEl.href && isCanonicalMediaPage(permalinkEl.href)) {
              return permalinkEl.href;
            }
          }
        } catch (e) {}
      }
      return null;
    }

    // Other popular media platforms (Vimeo, Twitch, etc.)
    if (isPopularMediaHost(host)) {
      const tabUrl = (cachedTabInfo && cachedTabInfo.url) || window.location.href;
      return isCanonicalMediaPage(tabUrl) ? tabUrl : null;
    }

    return null;
  }

  function getSlugFromUrl(urlStr) {
    try {
      const u = new URL(urlStr || window.location.href);
      const parts = u.pathname.split('/').filter(Boolean);
      if (parts.length > 0) {
        const last = parts[parts.length - 1].replace(/\.(html?|php|aspx?)$/i, '');
        if (last && last.length > 2 && !/^(index|watch|view|video|player|embed|master)$/i.test(last)) {
          return last.replace(/[_-]+/g, ' ').trim();
        }
      }
    } catch (e) {}
    return "";
  }

  function getVideoTitle(video) {
    const testUrls = [window.location.href, (cachedTabInfo && cachedTabInfo.url) || ""];
    if (video) {
      try {
        const pageUrl = getMediaPageUrl(video);
        if (pageUrl && !testUrls.includes(pageUrl)) {
          testUrls.unshift(pageUrl);
        }
      } catch (e) {}
    }
    try {
      const ogUrl = document.querySelector('meta[property="og:url"]')?.content;
      if (ogUrl && !testUrls.includes(ogUrl)) {
        testUrls.push(ogUrl);
      }
      const canonicalHref = document.querySelector('link[rel="canonical"]')?.href;
      if (canonicalHref && !testUrls.includes(canonicalHref)) {
        testUrls.push(canonicalHref);
      }
    } catch (e) {}

    // Special cases:
    // 1. TikTok: username_id
    for (const u of testUrls) {
      if (u && u.includes('tiktok.com')) {
        const m = u.match(/@([^/?#&]+)\/(?:video|v)\/(\d+)/i);
        if (m) {
          return `${m[1]}_${m[2]}`;
        }
      }
    }

    // 2. Instagram: username-urlid (e.g. filmygyan-Dc_7ZNGChot)
    for (const u of testUrls) {
      if (u && u.includes('instagram.com')) {
        const mId = u.match(/instagram\.com\/(?:[A-Za-z0-9_.]+\/)?(?:reels?|p|tv)\/([A-Za-z0-9_-]+)/i) || u.match(/\/(?:reels?|p|tv)\/([A-Za-z0-9_-]+)/i);
        if (mId) {
          const vId = mId[1];
          let username = "";
          const mUser = u.match(/instagram\.com\/([A-Za-z0-9_.]+)\/(?:reels?|p|tv)\//i);
          if (mUser && !['reels', 'reel', 'p', 'tv', 'explore', 'stories', 'direct', 'accounts'].includes(mUser[1].toLowerCase())) {
            username = mUser[1];
          }
          if (!username && video) {
            try {
              // Search up to container or check document
              let container = video.closest('article, [data-pagelet*="Reel"], [data-pagelet*="FeedUnit"], section, main');
              if (!container || container.matches('[role="presentation"]')) {
                let curr = video.parentElement;
                for (let i = 0; i < 15 && curr && curr !== document.body; i++) {
                  if (curr.querySelector('a[href*="/reel/"], a[href*="/reels/"], a[href*="/p/"]') || curr.tagName === 'ARTICLE') {
                    container = curr;
                    break;
                  }
                  curr = curr.parentElement;
                }
              }
              const scope = container || document;
              const authorLinks = scope.querySelectorAll('header a, a[role="link"], a[href^="/"], a[href*="instagram.com/"]');
              for (const a of authorLinks) {
                const rawHref = a.getAttribute('href') || a.href || '';
                const mHref = rawHref.match(/(?:instagram\.com)?\/([A-Za-z0-9_.]+)(?:\/|\?|$)/i);
                if (mHref && mHref[1]) {
                  const candidate = mHref[1];
                  if (!['explore', 'reels', 'reel', 'direct', 'stories', 'p', 'tv', 'accounts', 'legal', 'about', 'help', 'developer'].includes(candidate.toLowerCase())) {
                    const text = a.innerText.trim();
                    username = (text && !text.includes(' ') && text.length > 1 && !text.includes('\n')) ? text : candidate;
                    break;
                  }
                }
              }
            } catch (e) {}
          }
          if (!username) {
            const ldScript = document.querySelector('script[type="application/ld+json"]');
            if (ldScript) {
              try {
                const ld = JSON.parse(ldScript.textContent);
                const aName = ld?.author?.name || ld?.author?.identifier || (ld?.author?.alternateName ? ld.author.alternateName.replace(/^@/, '') : '');
                if (aName && !['instagram'].includes(aName.toLowerCase())) {
                  username = aName;
                }
              } catch (e) {}
            }
          }
          if (!username) {
            const titlesToTest = [
              document.title || '',
              document.querySelector('meta[property="og:title"]')?.content || '',
              document.querySelector('meta[name="twitter:title"]')?.content || '',
              document.querySelector('meta[property="og:description"]')?.content || '',
              document.querySelector('meta[name="description"]')?.content || ''
            ];
            for (const t of titlesToTest) {
              if (!t) continue;
              const m = t.match(/@([A-Za-z0-9_.]+)/) ||
                        t.match(/(?:^|[\s\-])([A-Za-z0-9_.]+)\s+on\s+(?:Instagram|[A-Za-z]+\s+\d+)/i) ||
                        t.match(/^([A-Za-z0-9_.]+)\s+on Instagram/i) ||
                        t.match(/(?:video|reel)?\s*by\s+([A-Za-z0-9_.]+)/i) ||
                        t.match(/^([A-Za-z0-9_.]+)\s*•\s*Instagram/i);
              if (m && m[1] && !['instagram', 'reels', 'reel', 'video', 'post'].includes(m[1].toLowerCase())) {
                username = m[1];
                break;
              }
            }
          }
          return username ? `${username}-${vId}` : vId;
        }
      }
    }

    // 3. Facebook: url id (e.g. https://www.facebook.com/reel/1674054117674795 -> 1674054117674795)
    for (const u of testUrls) {
      if (u && (u.includes('facebook.com') || u.includes('fb.watch') || u.includes('fb.com'))) {
        const m = u.match(/(?:reel|reels|videos?|share\/[vr])\/([A-Za-z0-9_-]+)/i) || u.match(/[?&]v=(\d+)/i);
        if (m) {
          return m[1];
        }
      }
    }

    // 4. X.com / Twitter: username-status_id (e.g. https://x.com/i_m_harshitsing/status/2095888237944525003/video/1 -> i_m_harshitsing-2095888237944525003)
    for (const u of testUrls) {
      if (u && (u.includes('x.com') || u.includes('twitter.com'))) {
        const m = u.match(/(?:x\.com|twitter\.com)\/([A-Za-z0-9_]+)\/status\/(\d+)/i);
        if (m) {
          const uName = m[1];
          const sId = m[2];
          if (!['i', 'home', 'explore', 'notifications', 'messages', 'search'].includes(uName.toLowerCase())) {
            return `${uName}-${sId}`;
          }
        }
      }
    // 5. Reddit post title
    if (window.location.hostname.includes('reddit.com') && video) {
      try {
        let container = null;
        let curr = video;
        while (curr) {
          if (curr.matches && curr.matches('shreddit-post, [data-test-id="post-container"], .Post, .thing, article')) {
            container = curr;
            break;
          }
          if (curr.parentElement) {
            curr = curr.parentElement;
          } else {
            const root = curr.getRootNode ? curr.getRootNode() : null;
            if (root && root instanceof ShadowRoot && root.host) {
              curr = root.host;
            } else {
              break;
            }
          }
        }
        if (!container && video.closest) {
          container = video.closest('shreddit-post, [data-test-id="post-container"], .Post, .thing, article');
        }
        if (container) {
          const postTitle = container.getAttribute('post-title');
          if (postTitle && !isGenericTitle(postTitle)) {
            return cleanTitleString(postTitle);
          }
          const titleEl = container.querySelector('a[slot="title"], h1[slot="title"], h3, [data-test-id="post-title"], a.title');
          if (titleEl && titleEl.textContent) {
            const t = cleanTitleString(titleEl.textContent);
            if (t && !isGenericTitle(t)) return t;
          }
        }
      } catch (e) {}
    }

    // 6. RedGifs id title
    for (const u of testUrls) {
      if (u && u.includes('redgifs.com')) {
        const m = u.match(/redgifs\.com\/(?:watch|ifr)\/([a-zA-Z0-9_-]+)/i);
        if (m) {
          return `redgifs-${m[1]}`;
        }
      }
    }

    if (activeIframeData && activeIframeData.title) {
      const t = cleanTitleString(activeIframeData.title);
      if (t && !isGenericTitle(t) && !t.toLowerCase().includes('embed') && t.toLowerCase() !== 'index') return t;
    }
    if (ytMediaInfo && ytMediaInfo.title) {
      const t = cleanTitleString(ytMediaInfo.title);
      if (t && !isGenericTitle(t)) return t;
    }
    const ytTitle = document.querySelector('h1.ytd-watch-metadata, #title h1, h1.title');
    if (ytTitle && ytTitle.innerText.trim()) {
      const t = cleanTitleString(ytTitle.innerText);
      if (t && !isGenericTitle(t)) return t;
    }
    if (cachedTabInfo && cachedTabInfo.title) {
      let t = cleanTitleString(cachedTabInfo.title);
      if (t && !isGenericTitle(t) && !t.toLowerCase().includes('embed') && t.toLowerCase() !== 'index') return t;
    }
    const metaTitle = document.querySelector('meta[property="og:title"], meta[name="twitter:title"]');
    if (metaTitle && metaTitle.content && metaTitle.content.trim()) {
      const t = cleanTitleString(metaTitle.content);
      if (t && !isGenericTitle(t) && !t.toLowerCase().includes('embed') && t.toLowerCase() !== 'index') return t;
    }
    if (video && video.title && video.title.trim()) {
      const t = cleanTitleString(video.title);
      if (t && !isGenericTitle(t)) return t;
    }
    // Check social container captions (Facebook, Instagram, etc.)
    if (video) {
      try {
        const container = video.closest('[role="article"], [data-pagelet*="FeedUnit"], [data-pagelet*="Reel"], div[role="main"]');
        if (container) {
          const captionEl = container.querySelector('[data-ad-preview="message"], div[dir="auto"][style*="text-align"]');
          if (captionEl && captionEl.innerText && captionEl.innerText.trim()) {
            const cap = cleanTitleString(captionEl.innerText.trim().split('\n')[0]);
            if (cap && !isGenericTitle(cap)) {
              return cap.length > 80 ? cap.substring(0, 80) : cap;
            }
          }
        }
      } catch (e) {}
    }
    if (document.title && document.title.trim()) {
      let dt = cleanTitleString(document.title);
      if (dt && !isGenericTitle(dt) && !dt.toLowerCase().includes('embed') && dt.toLowerCase() !== 'index') {
        return dt;
      }
    }
    const slug = getSlugFromUrl(window.location.href) || ((cachedTabInfo && cachedTabInfo.url) ? getSlugFromUrl(cachedTabInfo.url) : "");
    if (slug && !isGenericTitle(slug)) return slug;

    // Extract ID-based title for Twitter or generic platforms
    for (const u of testUrls) {
      if (u && (u.includes('twitter.com') || u.includes('x.com'))) {
        const m = u.match(/([^/?#&]+)\/status\/(\d+)/i);
        if (m && !['home', 'explore', 'messages', 'i'].includes(m[1].toLowerCase())) {
          return `${m[1]}-${m[2]}`;
        }
      }
      if (u) {
        const mAny = u.match(/\/(?:watch|video|v|post|embed|p)\/([A-Za-z0-9_-]{5,})/i);
        if (mAny) {
          const hostClean = window.location.hostname.replace(/^www\./, '').split('.')[0];
          return `${hostClean}-${mAny[1]}`;
        }
      }
    }

    return `${getPlatformName()} Video`;
  }

  function formatDuration(sec) {
    if (!sec || isNaN(sec) || !isFinite(sec) || sec <= 0) return "";
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = Math.floor(sec % 60);
    const pad = (n) => String(n).padStart(2, '0');
    return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
  }

  function estimateFileSize(durationSec, bitrateKbps, isAudio) {
    if (!durationSec || isNaN(durationSec) || !isFinite(durationSec) || durationSec <= 0) return "~ MB";
    const bytes = durationSec * bitrateKbps * 125;
    if (bytes >= 1073741824) {
      return (bytes / 1073741824).toFixed(1) + " GB";
    } else if (bytes >= 1048576) {
      return (bytes / 1048576).toFixed(1) + " MB";
    } else {
      return (bytes / 1024).toFixed(0) + " KB";
    }
  }

  function estimateFileSizeBytes(durationSec, bitrateKbps) {
    if (!durationSec || isNaN(durationSec) || !isFinite(durationSec) || durationSec <= 0) return 0;
    return Math.round(durationSec * (bitrateKbps || 2500) * 125);
  }

  // 9. Supported Resolutions Filtering (Never show unsupported qualities!)
  function getSupportedResolutions(video) {
    const isYouTube = window.location.hostname.includes('youtube.com');
    const duration = (ytMediaInfo && ytMediaInfo.duration) ||
                     (activeIframeData && activeIframeData.duration) ||
                     (video && video.duration) || 0;

    // A. Check YouTube Player API Levels
    if (isYouTube && ytMediaInfo && Array.isArray(ytMediaInfo.levels) && ytMediaInfo.levels.length > 0) {
      const ytLevelMap = {
        'highres': { quality: '4K (2160p)', badge: '4K', label: '4K Ultra HD', height: 2160, bitrate: 22000, cls: 'uhd' },
        'hd2880': { quality: '5K (2880p)', badge: '5K', label: '5K Ultra HD', height: 2880, bitrate: 30000, cls: 'uhd' },
        'hd2160': { quality: '4K (2160p)', badge: '4K', label: '4K Ultra HD', height: 2160, bitrate: 22000, cls: 'uhd' },
        'hd1440': { quality: '2K (1440p)', badge: '2K', label: '2K Quad HD', height: 1440, bitrate: 12000, cls: 'uhd' },
        'hd1080': { quality: '1080p', badge: '1080p', label: '1080p Full HD', height: 1080, bitrate: 5000, cls: 'hd' },
        'hd720': { quality: '720p', badge: '720p', label: '720p HD', height: 720, bitrate: 2500, cls: 'hd' },
        'large': { quality: '480p', badge: '480p', label: '480p SD', height: 480, bitrate: 1200, cls: '' },
        'medium': { quality: '360p', badge: '360p', label: '360p', height: 360, bitrate: 700, cls: '' },
        'small': { quality: '240p', badge: '240p', label: '240p', height: 240, bitrate: 400, cls: '' },
        'tiny': { quality: '144p', badge: '144p', label: '144p', height: 144, bitrate: 200, cls: '' }
      };

      const result = [];
      const seenQualities = new Set();
      for (const lvl of ytMediaInfo.levels) {
        const item = ytLevelMap[lvl];
        if (item && !seenQualities.has(item.quality)) {
          seenQualities.add(item.quality);
          result.push({
            ...item,
            sizeBytes: estimateFileSizeBytes(duration, item.bitrate),
            size: estimateFileSize(duration, item.bitrate, false)
          });
        }
      }

      // Append Audio Only Option
      result.push({
        quality: 'Audio Only (MP3)',
        badge: 'MP3',
        label: 'Audio Only',
        height: 0,
        bitrate: 192,
        cls: 'audio',
        isAudio: true,
        sizeBytes: estimateFileSizeBytes(duration, 192),
        size: estimateFileSize(duration, 192, true)
      });

      if (result.length > 1) {
        return result;
      }
    }

    // B. If an HLS (m3u8), DASH, or direct media stream was sniffed for this tab (only on generic sites)
    const isPopular = isPopularMediaHost(window.location.hostname);
    if (!isPopular) {
      const masterStream = sniffedMediaStreams.find(s => s.url.includes('master.m3u8') || s.url.includes('master.mpd'));
      const m3u8Stream = masterStream || sniffedMediaStreams.find(s => s.url.includes('.m3u8') || s.url.includes('.mpd'));
      const directStream = sniffedMediaStreams.slice().reverse().find(s => /\.(mp4|webm|vid|mkv)(\?|$)/i.test(s.url) || (s.contentType && s.contentType.includes('video/')));
      const streamCandidate = m3u8Stream || directStream || (activeIframeData && activeIframeData.streamUrl ? { url: activeIframeData.streamUrl } : null);

      if (streamCandidate) {
        const vh = (activeIframeData && activeIframeData.videoHeight) || (video && video.videoHeight) || 720;
        const resLabel = vh >= 1080 ? '1080p Full HD' : (vh >= 720 ? '720p HD' : (vh >= 480 ? '480p SD' : `${vh}p`));
        const resBadge = vh >= 1080 ? '1080p' : (vh >= 720 ? '720p' : (vh >= 480 ? '480p' : `${vh}p`));
        const resCls = vh >= 720 ? 'hd' : '';
        const tag = m3u8Stream ? '(HLS Stream)' : '(Media Stream)';

        return [
          {
            quality: `${resBadge} ${tag}`,
            badge: resBadge,
            label: `${resLabel} ${tag}`,
            height: vh,
            bitrate: vh >= 1080 ? 5000 : 2500,
            cls: resCls,
            streamUrl: streamCandidate.url,
            sizeBytes: estimateFileSizeBytes(duration, vh >= 1080 ? 5000 : 2500),
            size: estimateFileSize(duration, vh >= 1080 ? 5000 : 2500, false)
          },
          {
            quality: 'Audio Only (MP3)',
            badge: 'MP3',
            label: 'Audio Only',
            height: 0,
            bitrate: 192,
            cls: 'audio',
            isAudio: true,
            streamUrl: streamCandidate.url,
            sizeBytes: estimateFileSizeBytes(duration, 192),
            size: estimateFileSize(duration, 192, true)
          }
        ];
      }
    }

    // C. Standard Video Height Filtering (Generic sites or fallback)
    const rawVh = (activeIframeData && activeIframeData.videoHeight) || (video && video.videoHeight) || 0;
    const rawVw = (activeIframeData && activeIframeData.videoWidth) || (video && video.videoWidth) || 0;
    // For vertical videos (TikTok, YouTube Shorts, Reels), use maximum dimension to preserve 720p/1080p options
    const vh = Math.max(rawVh, rawVw) || 720;
    const allTiers = [
      { quality: '2160p (4K)', badge: '4K', label: '4K Ultra HD', height: 2160, bitrate: 22000, cls: 'uhd' },
      { quality: '1440p (2K)', badge: '2K', label: '2K Quad HD', height: 1440, bitrate: 12000, cls: 'uhd' },
      { quality: '1080p', badge: '1080p', label: '1080p Full HD', height: 1080, bitrate: 5000, cls: 'hd' },
      { quality: '720p', badge: '720p', label: '720p HD', height: 720, bitrate: 2500, cls: 'hd' },
      { quality: '480p', badge: '480p', label: '480p SD', height: 480, bitrate: 1200, cls: '' },
      { quality: '360p', badge: '360p', label: '360p', height: 360, bitrate: 700, cls: '' }
    ];

    // Strictly filter out any resolution tier higher than the video's actual dimensions
    let filtered = allTiers
      .filter(t => t.height <= vh)
      .map(t => ({
        ...t,
        sizeBytes: estimateFileSizeBytes(duration, t.bitrate),
        size: estimateFileSize(duration, t.bitrate, false)
      }));

    // If dimensions check was overly strict or metadata not ready, provide standard tiers (1080p, 720p, 480p, 360p)
    if (filtered.length === 0) {
      filtered = allTiers.slice(2).map(t => ({
        ...t,
        sizeBytes: estimateFileSizeBytes(duration, t.bitrate),
        size: estimateFileSize(duration, t.bitrate, false)
      }));
    }

    // Add Audio Option
    filtered.push({
      quality: 'Audio Only (MP3)',
      badge: 'MP3',
      label: 'Audio Only',
      height: 0,
      bitrate: 192,
      cls: 'audio',
      isAudio: true,
      sizeBytes: estimateFileSizeBytes(duration, 192),
      size: estimateFileSize(duration, 192, true)
    });

    return filtered;
  }

  // 10. Render Dropdown Contents
  function populateDropdown() {
    if (!activeVideo) return;
    const title = getVideoTitle(activeVideo);
    titleEl.textContent = title;
    titleEl.title = title;

    badgeEl.textContent = getPlatformName();

    const dur = (ytMediaInfo && ytMediaInfo.duration) ||
                (activeIframeData && activeIframeData.duration) ||
                (activeVideo && activeVideo.duration) || 0;
    const durStr = formatDuration(dur);
    durationEl.textContent = durStr ? `Duration: ${durStr}` : 'Streaming';

    listEl.innerHTML = '';
    const resolutions = getSupportedResolutions(activeVideo);

    resolutions.forEach((tier) => {
      const row = document.createElement('div');
      row.className = 'bdm-item';
      row.innerHTML = `
        <div class="bdm-item-left">
          <span class="bdm-res-badge ${tier.cls}">${tier.badge}</span>
          <span class="bdm-res-label">${tier.label}</span>
        </div>
        <div class="bdm-item-right">
          <span class="bdm-res-size">${tier.size}</span>
          <svg class="bdm-dl-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
        </div>
      `;

      row.addEventListener('click', (e) => {
        e.stopPropagation();
        triggerDownload(tier);
      });

      listEl.appendChild(row);
    });
  }

  // 11. Trigger Download via Bengal DM
  function triggerDownload(tier) {
    if (!activeVideo) return;
    const rawTitle = getVideoTitle(activeVideo);
    const title = isGenericTitle(rawTitle) ? "" : rawTitle;
    let targetUrl = "";

    const mediaPageUrl = getMediaPageUrl(activeVideo);
    if (mediaPageUrl) {
      targetUrl = mediaPageUrl;
    } else {
      // 1. Direct stream URL attached to tier (e.g. master m3u8)
      if (tier.streamUrl && (tier.streamUrl.startsWith('http://') || tier.streamUrl.startsWith('https://'))) {
        targetUrl = tier.streamUrl;
      } else if (sniffedMediaStreams.length > 0) {
        // 2. Sniffed m3u8 or media stream from background (prefer master playlist)
        const masterStream = sniffedMediaStreams.find(s => s.url.includes('master.m3u8') || s.url.includes('master.mpd'));
        const m3u8 = masterStream || sniffedMediaStreams.find(s => s.url.includes('.m3u8') || s.url.includes('.mpd'));
        const direct = sniffedMediaStreams.slice().reverse().find(s => /\.(mp4|webm|vid)(\?|$)/i.test(s.url));
        targetUrl = m3u8 ? m3u8.url : (direct ? direct.url : sniffedMediaStreams[0].url);
      } else if (activeIframeData && activeIframeData.currentSrc && (activeIframeData.currentSrc.startsWith('http://') || activeIframeData.currentSrc.startsWith('https://'))) {
        targetUrl = activeIframeData.currentSrc;
      } else if (activeIframeData && activeIframeData.streamUrl && (activeIframeData.streamUrl.startsWith('http://') || activeIframeData.streamUrl.startsWith('https://'))) {
        targetUrl = activeIframeData.streamUrl;
      } else if (activeVideo.tagName !== 'IFRAME' && activeVideo.currentSrc && (activeVideo.currentSrc.startsWith('http://') || activeVideo.currentSrc.startsWith('https://'))) {
        targetUrl = activeVideo.currentSrc;
      } else if (activeVideo.tagName !== 'IFRAME' && activeVideo.src && (activeVideo.src.startsWith('http://') || activeVideo.src.startsWith('https://'))) {
        targetUrl = activeVideo.src;
      } else if (cachedTabInfo && cachedTabInfo.url && isCanonicalMediaPage(cachedTabInfo.url)) {
        targetUrl = cachedTabInfo.url;
      } else if (isCanonicalMediaPage(window.location.href)) {
        targetUrl = window.location.href;
      }
    }

    if (!targetUrl) {
      try {
        let playerEl = null;
        let curr = activeVideo;
        while (curr) {
          if (curr.matches && curr.matches('shreddit-player')) {
            playerEl = curr;
            break;
          }
          if (curr.parentElement) {
            curr = curr.parentElement;
          } else {
            const root = curr.getRootNode ? curr.getRootNode() : null;
            if (root && root instanceof ShadowRoot && root.host) {
              curr = root.host;
            } else {
              break;
            }
          }
        }
        if (!playerEl && activeVideo.closest) {
          playerEl = activeVideo.closest('shreddit-player');
        }
        if (playerEl) {
          const pSrc = playerEl.getAttribute('src');
          if (pSrc && (pSrc.startsWith('http://') || pSrc.startsWith('https://'))) {
            targetUrl = pSrc;
          }
        }
      } catch (e) {}

      if (!targetUrl) {
        if (activeVideo.tagName !== 'IFRAME' && activeVideo.currentSrc && activeVideo.currentSrc.startsWith('http')) {
          targetUrl = activeVideo.currentSrc;
        } else if (activeVideo.tagName !== 'IFRAME' && activeVideo.src && activeVideo.src.startsWith('http')) {
          targetUrl = activeVideo.src;
        } else {
          targetUrl = window.location.href;
        }
      }
    }

    function isHtmlOrEmbedUrl(u) {
      if (!u) return true;
      try {
        const parsed = new URL(u);
        const p = parsed.pathname.toLowerCase();
        if (/\.(m3u8|mpd|mp4|webm|mkv|flv|vid|m4s)(\?|$)/i.test(p)) return false;
        return true;
      } catch {
        return true;
      }
    }

    const doSend = (finalTarget) => {
      footerEl.classList.add('opening');
      footerTextEl.textContent = 'Downloading with Bengal DM.';

      chrome.runtime.sendMessage({
        action: "send_to_bengal",
        url: finalTarget,
        referrer: (cachedTabInfo && cachedTabInfo.url) || window.location.href,
        isMedia: true,
        title: title,
        filename: title,
        quality: tier.quality,
        sizeBytes: tier.sizeBytes || 0,
        sizeStr: tier.size || ""
      }, (response) => {
        setTimeout(() => {
          closeDropdown();
        }, 1200);
      });
    };

    const isPopular = isPopularMediaHost(window.location.hostname);
    if (!isPopular && isHtmlOrEmbedUrl(targetUrl)) {
      chrome.runtime.sendMessage({ action: "get_sniffed_media" }, (res) => {
        if (res && Array.isArray(res.streams) && res.streams.length > 0) {
          const master = res.streams.find(s => s.url.includes('master.m3u8') || s.url.includes('master.mpd'));
          const m3u8 = master || res.streams.find(s => s.url.includes('.m3u8') || s.url.includes('.mpd'));
          const direct = res.streams.slice().reverse().find(s => /\.(mp4|webm|vid)(\?|$)/i.test(s.url) || (s.contentType && s.contentType.includes('video/')));
          const best = m3u8 || direct || res.streams[0];
          if (best && best.url) {
            targetUrl = best.url;
          }
        }
        doSend(targetUrl);
      });
      return;
    }

    doSend(targetUrl);
  }

  // 12. Widget Display & Positioning
  function updateWidgetPosition() {
    if (!activeVideo || !root.classList.contains('visible') || !isAppConnected || !enableMediaSniffing) return;

    const rect = activeVideo.getBoundingClientRect();
    if (rect.bottom <= 0 || rect.top >= window.innerHeight || rect.right <= 0 || rect.left >= window.innerWidth) {
      root.style.display = 'none';
      return;
    }

    if (isUserPositioned) {
      root.style.display = 'flex';
      root.style.left = `${userCoords.left}px`;
      root.style.top = `${userCoords.top}px`;
      root.style.right = 'auto';
      root.style.bottom = 'auto';
      return;
    }

    const pillW = pill.offsetWidth || 34;
    const pillH = pill.offsetHeight || 34;
    const pad = 16;
    const isTikTok = window.location.hostname.includes('tiktok.com');
    // TikTok has native overlays: top header actions (~48px) and bottom control bar (~56px) with fullscreen button
    const tiktokTopOffset = isTikTok ? 52 : 0;
    const tiktokBottomOffset = isTikTok ? 48 : 0;
    let left;
    let top;

    switch (videoPanelPosition) {
      case 'top-left':
        left = rect.left + pad;
        top = rect.top + pad + tiktokTopOffset;
        break;
      case 'top-center':
        left = rect.left + (rect.width - pillW) / 2;
        top = rect.top + pad + tiktokTopOffset;
        break;
      case 'center':
        left = rect.left + (rect.width - pillW) / 2;
        top = rect.top + (rect.height - pillH) / 2;
        break;
      case 'bottom-left':
        left = rect.left + pad;
        top = rect.bottom - pillH - 24 - tiktokBottomOffset;
        break;
      case 'bottom-center':
        left = rect.left + (rect.width - pillW) / 2;
        top = rect.bottom - pillH - 24 - tiktokBottomOffset;
        break;
      case 'bottom-right':
        left = rect.right - pillW - pad;
        top = rect.bottom - pillH - 24 - tiktokBottomOffset;
        break;
      case 'top-right':
      default:
        left = rect.right - pillW - pad;
        top = rect.top + pad + tiktokTopOffset;
        break;
    }

    const validPositions = ['top-right', 'top-left', 'top-center', 'center', 'bottom-right', 'bottom-left', 'bottom-center'];
    const activePosClass = `pos-${videoPanelPosition}`;
    validPositions.forEach(p => root.classList.remove(`pos-${p}`));
    root.classList.add(validPositions.includes(videoPanelPosition) ? activePosClass : 'pos-top-right');

    // Horizontal bounds: keep pill within window margins if video is on screen
    left = Math.max(8, Math.min(window.innerWidth - pillW - 8, left));

    // Vertical bounds:
    // If the widget's calculated position is completely outside the viewport
    // (e.g. video top has scrolled off the top of the browser screen), hide it.
    // NEVER clamp top with Math.max(8, ...), which freezes the popup at the top of the screen!
    if (top + pillH <= 0 || top >= window.innerHeight) {
      root.style.display = 'none';
      if (isDropdownOpen) {
        closeDropdown();
      }
      return;
    }

    root.style.display = 'flex';
    root.style.left = `${left}px`;
    root.style.top = `${top}px`;
    root.style.right = 'auto';
    root.style.bottom = 'auto';
  }

  function showWidget() {
    if (window.self !== window.top && isTopHandlingWidget && !document.fullscreenElement) {
      hideWidget('iframe_top_handling');
      return;
    }
    if (activeVideo && (dismissedVideos.has(activeVideo) || dismissedVideos.has(getVideoKey(activeVideo)))) {
      hideWidget('activeVideo_dismissed');
      return;
    }
    if (activeIframeVideo && (dismissedVideos.has(activeIframeVideo) || dismissedVideos.has(getVideoKey(activeIframeVideo)))) {
      hideWidget('activeIframeVideo_dismissed');
      return;
    }
    host.dataset.appConnected = String(isAppConnected);
    host.dataset.sniffing = String(enableMediaSniffing);
    host.dataset.blacklisted = String(isSiteBlacklisted());
    if (!isAppConnected || !enableMediaSniffing || isSiteBlacklisted()) {
      hideWidget('showWidget_disabled_or_blacklisted');
      return;
    }
    ensureAttached();
    host.dataset.visible = 'true';
    root.classList.add('visible');
    root.style.display = 'flex';
    updateWidgetPosition();
    resetIdleTimer();
  }

  let videoResizeObserver = null;
  function observeVideoGeometry(video) {
    if (videoResizeObserver) {
      videoResizeObserver.disconnect();
      videoResizeObserver = null;
    }
    if (!video || typeof ResizeObserver === 'undefined') return;
    try {
      videoResizeObserver = new ResizeObserver(() => {
        if (activeVideo === video && root.classList.contains('visible')) {
          updateWidgetPosition();
        }
      });
      videoResizeObserver.observe(video);
      if (video.parentElement) {
        videoResizeObserver.observe(video.parentElement);
      }
    } catch (e) {}
  }

  function hideWidget(reason = 'unknown') {
    host.dataset.visible = 'false';
    host.dataset.hideReason = reason;
    clearIdleTimer();
    closeDropdown();
    observeVideoGeometry(null);
    root.classList.remove('visible');
    root.style.display = 'none';
  }

  let lastToggleTime = 0;
  let lastOpenedTime = 0;

  function toggleDropdown() {
    const now = Date.now();
    if (now - lastToggleTime < 350) return;
    lastToggleTime = now;
    if (isDropdownOpen) {
      closeDropdown();
    } else {
      openDropdown();
    }
  }

  function openDropdown() {
    lastOpenedTime = Date.now();
    isDropdownOpen = true;
    clearIdleTimer();
    root.classList.add('open');
    footerEl.classList.remove('opening');
    footerTextEl.textContent = 'Bengal Download Manager';

    const isCenterPos = ['top-center', 'center', 'bottom-center'].includes(videoPanelPosition);
    const isBottomPos = ['bottom-left', 'bottom-right', 'bottom-center'].includes(videoPanelPosition);

    if (isUserPositioned) {
      const rect = root.getBoundingClientRect();
      if (rect.left < 160) {
        dropdown.style.left = '0';
        dropdown.style.right = 'auto';
        dropdown.style.transform = 'none';
      } else if (window.innerWidth - rect.right < 160) {
        dropdown.style.left = 'auto';
        dropdown.style.right = '0';
        dropdown.style.transform = 'none';
      } else {
        dropdown.style.left = '50%';
        dropdown.style.right = 'auto';
        dropdown.style.transform = 'translateX(-50%)';
      }
      dropdown.style.top = 'calc(100% + 6px)';
      dropdown.style.bottom = 'auto';
    } else if (isCenterPos) {
      dropdown.style.left = '50%';
      dropdown.style.right = 'auto';
      dropdown.style.transform = 'translateX(-50%)';
      if (isBottomPos) {
        dropdown.style.top = 'auto';
        dropdown.style.bottom = 'calc(100% + 6px)';
      } else {
        dropdown.style.top = 'calc(100% + 6px)';
        dropdown.style.bottom = 'auto';
      }
    } else if (['top-left', 'bottom-left'].includes(videoPanelPosition)) {
      dropdown.style.left = '0';
      dropdown.style.right = 'auto';
      dropdown.style.transform = 'none';
      if (isBottomPos) {
        dropdown.style.top = 'auto';
        dropdown.style.bottom = 'calc(100% + 6px)';
      } else {
        dropdown.style.top = 'calc(100% + 6px)';
        dropdown.style.bottom = 'auto';
      }
    } else {
      dropdown.style.left = 'auto';
      dropdown.style.right = '0';
      dropdown.style.transform = 'none';
      if (isBottomPos) {
        dropdown.style.top = 'auto';
        dropdown.style.bottom = 'calc(100% + 6px)';
      } else {
        dropdown.style.top = 'calc(100% + 6px)';
        dropdown.style.bottom = 'auto';
      }
    }

    requestMediaInfo();
    populateDropdown();
  }

  function closeDropdown() {
    isDropdownOpen = false;
    root.classList.remove('open');
    footerEl.classList.remove('opening');
    footerTextEl.textContent = 'Bengal Download Manager';
    resetIdleTimer();
  }

  // Close dropdown on outside click
  document.addEventListener('click', (e) => {
    if (Date.now() - lastOpenedTime < 350) return;
    const path = e.composedPath ? e.composedPath() : [];
    if (isDropdownOpen && !path.includes(host) && !host.contains(e.target)) {
      closeDropdown();
    }
  });

  // 13. Video State Observation
  function onVideoState(video) {
    if (!enableMediaSniffing || isSiteBlacklisted()) return;
    if (!video) return;

    if (dismissedVideos.has(video) || dismissedVideos.has(getVideoKey(video))) {
      if (activeVideo === video) {
        hideWidget('video_dismissed');
        activeVideo = null;
      }
      return;
    }

    if (!isAppConnected) {
      checkConnectionStatus((connected) => {
        if (connected && video && !isSiteBlacklisted()) {
          onVideoState(video);
        }
      });
      return;
    }

    const hasPlayed = playedVideos.has(video) || (activeVideo === video);
    if (!isValidPlayedVideo(video, hasPlayed)) {
      if (activeVideo === video && !isDropdownOpen) {
        hideWidget();
        activeVideo = null;
      }
      return;
    }

    if (!video.paused) {
      playedVideos.add(video);
    }

    // If inside an iframe, delegate to top window so user can move icon outside iframe
    if (window.self !== window.top && !document.fullscreenElement) {
      notifyTopFrameVideo(video, video.paused ? 'paused' : 'playing');
      if (isTopHandlingWidget) {
        hideWidget('top_is_handling');
        activeVideo = video;
        return;
      }
      // Debounce showing in iframe to allow top frame handshake to complete
      setTimeout(() => {
        if (!isTopHandlingWidget && !document.fullscreenElement && (activeVideo === video || !activeVideo)) {
          if (isValidPlayedVideo(video, true)) {
            activeVideo = video;
            showWidget();
          }
        }
      }, 300);
      return;
    }

    if (activeVideo !== video) {
      activeVideo = video;
      observeVideoGeometry(video);
      requestMediaInfo();
    }
    showWidget();
  }

  // Hover over video or custom player container (Facebook, X, YouTube, iframe embeds, etc.) to show widget
  document.addEventListener('mouseover', (e) => {
    if (window.self !== window.top && isTopHandlingWidget && !document.fullscreenElement) return;
    if (!enableMediaSniffing || isDropdownOpen || isSiteBlacklisted()) return;
    const target = e.target;
    if (!target) return;

    // If mouse is within our own dock/pill/dropdown, ignore
    const path = e.composedPath ? e.composedPath() : [];
    if (path.includes(host) || host.contains(target)) {
      return;
    }

    if (activeIframeVideo && (target === activeIframeVideo || (target.contains && target.contains(activeIframeVideo)) || (target.closest && target.closest('#player, .player, .movieplayer, .videocontainer, .playcontainer')))) {
      if (dismissedVideos.has(activeIframeVideo) || dismissedVideos.has(getVideoKey(activeIframeVideo))) {
        return;
      }
      if (!root.classList.contains('visible')) {
        showWidget();
      }
      return;
    }

    // If active video is actively playing and valid in the viewport:
    // Moving the mouse over the video, its player wrapper, or its native controls frame (e.g. TikTok frame)
    // MUST NEVER disrupt, swap, or hide activeVideo!
    if (activeVideo && !activeVideo.paused && isValidPlayedVideo(activeVideo, false)) {
      if (dismissedVideos.has(activeVideo) || dismissedVideos.has(getVideoKey(activeVideo))) {
        return;
      }
      const isOverActive = target === activeVideo ||
        (activeVideo.parentElement && activeVideo.parentElement.contains(target)) ||
        (target.closest && (
          target.closest('div.xgplayer, div[id*="xgwrapper"], div[class*="DivVideoWrapper"], [data-e2e="feed-video"], [data-e2e="video-player"]') === activeVideo.closest('div.xgplayer, div[id*="xgwrapper"], div[class*="DivVideoWrapper"], [data-e2e="feed-video"], [data-e2e="video-player"]') ||
          target.closest('.html5-video-player, #movie_player, .video-js, .jwplayer, .plyr, .dplayer') === activeVideo.closest('.html5-video-player, #movie_player, .video-js, .jwplayer, .plyr, .dplayer')
        ));
      if (isOverActive) {
        if (!root.classList.contains('visible')) {
          showWidget();
        }
        return;
      }
    }

    const video = (target instanceof HTMLVideoElement || target.tagName === 'VIDEO')
      ? target
      : (target.closest ? (target.closest('[data-testid="videoComponent"], [data-testid="videoPlayer"], article[data-testid="tweet"], [role="article"], [data-pagelet*="Reel"], [data-pagelet*="FeedUnit"], div[role="dialog"], div[data-video-id], div[aria-label*="Video"], [data-testid="tweetPhoto"], [data-testid="placementTracking"], div.player, div#player, div.movieplayer, div.videocontainer, div.playcontainer, div#player_el, .video-js, .jwplayer, .plyr, .dplayer, .artplayer, .clappr-player, .fluid_video_wrapper, .html5-video-player, [data-e2e="feed-item"], [data-e2e="user-post-item"], div[id*="xgwrapper"], div.xgplayer, [data-e2e="feed-video"], [data-e2e="browse-video"], [data-e2e="video-player"], [data-e2e="search-video"], div[class*="DivVideoWrapper"], div[class*="DivItemContainer"]') || target.parentElement)?.querySelector('video') : null);
    if (video && (!video.paused || playedVideos.has(video) || video.currentTime > 0)) {
      if (isValidPlayedVideo(video, true)) {
        if (activeVideo && activeVideo !== video && !activeVideo.paused && video.paused) {
          return;
        }
        if (activeVideo !== video) {
          onVideoState(video);
        } else if (!root.classList.contains('visible')) {
          showWidget();
        }
      }
    }
  }, { passive: true });

  document.addEventListener('play', (e) => {
    if (isSiteBlacklisted()) return;
    if (e.target instanceof HTMLVideoElement || e.target.tagName === 'VIDEO') {
      setTimeout(() => onVideoState(e.target), 150);
    }
  }, true);

  document.addEventListener('playing', (e) => {
    if (isSiteBlacklisted()) return;
    if (e.target instanceof HTMLVideoElement || e.target.tagName === 'VIDEO') {
      playedVideos.add(e.target);
      onVideoState(e.target);
    }
  }, true);

  document.addEventListener('timeupdate', (e) => {
    if (isSiteBlacklisted()) return;
    if (e.target instanceof HTMLVideoElement || e.target.tagName === 'VIDEO') {
      if (e.target.currentTime > 0.1) {
        playedVideos.add(e.target);
      }
      if (!activeVideo || activeVideo === e.target) {
        onVideoState(e.target);
      }
    }
  }, true);

  document.addEventListener('loadedmetadata', (e) => {
    if (isSiteBlacklisted()) return;
    if (e.target instanceof HTMLVideoElement || e.target.tagName === 'VIDEO') {
      if (!e.target.paused || playedVideos.has(e.target)) {
        onVideoState(e.target);
      }
    }
  }, true);

  document.addEventListener('canplay', (e) => {
    if (isSiteBlacklisted()) return;
    if (e.target instanceof HTMLVideoElement || e.target.tagName === 'VIDEO') {
      if (!e.target.paused || playedVideos.has(e.target)) {
        onVideoState(e.target);
      }
    }
  }, true);

  // Pausing video must NOT hide the popup! Keep it visible so user can click download.
  document.addEventListener('pause', (e) => {
    if (e.target === activeVideo) {
      updateWidgetPosition();
    }
  }, true);

  // Dynamically update resolutions if player upgrades quality during playback
  document.addEventListener('resize', (e) => {
    if (e.target === activeVideo && isDropdownOpen) {
      populateDropdown();
    }
  }, true);

  // Periodic active video scanner (crucial for custom iframe video players and fullscreen transitions)
  setInterval(() => {
    if (window.self !== window.top && isTopHandlingWidget && !document.fullscreenElement) {
      if (root.classList.contains('visible') || host.dataset.visible === 'true') {
        hideWidget('interval_iframe_top_handling');
      }
      return;
    }

    if (isSiteBlacklisted()) {
      if (root.classList.contains('visible') || host.dataset.visible === 'true') {
        hideWidget('interval_blacklisted');
      }
      return;
    }
    if (!isAppConnected) {
      checkConnectionStatus();
    }
    ensureAttached();
    if (activeVideo) {
      if (isDropdownOpen) {
        updateWidgetPosition();
        return;
      }
      if (!document.contains(activeVideo) || dismissedVideos.has(activeVideo) || dismissedVideos.has(getVideoKey(activeVideo))) {
        hideWidget();
        activeVideo = null;
      } else if (activeVideo.tagName === 'VIDEO' && !isValidPlayedVideo(activeVideo, true)) {
        hideWidget();
        activeVideo = null;
      } else {
        if (!root.classList.contains('visible') && isAppConnected && enableMediaSniffing) {
          showWidget();
        } else {
          updateWidgetPosition();
        }
        return;
      }
    }

    const videos = Array.from(document.querySelectorAll('video'));
    // IDM Pattern: Filter to valid videos in viewport and rank by visible area
    const validCandidates = videos.filter(v => isValidPlayedVideo(v, true));
    if (validCandidates.length > 0) {
      // First prioritize playing videos
      const playingCandidates = validCandidates.filter(v => !v.paused);
      if (playingCandidates.length > 0) {
        // Pick the playing video with the largest visible bounding area
        let best = playingCandidates[0];
        let maxArea = (best.clientWidth || best.videoWidth || 1) * (best.clientHeight || best.videoHeight || 1);
        for (let i = 1; i < playingCandidates.length; i++) {
          const area = (playingCandidates[i].clientWidth || playingCandidates[i].videoWidth || 1) * (playingCandidates[i].clientHeight || playingCandidates[i].videoHeight || 1);
          if (area > maxArea) {
            maxArea = area;
            best = playingCandidates[i];
          }
        }
        if (activeVideo !== best) {
          onVideoState(best);
        } else if (!root.classList.contains('visible') && isAppConnected && enableMediaSniffing) {
          showWidget();
        }
        return;
      }

      // If none currently playing, pick played/in-progress video with largest area
      const playedCandidates = validCandidates.filter(v => playedVideos.has(v) || v.currentTime > 0);
      if (playedCandidates.length > 0) {
        let best = playedCandidates[0];
        let maxArea = (best.clientWidth || best.videoWidth || 1) * (best.clientHeight || best.videoHeight || 1);
        for (let i = 1; i < playedCandidates.length; i++) {
          const area = (playedCandidates[i].clientWidth || playedCandidates[i].videoWidth || 1) * (playedCandidates[i].clientHeight || playedCandidates[i].videoHeight || 1);
          if (area > maxArea) {
            maxArea = area;
            best = playedCandidates[i];
          }
        }
        if (activeVideo !== best) {
          onVideoState(best);
        } else if (!root.classList.contains('visible') && isAppConnected && enableMediaSniffing) {
          showWidget();
        }
      }
    }
  }, 500);

  window.addEventListener('scroll', updateWidgetPosition, { passive: true, capture: true });
  window.addEventListener('resize', updateWidgetPosition, { passive: true });
})();
