// Runs inside a hidden offscreen document (reason: MATCH_MEDIA). It only watches the
// system color scheme and tells the background service worker whenever it changes.
(function () {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  function report() {
    try {
      chrome.runtime.sendMessage({
        action: 'system_theme_report',
        effectiveTheme: mq.matches ? 'dark' : 'light'
      }).catch(() => {});
    } catch (e) {}
  }
  report();
  if (mq.addEventListener) mq.addEventListener('change', report);
  else if (mq.addListener) mq.addListener(report);
})();
