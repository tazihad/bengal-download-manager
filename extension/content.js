document.addEventListener('click', (event) => {
    const link = event.target.closest('a');
    if (!link || !link.href || !link.href.startsWith('http')) return;
    
    // 1. Skip if modifier keys are pressed (let browser handle new tabs/windows natively)
    if (event.ctrlKey || event.shiftKey || event.metaKey || event.altKey) return;

    // 2. heuristic: intercept everything with an extension UNLESS it's a web asset or image
    const ignoredExts = [
        'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif', 'tif', 'tiff',
        'html', 'htm', 'php', 'js', 'css', 'xml', 'json', 'txt', 'md',
        'woff', 'woff2', 'eot', 'ttf', 'otf'
    ];

    const url = new URL(link.href);
    const pathname = url.pathname.toLowerCase();
    const parts = pathname.split('?')[0].split('#')[0].split('.');
    const extension = parts.length > 1 ? parts.pop() : "";

    // Intercept if it HAS an extension and that extension is NOT ignored
    if (!extension || ignoredExts.includes(extension)) return;

    // 3. Block navigation for verified potential downloads
    event.preventDefault();
    event.stopPropagation();

    const originalCursor = link.style.cursor;
    link.style.cursor = 'wait';

    chrome.runtime.sendMessage({
        action: "check_link_preflight",
        url: link.href
    }, (response) => {
        link.style.cursor = originalCursor;
        
        if (response && response.handledByBengal) {
            return;
        }
        
        // Resume navigation if Bengal didn't take it (failsafe)
        if (link.target === '_blank') {
            window.open(link.href, '_blank');
        } else {
            window.location.href = link.href;
        }
    });
}, true);
