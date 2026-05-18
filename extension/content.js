document.addEventListener('click', (event) => {
    const link = event.target.closest('a');
    if (!link || !link.href || !link.href.startsWith('http')) return;
    
    // 1. Skip if modifier keys are pressed (let browser handle new tabs/windows natively)
    if (event.ctrlKey || event.shiftKey || event.metaKey || event.altKey) return;

    // 2. heuristic: skip pre-flight for obvious web pages
    const url = new URL(link.href);
    const pathname = url.pathname.toLowerCase();
    const isWebPage = pathname.endsWith('/') || 
                      pathname.split('/').pop() === '' ||
                      pathname.match(/\.(html|php|asp|aspx|jsp|htm)$/i) ||
                      (!pathname.includes('.') && !pathname.endsWith('/'));

    if (isWebPage) return;

    // 3. Block navigation for potential downloads
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
        
        // Resume navigation if Bengal didn't take it
        if (link.target === '_blank') {
            window.open(link.href, '_blank');
        } else {
            window.location.href = link.href;
        }
    });
}, true);
