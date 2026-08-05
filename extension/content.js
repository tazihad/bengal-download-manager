const IGNORED_EXTENSIONS = [
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif', 'tif', 'tiff',
    'html', 'htm', 'php', 'js', 'css', 'xml', 'json', 'txt', 'md',
    'woff', 'woff2', 'eot', 'ttf', 'otf'
];

// --- LINK CLICK MONITORING SYSTEM ---
document.addEventListener('click', (event) => {
    const link = event.target.closest('a, area');
    if (!link || !link.href || (!link.href.startsWith('http://') && !link.href.startsWith('https://'))) return;

    // Allow native browser action when modifier keys (Ctrl/Shift/Meta/Alt) are held
    if (event.ctrlKey || event.shiftKey || event.metaKey || event.altKey) return;

    try {
        const url = new URL(link.href);
        const pathname = url.pathname.toLowerCase();
        const parts = pathname.split('?')[0].split('#')[0].split('.');
        const extension = parts.length > 1 ? parts.pop() : "";

        const downloadAttr = link.getAttribute('download');
        if (!downloadAttr && (!extension || IGNORED_EXTENSIONS.includes(extension))) return;

        // Query background service to check Bengal DM backend status
        chrome.runtime.sendMessage({ action: "check_status" }, (statusResponse) => {
            if (chrome.runtime.lastError || !statusResponse || !statusResponse.online) {
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
