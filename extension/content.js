document.addEventListener('click', (event) => {
    // 1. Find the closest <a> link tag that the user clicked
    const link = event.target.closest('a');

    if (link && link.href && link.href.startsWith('http')) {

        // 2. Define the file types you want to intercept silently
        const interceptTypes = /\.(zip|rar|7z|tar|gz|iso|exe|msi|mp4|mkv|avi|mp3|flac|pdf)(\?.*)?$/i;

        // 3. If the link matches a download file type
        if (link.href.match(interceptTypes)) {

            // CRITICAL: Block Firefox from seeing the click or navigating
            event.preventDefault();
            event.stopPropagation();

            // Send the URL directly to our background.js script
            chrome.runtime.sendMessage({
                action: "silent_download",
                url: link.href
            });
        }
    }
}, true); // 'true' uses the capture phase to intercept before the website's own code can react