# Spec & Plan: Refactoring TCP Listener for Robust HTTP Handling

The current `TcpListenerThread` in `src/main.py` uses a raw socket with a single `conn.recv(4096)` call. This is fragile because it assumes the entire HTTP headers and body (including potentially large cookies and JSON payload) will arrive in a single 4KB packet. If the request is larger or fragmented, the JSON body is truncated, causing the download to fail with an error.

## Proposed Architecture

We will replace the raw socket implementation with Python's built-in `http.server.HTTPServer` and `BaseHTTPRequestHandler`. This standard library automatically handles:
- Reading all headers completely.
- Parsing `Content-Length`.
- Reading the exact body size, regardless of TCP packet fragmentation.

## Implementation Steps

### Task 1: Refactor TcpListenerThread in `src/main.py`

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Import required modules**

Add `from http.server import HTTPServer, BaseHTTPRequestHandler` at the top of the file (or inside the class).

- [ ] **Step 2: Create the HTTP Request Handler**

Define a handler class that processes OPTIONS, GET, and POST requests exactly as the old raw socket did, but using proper HTTP server methods.

```python
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class IPCRequestHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        ext_data = load_extension_config()
        config_json = json.dumps({
            "status": "Bengal DM is running",
            "aria2": {
                "port": ext_data.get("port", 56800),
                "token": ext_data.get("token", "")
            }
        })
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(config_json.encode('utf-8'))

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
        url = ""
        user_agent = ""
        cookies = ""
        
        try:
            payload = json.loads(body)
            url = payload.get("url", "")
            user_agent = payload.get("userAgent", "")
            cookies = payload.get("cookies", "")
        except json.JSONDecodeError:
            url = body
            
        if url and url.startswith("http"):
            # self.server.emitter is passed when initializing the server
            self.server.emitter.new_download_signal.emit(f"{url}|{user_agent}|{cookies}")
            
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
        else:
            self.send_response(400)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
    def log_message(self, format, *args):
        pass # Suppress default logging to stderr
```

- [ ] **Step 3: Update TcpListenerThread to use HTTPServer**

Replace the raw socket loop with `HTTPServer.serve_forever()`.

```python
class TcpListenerThread(QThread):
    def __init__(self, port, emitter, parent=None):
        super().__init__(parent)
        self.port = port
        self.emitter = emitter
        self.server = None

    def run(self):
        try:
            self.server = HTTPServer(('127.0.0.1', self.port), IPCRequestHandler)
            # Attach emitter to server so handler can access it
            self.server.emitter = self.emitter 
            self.server.serve_forever()
        except Exception as e:
            pass

    def stop(self):
        if self.server:
            # shutdown() must be called from another thread
            threading.Thread(target=self.server.shutdown, daemon=True).start()
```

- [ ] **Step 4: Commit changes**

```bash
git add src/main.py
git commit -m "fix: refactor IPC listener to use HTTPServer for robust payload handling"
```