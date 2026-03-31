function applyTheme(theme) {
    if (theme === 'system') {
        const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    } else {
        document.documentElement.setAttribute('data-theme', theme);
    }
}

document.getElementById('options-link').addEventListener('click', (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
});

chrome.storage.local.get({ theme: "system" }, async (items) => {
    applyTheme(items.theme);

    const statusText = document.getElementById('status-text');
    const dot = document.getElementById('dot');

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 1500);

        // Ping the Python app on port 9000
        const response = await fetch("http://127.0.0.1:9000/", {
            method: 'GET',
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (response.ok) {
            dot.className = "dot online";
            statusText.textContent = "Bengal DM Running";
        } else {
            throw new Error("Invalid Response");
        }
    } catch (error) {
        dot.className = "dot offline";
        statusText.textContent = "App Not Running";
    }
});