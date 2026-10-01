// Lightweight content script to monitor system light/dark mode and notify background service worker in Chrome
(function initThemeToggle() {
  function checkTheme() {
    if (!window.matchMedia) return;
    try {
      const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      const scheme = isDark ? 'dark' : 'light';
      chrome.runtime.sendMessage({
        scheme: scheme,
        action: "report_system_theme",
        systemTheme: scheme
      }).catch(() => {});
    } catch {}
  }

  if (window.matchMedia) {
    try {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      if (mq.addEventListener) {
        mq.addEventListener('change', checkTheme);
      } else if (mq.addListener) {
        mq.addListener(checkTheme);
      }
      checkTheme();
    } catch {}
  }
})();
