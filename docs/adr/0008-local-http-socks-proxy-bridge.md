# 0008 Local HTTP-to-SOCKS Proxy Adapter for Aria2

Status: accepted

## Context
Aria2 does not provide native client support for SOCKS4, SOCKS4a, SOCKS5, or SOCKS5h proxies ([aria2 issue #153](https://github.com/aria2/aria2/issues/153)). Specifying `aria2c --all-proxy=socks5://host:port` fails because Aria2 only implements an HTTP/HTTPS proxy client protocol.

Previous versions of Bengal Download Manager only exposed HTTP and HTTPS options in the Options dialog. Users routing traffic through local Tor instances (`socks5://127.0.0.1:9050`), SSH dynamic tunnels, or corporate SOCKS proxies could not accelerate downloads with Aria2.

## Decision
We implement a local **HTTP-to-SOCKS Proxy Adapter** (`SocksHttpBridge` and `SocksBridgeRunner`) in `src/core/services/socks_bridge.py`:
- **Deep Module Design**: `Aria2DaemonManager` supervises the `SocksBridgeRunner` lifecycle. Calling `start()` or `update_proxy()` automatically binds the bridge on an unprivileged loopback address (`127.0.0.1:0`) and injects `--all-proxy=http://127.0.0.1:<bridge_port>` into Aria2.
- **Protocol Translation**:
  - Translates incoming `CONNECT host:port HTTP/1.1` into upstream SOCKS connections via `python-socks[asyncio]`, returning `200 Connection Established` and bi-directionally piping raw bytes.
  - Rewrites incoming absolute HTTP `GET/POST` proxy requests to relative paths and relays responses.
  - Returns standard HTTP error codes (`502 Bad Gateway` on SOCKS connection errors, `504 Gateway Timeout` on timeout, `400 Bad Request` on malformed/oversized headers).
- **Security & Reliability**:
  - Strictly binds to `127.0.0.1` (never `0.0.0.0`) on an ephemeral OS-assigned port to avoid port collisions and eliminate external exposure.
  - Enforces a 64 KB header size limit and 15-second connect timeout.
  - Uses `threading.Event` to eliminate busy-waiting during thread startup.
  - Cleanly cancels all active client tasks and closes all sockets upon termination.
- **UI Integration**:
  - Adds `SOCKS5` and `SOCKS4` options to the Options dialog "Proxy / Socks" tab.
  - Dynamically updates the active Aria2 daemon via JSON-RPC `aria2.changeGlobalOption`.

## Consequences
- Aria2 can download through SOCKS4, SOCKS4a, SOCKS5, and SOCKS5h proxies seamlessly across Linux AppImage, Flatpak, Snap, and standalone binaries without root permissions or external system daemons.
- Presentation layers (`options.py`, `MainWindow`) remain decoupled from socket handshakes, asyncio event loops, and proxy protocol details.
- Standard test suites run headlessly with mock SOCKS endpoints without requiring external network access.
