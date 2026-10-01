// Offscreen document to monitor OS and browser dark mode changes for Chromium MV3 service workers
(function initThemeWatcher() {
  if (typeof window === 'undefined' || !window.matchMedia) return;

  const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');

  function reportTheme(isDark) {
    const mode = isDark ? 'dark' : 'light';
    try {
      chrome.storage.local.set({ systemTheme: mode });
    } catch {}
    try {
      chrome.runtime.sendMessage({
        action: 'changeTheme',
        isDark: Boolean(isDark),
        systemTheme: mode
      }).catch(() => {});
    } catch {}
  }

  // Initial sync immediately upon creation
  reportTheme(darkModeQuery.matches);

  // Live listener for immediate system theme changes
  if (darkModeQuery.addEventListener) {
    darkModeQuery.addEventListener('change', (e) => reportTheme(e.matches));
  } else if (darkModeQuery.addListener) {
    darkModeQuery.addListener((e) => reportTheme(e.matches));
  }
})();
