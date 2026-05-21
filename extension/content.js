document.addEventListener('click', (event) => {
    const link = event.target.closest('a');
    if (!link || !link.href || !link.href.startsWith('http')) return;
    
    // 1. Skip if modifier keys are pressed (let browser handle new tabs/windows natively)
    if (event.ctrlKey || event.shiftKey || event.metaKey || event.altKey) return;

    // 2. heuristic: only intercept if it matches our target extension list
    const targetExts = [
        '3gp', '7z', 'aac', 'ace', 'aif', 'arj', 'asf', 'avi', 'bin', 'bz2', 'exe', 'gz', 'gzip', 
        'img', 'iso', 'lzh', 'm4a', 'm4v', 'mkv', 'mov', 'mp3', 'mp4', 'mpa', 'mpe', 'mpeg', 'mpg', 
        'msi', 'msu', 'ogg', 'ogv', 'pdf', 'plj', 'pps', 'ppt', 'rar', 'rmvb', 'sea', 'sit', 'sitx', 
        'tar', 'tif', 'tiff', 'wav', 'wma', 'wmv', 'zip', 'deb', 'rpm', 'appimage',
        'xz', 'bz', 'lzma', 'war', 'ear',
        'doc', 'docx', 'xls', 'xlsx', 'pptx', 'odt', 'ods', 'odp', 'rtf', 'csv', 'ppsx', 'dot'
    ];

    const url = new URL(link.href);
    const pathname = url.pathname.toLowerCase();
    const parts = pathname.split('?')[0].split('#')[0].split('.');
    const extension = parts.length > 1 ? parts.pop() : "";

    if (!targetExts.includes(extension)) return;

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
