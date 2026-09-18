"""
Local HTTP-to-SOCKS Proxy Adapter for Bengal Download Manager.
Enables Aria2 (and other HTTP proxy clients) to route traffic through SOCKS4/SOCKS5 proxies
by serving as an unprivileged, loopback-only HTTP proxy adapter.
"""

import asyncio
import logging
import socket
import threading
from typing import Optional, Set, Tuple
from urllib.parse import urlsplit

from python_socks.async_.asyncio import Proxy
from python_socks import ProxyError, ProxyConnectionError, ProxyTimeoutError

logger = logging.getLogger("bengal.socks_bridge")

MAX_HEADER_SIZE = 65536  # 64 KB request header limit
DEFAULT_TIMEOUT = 15.0   # 15 seconds upstream connect timeout


def parse_host_port(netloc: str, default_port: int = 80) -> Tuple[str, int]:
    """
    Parses host and port from a network location string, supporting IPv6 addresses.
    Examples:
      'example.com:8080' -> ('example.com', 8080)
      'example.com' -> ('example.com', 80)
      '[::1]:8443' -> ('::1', 8443)
      '[::1]' -> ('::1', 80)
    """
    netloc = netloc.strip()
    if netloc.startswith("["):
        end_bracket = netloc.find("]")
        if end_bracket != -1:
            host = netloc[1:end_bracket]
            rest = netloc[end_bracket + 1:]
            if rest.startswith(":"):
                try:
                    return host, int(rest[1:])
                except ValueError:
                    pass
            return host, default_port

    if ":" in netloc:
        parts = netloc.rsplit(":", 1)
        try:
            return parts[0], int(parts[1])
        except ValueError:
            return parts[0], default_port

    return netloc, default_port


class SocksHttpBridge:
    """
    Asynchronous local HTTP proxy server that forwards incoming HTTP and HTTPS
    CONNECT requests through an upstream SOCKS4/SOCKS5 proxy.
    """

    def __init__(
        self,
        proxy_url: str,
        host: str = "127.0.0.1",
        port: int = 0,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.proxy_url = proxy_url
        self.host = host
        self.port = port
        self.timeout = timeout
        self.server: Optional[asyncio.Server] = None
        self.actual_port: int = 0
        self._active_tasks: Set[asyncio.Task] = set()
        self._stopping: bool = False

    @staticmethod
    def _mask_proxy_url(url: str) -> str:
        try:
            split = urlsplit(url)
            if split.password:
                masked_netloc = split.netloc.replace(f":{split.password}@", ":****@")
                return split._replace(netloc=masked_netloc).geturl()
        except Exception:
            pass
        return url

    async def start(self) -> Tuple[str, int]:
        """Binds and starts listening for local HTTP proxy requests."""
        self._stopping = False
        self.server = await asyncio.start_server(
            self._handle_client,
            host=self.host,
            port=self.port,
        )
        sockets = self.server.sockets or []
        if sockets:
            self.actual_port = sockets[0].getsockname()[1]
        else:
            self.actual_port = self.port

        logger.info(
            "[SocksBridge] Listening on %s:%d -> Upstream: %s",
            self.host,
            self.actual_port,
            self._mask_proxy_url(self.proxy_url),
        )
        return self.host, self.actual_port

    async def stop(self) -> None:
        """Closes listener and aborts all active client sessions."""
        self._stopping = True
        if self.server:
            self.server.close()
            try:
                await self.server.wait_closed()
            except Exception:
                pass
            self.server = None

        # Cancel any ongoing client tasks
        tasks_to_cancel = [t for t in self._active_tasks if not t.done()]
        for task in tasks_to_cancel:
            task.cancel()

        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        self._active_tasks.clear()
        logger.info("[SocksBridge] Stopped successfully.")

    async def _handle_client(
        self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        if task:
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)

        try:
            # Read until double CRLF with header size limit guard
            header_bytes = bytearray()
            while b"\r\n\r\n" not in header_bytes and not self._stopping:
                chunk = await client_reader.read(4096)
                if not chunk:
                    break
                header_bytes.extend(chunk)
                if len(header_bytes) > MAX_HEADER_SIZE:
                    await self._send_error(
                        client_writer, 400, "Bad Request", "Header limit exceeded"
                    )
                    return

            if not header_bytes:
                return

            delim_idx = header_bytes.find(b"\r\n\r\n")
            if delim_idx == -1:
                return

            header_part = bytes(header_bytes[:delim_idx])
            rest = bytes(header_bytes[delim_idx + 4 :])

            lines = header_part.split(b"\r\n")
            if not lines or not lines[0]:
                await self._send_error(client_writer, 400, "Bad Request", "Empty request")
                return

            request_line = lines[0].decode("latin-1", errors="replace")
            parts = request_line.strip().split()
            if len(parts) < 2:
                await self._send_error(
                    client_writer, 400, "Bad Request", "Malformed request line"
                )
                return

            method = parts[0].upper()
            target = parts[1]
            http_version = parts[2] if len(parts) > 2 else "HTTP/1.1"

            if method == "CONNECT":
                await self._handle_connect(client_reader, client_writer, target, rest)
            else:
                await self._handle_http(
                    client_reader,
                    client_writer,
                    method,
                    target,
                    http_version,
                    lines[1:],
                    rest,
                )

        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            logger.debug("[SocksBridge] Error handling client: %s", e)
        finally:
            try:
                client_writer.close()
                await client_writer.wait_closed()
            except Exception:
                pass

    async def _handle_connect(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        target: str,
        initial_data: bytes,
    ) -> None:
        dest_host, dest_port = parse_host_port(target, default_port=443)
        remote_reader, remote_writer = await self._connect_upstream(
            client_writer, dest_host, dest_port
        )
        if not remote_writer or not remote_reader:
            return

        try:
            client_writer.write(
                b"HTTP/1.1 200 Connection Established\r\n"
                b"Proxy-Agent: Bengal-SocksBridge/1.0\r\n\r\n"
            )
            await client_writer.drain()

            if initial_data:
                remote_writer.write(initial_data)
                await remote_writer.drain()

            await self._relay(client_reader, client_writer, remote_reader, remote_writer)
        finally:
            try:
                remote_writer.close()
                await remote_writer.wait_closed()
            except Exception:
                pass

    async def _handle_http(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        method: str,
        target: str,
        http_version: str,
        header_lines: list[bytes],
        rest: bytes,
    ) -> None:
        if target.startswith("http://") or target.startswith("https://"):
            split_url = urlsplit(target)
            dest_host, dest_port = parse_host_port(split_url.netloc, default_port=80)
            path_query = split_url.path or "/"
            if split_url.query:
                path_query += f"?{split_url.query}"
        else:
            path_query = target
            host_header = ""
            for h in header_lines:
                if h.lower().startswith(b"host:"):
                    host_header = h.split(b":", 1)[1].decode("latin-1").strip()
                    break
            if not host_header:
                await self._send_error(client_writer, 400, "Bad Request", "Missing Host header")
                return
            dest_host, dest_port = parse_host_port(host_header, default_port=80)

        remote_reader, remote_writer = await self._connect_upstream(
            client_writer, dest_host, dest_port
        )
        if not remote_writer or not remote_reader:
            return

        try:
            req_bytes = bytearray(f"{method} {path_query} {http_version}\r\n".encode("latin-1"))
            has_host = False
            for line in header_lines:
                lower = line.lower()
                # Strip proxy hop-by-hop headers
                if lower.startswith(b"proxy-connection:") or lower.startswith(b"proxy-authorization:"):
                    continue
                if lower.startswith(b"host:"):
                    has_host = True
                req_bytes.extend(line + b"\r\n")

            if not has_host:
                req_bytes.extend(f"Host: {dest_host}\r\n".encode("latin-1"))
            req_bytes.extend(b"\r\n")

            if rest:
                req_bytes.extend(rest)

            remote_writer.write(req_bytes)
            await remote_writer.drain()

            await self._relay(client_reader, client_writer, remote_reader, remote_writer)
        finally:
            try:
                remote_writer.close()
                await remote_writer.wait_closed()
            except Exception:
                pass

    async def _connect_upstream(
        self, client_writer: asyncio.StreamWriter, dest_host: str, dest_port: int
    ) -> Tuple[Optional[asyncio.StreamReader], Optional[asyncio.StreamWriter]]:
        try:
            proxy = Proxy.from_url(self.proxy_url)
            sock = await proxy.connect(dest_host, dest_port, timeout=self.timeout)
            remote_reader, remote_writer = await asyncio.open_connection(sock=sock)
            return remote_reader, remote_writer
        except ProxyTimeoutError as e:
            logger.warning("[SocksBridge] Timeout connecting to %s:%d: %s", dest_host, dest_port, e)
            await self._send_error(
                client_writer,
                504,
                "Gateway Timeout",
                f"SOCKS proxy timed out connecting to {dest_host}:{dest_port}",
            )
            return None, None
        except (ProxyConnectionError, ProxyError, OSError) as e:
            logger.warning("[SocksBridge] SOCKS failure to %s:%d: %s", dest_host, dest_port, e)
            await self._send_error(
                client_writer,
                502,
                "Bad Gateway",
                f"SOCKS proxy connection failed to {dest_host}:{dest_port}: {e}",
            )
            return None, None
        except Exception as e:
            logger.error("[SocksBridge] Unexpected error to %s:%d: %s", dest_host, dest_port, e)
            await self._send_error(client_writer, 500, "Internal Server Error", str(e))
            return None, None

    async def _relay(
        self,
        r1: asyncio.StreamReader,
        w1: asyncio.StreamWriter,
        r2: asyncio.StreamReader,
        w2: asyncio.StreamWriter,
    ) -> None:
        async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            try:
                while not self._stopping:
                    data = await reader.read(65536)
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()
            except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
                pass
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        t1 = asyncio.create_task(_pipe(r1, w2))
        t2 = asyncio.create_task(_pipe(r2, w1))
        await asyncio.gather(t1, t2, return_exceptions=True)

    async def _send_error(
        self, writer: asyncio.StreamWriter, code: int, status: str, detail: str
    ) -> None:
        body = f"{code} {status}\r\n{detail}\r\n".encode("utf-8")
        resp = (
            f"HTTP/1.1 {code} {status}\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("latin-1") + body
        try:
            writer.write(resp)
            await writer.drain()
        except Exception:
            pass


class SocksBridgeRunner:
    """
    Thread-safe runner executing SocksHttpBridge inside a dedicated background asyncio event loop.
    Uses threading.Event to prevent busy-waiting during startup.
    """

    def __init__(
        self,
        proxy_url: str,
        host: str = "127.0.0.1",
        port: int = 0,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.proxy_url = proxy_url
        self.host = host
        self.port = port
        self.timeout = timeout
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.bridge: Optional[SocksHttpBridge] = None
        self.thread: Optional[threading.Thread] = None
        self._ready_event = threading.Event()
        self._bound_host: str = host
        self._bound_port: int = 0
        self._error: Optional[Exception] = None

    def start(self, timeout: float = 5.0) -> Tuple[str, int]:
        """Starts the bridge daemon thread and blocks until port is bound or timeout occurs."""
        self._ready_event.clear()
        self._error = None
        self.thread = threading.Thread(
            target=self._run, daemon=True, name="SocksBridgeThread"
        )
        self.thread.start()

        if not self._ready_event.wait(timeout=timeout):
            self.stop()
            raise TimeoutError("Timed out waiting for SocksHttpBridge to bind")

        if self._error:
            self.stop()
            raise RuntimeError(f"Failed to start SocksHttpBridge: {self._error}")

        return self._bound_host, self._bound_port

    def _run(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.bridge = SocksHttpBridge(
                self.proxy_url, host=self.host, port=self.port, timeout=self.timeout
            )
            self._bound_host, self._bound_port = self.loop.run_until_complete(
                self.bridge.start()
            )
            self._ready_event.set()
            self.loop.run_forever()
        except Exception as e:
            self._error = e
            self._ready_event.set()
        finally:
            try:
                pending = asyncio.all_tasks(self.loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self.loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                self.loop.close()
            except Exception:
                pass

    def stop(self, timeout: float = 2.0) -> None:
        """Stops the bridge server and terminates the event loop."""
        if self.bridge and self.loop and self.loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self.bridge.stop(), self.loop)
                future.result(timeout=timeout)
            except Exception:
                pass
            self.loop.call_soon_threadsafe(self.loop.stop)

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=timeout)
            self.thread = None

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive() and self._bound_port > 0

    def get_http_proxy_url(self) -> str:
        if not self.is_running():
            return ""
        return f"http://{self._bound_host}:{self._bound_port}"
