// Offscreen document to monitor OS and browser dark mode changes for Chromium MV3 service workers
(function initThemeWatcher() {
  if (typeof window === 'undefined' || !window.matchMedia) return;

  const mq = window.matchMedia('(prefers-color-scheme: dark)');

  function reportTheme(isDark) {
    const mode = isDark ? 'dark' : 'light';
    try {
      chrome.storage.local.set({ systemTheme: mode });
    } catch {}
    try {
      chrome.runtime.sendMessage({
        action: 'report_system_theme',
        systemTheme: mode
      }).catch(() => {});
    } catch {}
  }

  // Initial sync immediately upon creation
  reportTheme(mq.matches);

  // Live listener for immediate system theme changes
  if (mq.addEventListener) {
    mq.addEventListener('change', (e) => reportTheme(e.matches));
  } else if (mq.addListener) {
    mq.addListener((e) => reportTheme(e.matches));
  }
})();
