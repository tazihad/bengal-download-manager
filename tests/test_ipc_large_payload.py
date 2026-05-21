import os
import sys
import socket
import json
import threading
import time
import pytest
from unittest.mock import MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from main import TcpListenerThread

def test_large_payload_parsing():
    """Verify that the IPC listener correctly parses large payloads (e.g. with many cookies)."""
    port = 9876
    emitter = MagicMock()
    
    # Initialize the thread
    thread = TcpListenerThread(port, emitter)
    
    # Start the server in a background thread
    server_thread = threading.Thread(target=thread.run, daemon=True)
    server_thread.start()
    
    # Give it a moment to start
    time.sleep(0.5)
    
    try:
        url = "http://example.com/file.zip"
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        # 8KB of cookies to definitely exceed the old 4KB limit
        cookies = "c" * 8192
        payload = json.dumps({"url": url, "userAgent": ua, "cookies": cookies})
        
        # Manually send HTTP POST
        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as s:
            request = (
                f"POST / HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{port}\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(payload)}\r\n"
                f"\r\n"
                f"{payload}"
            )
            s.sendall(request.encode('utf-8'))
            
            # Read response
            response = s.recv(1024).decode('utf-8')
            assert "200 OK" in response

        # Verify that the signal was emitted with the FULL data
        expected_signal = f"{url}|{ua}|{cookies}"
        emitter.new_download_signal.emit.assert_called_once_with(expected_signal)
        
    finally:
        # Shutdown the server
        thread.stop()
        time.sleep(0.2)
