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

chrome.storage.local.get({ host: "localhost", port: 50001, theme: "system" }, async (items) => {
    applyTheme(items.theme);

    const statusText = document.getElementById('status-text');
    const dot = document.getElementById('dot');

    try {
        const url = `http://${items.host}:${items.port}/jsonrpc`;
        const payload = { jsonrpc: "2.0", id: "status-check", method: "aria2.getVersion" };

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);

        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (response.ok) {
            const data = await response.json();
            if (data.result && data.result.version) {
                dot.className = "dot online";
                statusText.textContent = "Connected";
                return;
            }
        }
        throw new Error("Invalid Response");
    } catch (error) {
        dot.className = "dot offline";
        statusText.textContent = error.name === 'AbortError' ? "Timeout" : "Disconnected";
    }
});