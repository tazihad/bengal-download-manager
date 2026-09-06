const IGNORED_EXTENSIONS = [
  'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif', 'tif', 'tiff',
  'html', 'htm', 'php', 'js', 'css', 'xml', 'json', 'txt', 'md',
  'woff', 'woff2', 'eot', 'ttf', 'otf'
];

const RECOGNIZED_DOWNLOAD_EXTS = [
  'exe', 'msi', 'zip', '7z', 'rar', 'tar', 'gz', 'tgz', 'bz2', 'xz',
  'iso', 'dmg', 'apk', 'deb', 'rpm', 'bin', 'appimage', 'pkg',
  'pdf', 'epub', 'mobi', 'djvu',
  'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'm4v',
  'mp3', 'flac', 'wav', 'ogg', 'm4a', 'aac', 'opus',
  'torrent'
];

function getFileExtension(url) {
  if (!url) return "";
  const clean = url.split('?')[0].split('#')[0];
  const parts = clean.split('/');
  const last = parts.pop() || "";
  const subParts = last.split('.');
  return subParts.length > 1 ? subParts.pop().toLowerCase() : "";
}

// --- LINK CLICK MONITORING SYSTEM ---
document.addEventListener('click', (event) => {
  const link = event.target.closest('a, area');
  if (!link || !link.href || (!link.href.startsWith('http://') && !link.href.startsWith('https://'))) return;

  // Allow native browser action when modifier keys (Ctrl/Shift/Meta/Alt) are held
  if (event.ctrlKey || event.shiftKey || event.metaKey || event.altKey) return;

  try {
    const extension = getFileExtension(link.href);
    const downloadAttr = link.getAttribute('download');

    // Never intercept web assets or regular web navigation links
    if (extension && IGNORED_EXTENSIONS.includes(extension) && !downloadAttr) {
      return;
    }

    // Query background service to check Bengal DM backend status & filtering rules
    chrome.runtime.sendMessage({
      action: "check_status",
      url: link.href,
      referrer: window.location.href
    }, (statusResponse) => {
      if (chrome.runtime.lastError || !statusResponse || !statusResponse.online) {
        return;
      }

      // If global interception is disabled or website/URL is blacklisted, leave to browser
      if (statusResponse.enableInterception === false || statusResponse.blacklisted) {
        return;
      }

      const isDownloadExt = extension && RECOGNIZED_DOWNLOAD_EXTS.includes(extension);
      const isExplicitWhitelistedExt = Boolean(statusResponse.whitelistedExt);

      // Only intercept if the link has a download attribute or recognized downloadable file extension
      if (!downloadAttr && !isDownloadExt && !isExplicitWhitelistedExt) {
        return;
      }

      // Bengal DM is active - intercept link click and notify browser DOM engine that download was taken over
      event.preventDefault();
      event.stopPropagation();
      if (event.stopImmediatePropagation) {
        event.stopImmediatePropagation();
      }

      chrome.runtime.sendMessage({
        action: "send_to_bengal",
        url: link.href,
        referrer: window.location.href
      }, (response) => {
        if (response && response.isHtmlLanding) {
          // HTML web page target: open normally in browser tab
          if (link.target && link.target !== '_self') {
            window.open(link.href, link.target);
          } else {
            window.location.href = link.href;
          }
        }
      });
    });
  } catch (e) {
    // Fallback on error
  }
}, true);

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
  fetchSniffedMedia();

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.action === "media_stream_detected" && msg.stream) {
      if (!sniffedMediaStreams.some(s => s.url === msg.stream.url)) {
        sniffedMediaStreams.unshift(msg.stream);
        if (sniffedMediaStreams.length > 30) sniffedMediaStreams.pop();
        if (activeVideo && isDropdownOpen) {
          populateDropdown();
        }
      }
    }
  });

  // Request fresh media info periodically
  function requestMediaInfo() {
    try {
      window.postMessage({ type: '__BDM_GET_MEDIA_INFO__' }, '*');
    } catch (e) {}
    fetchTabInfo();
    fetchSniffedMedia();
  }

  // 2. Create Shadow DOM Container on document.documentElement
  const host = document.createElement('bdm-video-dock');
  host.style.cssText = 'position: fixed; z-index: 2147483647; pointer-events: none; top: 0; left: 0;';
  const shadow = host.attachShadow({ mode: 'open' });

  function ensureAttached() {
    const targetParent = document.fullscreenElement || document.body || document.documentElement;
    if (targetParent && host.parentNode !== targetParent) {
      targetParent.appendChild(host);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureAttached);
  } else {
    ensureAttached();
  }
  document.addEventListener('fullscreenchange', ensureAttached);

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
      opacity: 1;
      transition: opacity 0.35s ease, transform 0.2s ease;
    }

    .bdm-root.visible {
      display: flex;
    }

    /* Barely visible / transparent after few seconds of inactivity */
    .bdm-root.idle {
      opacity: 0.22;
    }

    /* If hovered, active, open, or dragging, remove transparency completely */
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
      from { opacity: 0; transform: translateY(-4px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .bdm-root.open .bdm-dropdown {
      display: block;
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
      justify-content: space-between;
      padding: 6px 12px;
      background: #101317;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      font-size: 10.5px;
      color: #6b7280;
    }

    .bdm-feedback {
      padding: 10px 12px;
      font-size: 12px;
      color: #34d399;
      text-align: center;
      background: rgba(16, 185, 129, 0.1);
      display: none;
    }
  `;
  shadow.appendChild(style);

  // 4. Create DOM Structure
  const root = document.createElement('div');
  root.className = 'bdm-root';
  root.id = 'bdmRoot';

  const logoUrl = (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.getURL)
    ? chrome.runtime.getURL('assets/tray_monochrome_light.png')
    : '';

  const logoHtml = logoUrl
    ? `<img class="bdm-logo-img" src="${logoUrl}" alt="Bengal DM" draggable="false" />`
    : `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="2" y="2" width="20" height="20" rx="5" fill="#1e2229" stroke="#3daee9" stroke-width="1.5"/>
        <path d="M12 6V14M12 14L8.5 10.5M12 14L15.5 10.5" stroke="#3daee9" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M6 17H18" stroke="#f59e0b" stroke-width="2" stroke-linecap="round"/>
      </svg>`;

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
      <div class="bdm-feedback" id="bdmFeedback">Sending to Bengal DM...</div>
      <div class="bdm-list" id="bdmList"></div>
      <div class="bdm-footer">
        <span>Bengal Download Manager</span>
        <span>Port 9000</span>
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
  const feedbackEl = shadow.getElementById('bdmFeedback');

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

  // 6. Draggable / Movable Behavior
  let isPointerDown = false;
  let hasDragged = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let initialLeft = 0;
  let initialTop = 0;

  pill.addEventListener('pointerdown', (e) => {
    if (e.target.closest('#bdmCloseBtn')) return;

    clearIdleTimer();
    root.classList.add('dragging');

    isPointerDown = true;
    hasDragged = false;
    dragStartX = e.clientX;
    dragStartY = e.clientY;

    const rect = root.getBoundingClientRect();
    initialLeft = rect.left;
    initialTop = rect.top;

    try {
      pill.setPointerCapture(e.pointerId);
    } catch (err) {}
  });

  pill.addEventListener('pointermove', (e) => {
    if (!isPointerDown) return;
    const dx = e.clientX - dragStartX;
    const dy = e.clientY - dragStartY;

    if (!hasDragged && Math.hypot(dx, dy) > 4) {
      hasDragged = true;
      isUserPositioned = true;
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
    if (!isPointerDown) return;
    isPointerDown = false;
    root.classList.remove('dragging');
    try {
      pill.releasePointerCapture(e.pointerId);
    } catch (err) {}

    if (!hasDragged) {
      toggleDropdown();
    } else if (!isDropdownOpen) {
      resetIdleTimer();
    }
  });

  // 6. Cross Button in Corner (Hover-to-view dismissal)
  closeBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (activeVideo) {
      dismissedVideos.add(getVideoKey(activeVideo));
    }
    hideWidget();
  });

  function getVideoKey(video) {
    if (window.location.hostname.includes('youtube.com')) {
      const v = new URLSearchParams(window.location.search).get('v');
      if (v) return `yt_${v}`;
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
    if (dismissedVideos.has(getVideoKey(video))) {
      return false;
    }

    // Navigational link check: legitimate playable main media players are never wrapped inside <a> navigational tags
    const anchor = video.closest('a[href]');
    if (anchor) {
      const href = (anchor.getAttribute('href') || '').trim();
      if (href && !href.startsWith('#') && !href.startsWith('javascript:')) {
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
    if (video.matches) {
      for (const sel of previewClassesOrAttrs) {
        if (video.matches(sel)) return false;
      }
    }

    // Inline event handlers for thumbnail/hover video players (e.g. onplay="hvponplay(this)")
    const onplayAttr = (video.getAttribute('onplay') || '').toLowerCase();
    if (onplayAttr.includes('hvp') || onplayAttr.includes('preview') || onplayAttr.includes('thumb')) {
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
    if (video.loop && video.muted && !video.controls) {
      if (!video.duration || !isFinite(video.duration) || video.duration < 45) {
        const hasCustomPlayer = video.closest('.jwplayer, .video-js, .plyr, .dplayer, .artplayer, #movie_player, .html5-video-player');
        if (!hasCustomPlayer) {
          return false;
        }
      }
    }

    const rect = video.getBoundingClientRect();
    const isInIframe = window.self !== window.top;
    const minW = isInIframe ? 160 : 260;
    const minH = isInIframe ? 90 : 140;

    // Dimensions check
    if ((rect.width < minW || rect.height < minH) && (video.videoWidth < 240 || video.videoHeight < 140)) {
      return false;
    }

    // Viewport check (if in top window; inside iframe rect is relative to iframe viewport)
    if (rect.bottom <= 0 || rect.top >= window.innerHeight || rect.right <= 0 || rect.left >= window.innerWidth) {
      return false;
    }

    // Check display / visibility styles
    const style = window.getComputedStyle(video);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
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
    } else {
      const genericPreview = video.closest([
        'ytd-thumbnail',
        '#inline-preview-player',
        'ytd-video-preview',
        '.feed-video-preview',
        '.shorts-carousel',
        '.thumb-preview',
        '.post_vid_thumb',
        '.vid_container',
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

    return true;
  }

  // 8. Video Title & Duration Extraction
  function cleanTitleString(str) {
    if (!str || typeof str !== 'string') return "";
    let clean = str.trim();
    // Strip common leading noise
    clean = clean.replace(/^(Watch\s*[:-]?\s*|Streaming\s*[:-]?\s*|Play\s*[:-]?\s*)/i, '');
    // Strip trailing site brandings like "- Vidara", "| Vidara", "- YouTube", "- Vidara.so", " | 123movies", etc.
    clean = clean.replace(/\s*[-–—|]\s*([a-zA-Z0-9.-]+\.(com|org|net|so|to|is|io|me|tv|cc|cx)|Vidara|YouTube|Vimeo|Dailymotion|StreamTape|SuperStream|Flixtor|Fmovies|123movies|BiliBili|Twitch|SoundCloud|Facebook|Twitter|TikTok|Reddit)[^|\-–—]*$/i, '');
    clean = clean.replace(/\s*[-–—|]\s*Watch\s+.*$/i, '');
    clean = clean.replace(/\s*[-–—|]\s*Official\s+(Website|Site|Stream|Video).*$/i, '');
    return clean.trim();
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
    if (ytMediaInfo && ytMediaInfo.title) {
      const t = cleanTitleString(ytMediaInfo.title);
      if (t) return t;
    }
    const ytTitle = document.querySelector('h1.ytd-watch-metadata, #title h1, h1.title');
    if (ytTitle && ytTitle.innerText.trim()) {
      const t = cleanTitleString(ytTitle.innerText);
      if (t) return t;
    }
    if (cachedTabInfo && cachedTabInfo.title) {
      let t = cleanTitleString(cachedTabInfo.title);
      if (t && !t.toLowerCase().includes('embed') && t.toLowerCase() !== 'index') return t;
    }
    const metaTitle = document.querySelector('meta[property="og:title"], meta[name="twitter:title"]');
    if (metaTitle && metaTitle.content && metaTitle.content.trim()) {
      const t = cleanTitleString(metaTitle.content);
      if (t && !t.toLowerCase().includes('embed') && t.toLowerCase() !== 'index') return t;
    }
    if (video && video.title && video.title.trim()) {
      const t = cleanTitleString(video.title);
      if (t) return t;
    }
    if (document.title && document.title.trim()) {
      let dt = cleanTitleString(document.title);
      if (dt && !dt.toLowerCase().includes('embed') && dt.toLowerCase() !== 'index') {
        return dt;
      }
    }
    const slug = getSlugFromUrl(window.location.href) || ((cachedTabInfo && cachedTabInfo.url) ? getSlugFromUrl(cachedTabInfo.url) : "");
    if (slug) return slug;
    return "Video Stream";
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
    const duration = (ytMediaInfo && ytMediaInfo.duration) || video.duration || 0;

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

    // B. If an HLS (m3u8) or DASH stream was sniffed for this tab
    const masterStream = sniffedMediaStreams.find(s => s.url.includes('master.m3u8') || s.url.includes('master.mpd'));
    const m3u8Stream = masterStream || sniffedMediaStreams.find(s => s.url.includes('.m3u8') || s.url.includes('.mpd'));
    if (m3u8Stream) {
      const vh = video.videoHeight || 720;
      const resLabel = vh >= 1080 ? '1080p Full HD' : (vh >= 720 ? '720p HD' : (vh >= 480 ? '480p SD' : `${vh}p`));
      const resBadge = vh >= 1080 ? '1080p' : (vh >= 720 ? '720p' : (vh >= 480 ? '480p' : `${vh}p`));
      const resCls = vh >= 720 ? 'hd' : '';

      return [
        {
          quality: `${resBadge} (HLS Stream)`,
          badge: resBadge,
          label: `${resLabel} (HLS Stream)`,
          height: vh,
          bitrate: vh >= 1080 ? 5000 : 2500,
          cls: resCls,
          streamUrl: m3u8Stream.url,
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
          streamUrl: m3u8Stream.url,
          sizeBytes: estimateFileSizeBytes(duration, 192),
          size: estimateFileSize(duration, 192, true)
        }
      ];
    }

    // C. Standard Video Height Filtering (Generic sites or fallback)
    const vh = video.videoHeight || 720;
    const allTiers = [
      { quality: '2160p (4K)', badge: '4K', label: '4K Ultra HD', height: 2160, bitrate: 22000, cls: 'uhd' },
      { quality: '1440p (2K)', badge: '2K', label: '2K Quad HD', height: 1440, bitrate: 12000, cls: 'uhd' },
      { quality: '1080p', badge: '1080p', label: '1080p Full HD', height: 1080, bitrate: 5000, cls: 'hd' },
      { quality: '720p', badge: '720p', label: '720p HD', height: 720, bitrate: 2500, cls: 'hd' },
      { quality: '480p', badge: '480p', label: '480p SD', height: 480, bitrate: 1200, cls: '' },
      { quality: '360p', badge: '360p', label: '360p', height: 360, bitrate: 700, cls: '' }
    ];

    // Strictly filter out any resolution tier higher than the video's actual dimensions
    const filtered = allTiers
      .filter(t => t.height <= vh)
      .map(t => ({
        ...t,
        sizeBytes: estimateFileSizeBytes(duration, t.bitrate),
        size: estimateFileSize(duration, t.bitrate, false)
      }));

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

    const isYouTube = window.location.hostname.includes('youtube.com');
    badgeEl.textContent = isYouTube ? 'YouTube' : 'Media';

    const dur = (ytMediaInfo && ytMediaInfo.duration) || activeVideo.duration || 0;
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
    const title = getVideoTitle(activeVideo);
    let targetUrl = window.location.href;

    const isYouTube = window.location.hostname.includes('youtube.com');
    if (isYouTube) {
      targetUrl = window.location.href;
    } else {
      // 1. Direct stream URL attached to tier (e.g. master m3u8)
      if (tier.streamUrl && (tier.streamUrl.startsWith('http://') || tier.streamUrl.startsWith('https://'))) {
        targetUrl = tier.streamUrl;
      } else if (sniffedMediaStreams.length > 0) {
        // 2. Sniffed m3u8 or media stream from background (prefer master playlist)
        const masterStream = sniffedMediaStreams.find(s => s.url.includes('master.m3u8') || s.url.includes('master.mpd'));
        const m3u8 = masterStream || sniffedMediaStreams.find(s => s.url.includes('.m3u8') || s.url.includes('.mpd'));
        targetUrl = m3u8 ? m3u8.url : sniffedMediaStreams[0].url;
      } else if (activeVideo.currentSrc && (activeVideo.currentSrc.startsWith('http://') || activeVideo.currentSrc.startsWith('https://'))) {
        targetUrl = activeVideo.currentSrc;
      } else if (activeVideo.src && (activeVideo.src.startsWith('http://') || activeVideo.src.startsWith('https://'))) {
        targetUrl = activeVideo.src;
      } else if (cachedTabInfo && cachedTabInfo.url) {
        targetUrl = cachedTabInfo.url;
      }
    }

    feedbackEl.textContent = `Opening ${tier.quality} in Bengal DM...`;
    feedbackEl.style.display = 'block';

    chrome.runtime.sendMessage({
      action: "send_to_bengal",
      url: targetUrl,
      referrer: (cachedTabInfo && cachedTabInfo.url) || window.location.href,
      isMedia: true,
      title: title,
      filename: title,
      quality: tier.quality,
      sizeBytes: tier.sizeBytes || 0,
      sizeStr: tier.size || ""
    }, (response) => {
      setTimeout(() => {
        feedbackEl.style.display = 'none';
        closeDropdown();
      }, 1200);
    });
  }

  // 12. Widget Display & Positioning
  function updateWidgetPosition() {
    if (!activeVideo || !root.classList.contains('visible')) return;

    if (isUserPositioned) {
      root.style.left = `${userCoords.left}px`;
      root.style.top = `${userCoords.top}px`;
      root.style.right = 'auto';
      root.style.bottom = 'auto';
      return;
    }

    const rect = activeVideo.getBoundingClientRect();
    if (rect.bottom <= 0 || rect.top >= window.innerHeight) {
      root.style.display = 'none';
      return;
    } else {
      root.style.display = 'flex';
    }

    const pillW = pill.offsetWidth || 34;
    const pad = 16;
    let left = rect.right - pillW - pad;
    let top = rect.top + pad;

    left = Math.max(8, Math.min(window.innerWidth - pillW - 8, left));
    top = Math.max(8, Math.min(window.innerHeight - 40, top));

    root.style.left = `${left}px`;
    root.style.top = `${top}px`;
    root.style.right = 'auto';
    root.style.bottom = 'auto';
  }

  function showWidget() {
    ensureAttached();
    root.classList.add('visible');
    root.style.display = 'flex';
    updateWidgetPosition();
    resetIdleTimer();
  }

  function hideWidget() {
    clearIdleTimer();
    closeDropdown();
    root.classList.remove('visible');
    root.style.display = 'none';
  }

  function toggleDropdown() {
    if (isDropdownOpen) {
      closeDropdown();
    } else {
      openDropdown();
    }
  }

  function openDropdown() {
    isDropdownOpen = true;
    clearIdleTimer();
    root.classList.add('open');

    // Prevent dropdown clipping off left edge if dragged near left boundary
    const rect = root.getBoundingClientRect();
    if (rect.left < 320) {
      dropdown.style.right = 'auto';
      dropdown.style.left = '0';
    } else {
      dropdown.style.left = 'auto';
      dropdown.style.right = '0';
    }

    requestMediaInfo();
    populateDropdown();
  }

  function closeDropdown() {
    isDropdownOpen = false;
    root.classList.remove('open');
    feedbackEl.style.display = 'none';
    resetIdleTimer();
  }

  // Close dropdown on outside click
  document.addEventListener('click', (e) => {
    if (isDropdownOpen && !host.contains(e.target)) {
      closeDropdown();
    }
  });

  // 13. Video State Observation
  function onVideoState(video) {
    if (!video) return;

    const hasPlayed = playedVideos.has(video) || (activeVideo === video);
    if (!isValidPlayedVideo(video, hasPlayed)) {
      if (activeVideo === video) {
        hideWidget();
        activeVideo = null;
      }
      return;
    }

    if (!video.paused) {
      playedVideos.add(video);
    }

    if (activeVideo !== video) {
      activeVideo = video;
      requestMediaInfo();
    }
    showWidget();
  }

  document.addEventListener('play', (e) => {
    if (e.target instanceof HTMLVideoElement || e.target.tagName === 'VIDEO') {
      setTimeout(() => onVideoState(e.target), 200);
    }
  }, true);

  document.addEventListener('playing', (e) => {
    if (e.target instanceof HTMLVideoElement || e.target.tagName === 'VIDEO') {
      playedVideos.add(e.target);
      onVideoState(e.target);
    }
  }, true);

  document.addEventListener('timeupdate', (e) => {
    if (e.target instanceof HTMLVideoElement || e.target.tagName === 'VIDEO') {
      if (e.target.currentTime > 0.1) {
        playedVideos.add(e.target);
      }
      if (!activeVideo || activeVideo === e.target) {
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

  // Periodic active video scanner (crucial for custom iframe video players like JWPlayer/HLS.js on vidara.so)
  setInterval(() => {
    if (activeVideo) {
      if (!document.contains(activeVideo) || dismissedVideos.has(getVideoKey(activeVideo)) || !isValidPlayedVideo(activeVideo, true)) {
        hideWidget();
        activeVideo = null;
      } else {
        updateWidgetPosition();
      }
      return;
    }

    const videos = document.querySelectorAll('video');
    for (const v of videos) {
      if (!v.paused || playedVideos.has(v)) {
        if (isValidPlayedVideo(v, playedVideos.has(v))) {
          onVideoState(v);
          break;
        }
      }
    }
  }, 1000);

  window.addEventListener('scroll', updateWidgetPosition, { passive: true });
  window.addEventListener('resize', updateWidgetPosition, { passive: true });
})();
