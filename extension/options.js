const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 9000;

// Saves options to chrome.storage.local
function save_options() {
  const host = document.getElementById('host').value.trim();
  const port = parseInt(document.getElementById('port').value, 10);

  if (!host || isNaN(port) || port < 1 || port > 65535) {
    const status = document.getElementById('status');
    status.textContent = 'Error: Invalid Host or Port.';
    status.style.color = 'red';
    setTimeout(function() {
      status.textContent = '';
    }, 2000);
    return;
  }
  
  chrome.storage.local.set({
    host: host,
    port: port
  }, function() {
    const status = document.getElementById('status');
    status.textContent = 'Settings saved.';
    status.style.color = 'green';
    setTimeout(function() {
      status.textContent = '';
    }, 750);
  });
}

// Restores input fields using the preferences stored in chrome.storage.local.
function restore_options() {
  chrome.storage.local.get({
    host: DEFAULT_HOST,
    port: DEFAULT_PORT
  }, function(items) {
    document.getElementById('host').value = items.host;
    document.getElementById('port').value = items.port;
  });
}

document.addEventListener('DOMContentLoaded', restore_options);
document.getElementById('save').addEventListener('click', save_options);