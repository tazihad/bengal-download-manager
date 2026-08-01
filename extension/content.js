const IGNORED_EXTENSIONS = [
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif', 'tif', 'tiff',
    'html', 'htm', 'php', 'js', 'css', 'xml', 'json', 'txt', 'md',
    'woff', 'woff2', 'eot', 'ttf', 'otf'
];

document.addEventListener('click', (event) => {
    const link = event.target.closest('a');
    if (!link || !link.href || (!link.href.startsWith('http://') && !link.href.startsWith('https://'))) return;

    // Skip if modifier keys are pressed (let browser handle new tabs/windows natively)
    if (event.ctrlKey || event.shiftKey || event.metaKey || event.altKey) return;

    try {
        const url = new URL(link.href);
        const pathname = url.pathname.toLowerCase();
        const parts = pathname.split('?')[0].split('#')[0].split('.');
        const extension = parts.length > 1 ? parts.pop() : "";

        // Only intercept if link points to a file with an extension that is NOT ignored
        if (!extension || IGNORED_EXTENSIONS.includes(extension)) return;

        const downloadAttr = link.getAttribute('download');
        if (!downloadAttr && !extension) return;

        // Check if background service worker can handle this download via Bengal DM
        chrome.runtime.sendMessage({ action: "check_status" }, (statusResponse) => {
            if (chrome.runtime.lastError || !statusResponse || !statusResponse.online) {
                // Bengal DM is not running, let default browser download happen
                return;
            }

            // Bengal DM is active - route download to Bengal DM
            event.preventDefault();
            event.stopPropagation();

            chrome.runtime.sendMessage({
                action: "send_to_bengal",
                url: link.href
            });
        });
    } catch (e) {
        // Fallback on error
    }
}, true);

