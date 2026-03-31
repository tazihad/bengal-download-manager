chrome.downloads.onCreated.addListener((downloadItem) => {
  if (downloadItem.url.startsWith("http")) {

    // 1. Cancel the browser download
    chrome.downloads.cancel(downloadItem.id, () => {

      // 2. Send to aria2 using HTTP POST
      chrome.storage.local.get({ host: "localhost", port: 50001 }, (items) => {
        const url = `http://${items.host}:${items.port}/jsonrpc`;

        const payload = {
          jsonrpc: "2.0",
          id: "bengal-dm-add",
          method: "aria2.addUri",
          params: [[downloadItem.url]]
        };

        fetch(url, {
          method: 'POST',
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(payload)
        })
          .then(response => {
            if (!response.ok) throw new Error("Network response was not ok");
            console.log("Sent to Bengal DM successfully");
          })
          .catch(err => console.error("Bengal DM Connection failed:", err));
      });
    });
  }
});