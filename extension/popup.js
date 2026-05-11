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

async function checkAria2(port, token) {
    const url = `http://localhost:${port}/jsonrpc`;
    const params = token ? [`token:${token}`] : [];
    const payload = { jsonrpc: "2.0", id: "popup-check", method: "aria2.getVersion", params: params };

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 1000);
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        const data = await response.json();
        return !!(data.result && data.result.version);
    } catch (e) {
        return false;
    }
}

chrome.storage.local.get({ theme: "system", port: 56800, token: "" }, async (items) => {
    applyTheme(items.theme);

    const statusText = document.getElementById('status-text');
    const dot = document.getElementById('dot');

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 1500);

        // 1. Ping the Python app on port 9000
        const response = await fetch("http://127.0.0.1:9000/", {
            method: 'GET',
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (response.ok) {
            // 2. Ping Aria2 to ensure sync
            const ariaOnline = await checkAria2(items.port, items.token);
            if (ariaOnline) {
                dot.className = "dot online";
                statusText.textContent = "Bengal DM Running";
            } else {
                dot.className = "dot offline";
                statusText.textContent = "Ports Out of Sync";
            }
        } else {
            throw new Error("Invalid Response");
        }
    } catch (error) {
        dot.className = "dot offline";
        statusText.textContent = "App Not Running";
    }
});
