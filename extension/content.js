document.addEventListener('click', (event) => {
    // 1. Find the closest <a> link tag that the user clicked
    const link = event.target.closest('a');

    if (link && link.href && link.href.startsWith('http')) {
        // CRITICAL: Block the browser from navigating immediately
        event.preventDefault();
        event.stopPropagation();

        const isNewTab = link.target === '_blank';
        
        // Show a visual cue (optional, depending on preference)
        document.body.style.cursor = 'wait';

        // Send the URL directly to our background.js script for pre-flight check
        chrome.runtime.sendMessage({
            action: "check_link_preflight",
            url: link.href
        }, (response) => {
            document.body.style.cursor = 'default';
            
            // If background says Bengal handled it, we do nothing (navigation remains blocked)
            if (response && response.handledByBengal) {
                return;
            }
            
            // If Bengal didn't handle it, we resume navigation
            if (isNewTab) {
                window.open(link.href, '_blank');
            } else {
                window.location.href = link.href;
            }
        });
    }
}, true); // 'true' uses the capture phase to intercept before the website's own code can react
