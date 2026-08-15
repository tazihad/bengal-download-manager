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
    chrome.runtime.sendMessage({ action: "check_status", url: link.href }, (statusResponse) => {
      if (chrome.runtime.lastError || !statusResponse || !statusResponse.online) {
        return;
      }

      // If blacklisted, leave to browser
      if (statusResponse.blacklisted) {
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
        url: link.href
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
