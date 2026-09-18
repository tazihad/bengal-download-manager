"""
Unit tests for SocksHttpBridge and SocksBridgeRunner.
Tests local HTTP-to-SOCKS adapter, CONNECT tunneling, HTTP forwarding, and error handling.
"""

import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from core.services.socks_bridge import (
    SocksHttpBridge,
    SocksBridgeRunner,
    parse_host_port,
    MAX_HEADER_SIZE,
)
from core.utils import is_socks_proxy_config, get_upstream_proxy_url, get_aria2_proxy_url
from python_socks import ProxyConnectionError, ProxyTimeoutError


def test_parse_host_port():
    assert parse_host_port("example.com:8080") == ("example.com", 8080)
    assert parse_host_port("example.com", default_port=80) == ("example.com", 80)
    assert parse_host_port("example.com", default_port=443) == ("example.com", 443)
    assert parse_host_port("[::1]:8443") == ("::1", 8443)
    assert parse_host_port("[::1]", default_port=80) == ("::1", 80)
    assert parse_host_port("[2001:db8::1]:1080") == ("2001:db8::1", 1080)
    assert parse_host_port("   127.0.0.1:9050   ") == ("127.0.0.1", 9050)


def test_socks_proxy_config_helpers():
    socks5_cfg = {
        "mode": "manual",
        "type": "socks5",
        "host": "127.0.0.1",
        "port": 1080,
        "auth": True,
        "user": "test_user",
        "password": "secret_password",
    }
    assert is_socks_proxy_config(socks5_cfg) is True
    assert get_upstream_proxy_url(socks5_cfg) == "socks5://test_user:secret_password@127.0.0.1:1080"
    # Aria2 proxy URL returns empty for SOCKS because it cannot connect directly
    assert get_aria2_proxy_url(socks5_cfg) == ""

    socks4_cfg = {
        "mode": "manual",
        "type": "socks4",
        "host": "10.0.0.1",
        "port": 9050,
        "auth": True,
        "user": "ident_user",
        "password": "ignored_in_socks4",
    }
    assert is_socks_proxy_config(socks4_cfg) is True
    assert get_upstream_proxy_url(socks4_cfg) == "socks4://ident_user@10.0.0.1:9050"

    http_cfg = {
        "mode": "manual",
        "type": "http",
        "host": "proxy.corp.com",
        "port": 3128,
        "auth": False,
    }
    assert is_socks_proxy_config(http_cfg) is False
    assert get_upstream_proxy_url(http_cfg) == "http://proxy.corp.com:3128"
    assert get_aria2_proxy_url(http_cfg) == "http://proxy.corp.com:3128"

    direct_cfg = {"mode": "no_proxy"}
    assert is_socks_proxy_config(direct_cfg) is False
    assert get_upstream_proxy_url(direct_cfg) == ""
    assert get_aria2_proxy_url(direct_cfg) == ""


def test_socks_http_bridge_lifecycle():
    async def _run():
        bridge = SocksHttpBridge("socks5://127.0.0.1:1080", host="127.0.0.1", port=0)
        host, port = await bridge.start()
        assert host == "127.0.0.1"
        assert port > 0
        assert bridge.actual_port == port

        # Ensure port accepts connections
        reader, writer = await asyncio.open_connection(host, port)
        writer.close()
        await writer.wait_closed()

        await bridge.stop()
        assert bridge.server is None

    asyncio.run(_run())


def test_socks_bridge_runner_thread():
    runner = SocksBridgeRunner("socks5://127.0.0.1:1080", host="127.0.0.1", port=0)
    assert not runner.is_running()
    assert runner.get_http_proxy_url() == ""

    host, port = runner.start(timeout=5.0)
    assert runner.is_running()
    assert host == "127.0.0.1"
    assert port > 0
    assert runner.get_http_proxy_url() == f"http://127.0.0.1:{port}"

    runner.stop(timeout=2.0)
    assert not runner.is_running()
    assert runner.get_http_proxy_url() == ""


def test_bridge_connect_tunnel_success():
    """Simulates an HTTPS CONNECT tunnel relayed through a mock SOCKS proxy connection."""
    async def _run():
        bridge = SocksHttpBridge("socks5://127.0.0.1:1080", host="127.0.0.1", port=0)
        host, port = await bridge.start()

        received_from_client = []
        async def _mock_remote_server(r, w):
            data = await r.read(100)
            received_from_client.append(data)
            w.write(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nHELLO")
            await w.drain()
            w.close()
            await w.wait_closed()

        mock_remote = await asyncio.start_server(_mock_remote_server, host="127.0.0.1", port=0)
        remote_port = mock_remote.sockets[0].getsockname()[1]

        real_connect = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        real_connect.connect(("127.0.0.1", remote_port))

        with patch("core.services.socks_bridge.Proxy.from_url") as mock_proxy_cls:
            mock_proxy = MagicMock()
            mock_proxy.connect = AsyncMock(return_value=real_connect)
            mock_proxy_cls.return_value = mock_proxy

            client_r, client_w = await asyncio.open_connection(host, port)
            client_w.write(f"CONNECT 127.0.0.1:{remote_port} HTTP/1.1\r\nHost: 127.0.0.1:{remote_port}\r\n\r\n".encode())
            await client_w.drain()

            established_line = await client_r.readline()
            assert b"200 Connection Established" in established_line
            while True:
                line = await client_r.readline()
                if line in (b"\r\n", b"\n", b""):
                    break

            client_w.write(b"PING_SECURE")
            await client_w.drain()

            resp = await client_r.read(100)
            assert b"HELLO" in resp

            client_w.close()
            await client_w.wait_closed()

        mock_remote.close()
        await mock_remote.wait_closed()
        await bridge.stop()

    asyncio.run(_run())


def test_bridge_http_get_forwarding():
    """Simulates a plain HTTP GET request rewritten and forwarded through mock SOCKS."""
    async def _run():
        bridge = SocksHttpBridge("socks5://127.0.0.1:1080", host="127.0.0.1", port=0)
        host, port = await bridge.start()

        received_request = []
        async def _mock_http_dest(r, w):
            data = await r.read(1024)
            received_request.append(data)
            w.write(b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nPONG")
            await w.drain()
            w.close()
            await w.wait_closed()

        mock_dest = await asyncio.start_server(_mock_http_dest, host="127.0.0.1", port=0)
        dest_port = mock_dest.sockets[0].getsockname()[1]

        real_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        real_sock.connect(("127.0.0.1", dest_port))

        with patch("core.services.socks_bridge.Proxy.from_url") as mock_proxy_cls:
            mock_proxy = MagicMock()
            mock_proxy.connect = AsyncMock(return_value=real_sock)
            mock_proxy_cls.return_value = mock_proxy

            client_r, client_w = await asyncio.open_connection(host, port)
            client_w.write(
                (
                    f"GET http://127.0.0.1:{dest_port}/downloads/test.bin HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{dest_port}\r\n"
                    "Proxy-Connection: keep-alive\r\n\r\n"
                ).encode("latin-1")
            )
            await client_w.drain()

            resp = await client_r.read(1024)
            assert b"200 OK" in resp
            assert b"PONG" in resp

            client_w.close()
            await client_w.wait_closed()

        assert len(received_request) > 0
        assert b"GET /downloads/test.bin HTTP/1.1" in received_request[0]
        assert b"proxy-connection" not in received_request[0].lower()

        mock_dest.close()
        await mock_dest.wait_closed()
        await bridge.stop()

    asyncio.run(_run())


def test_bridge_socks_connection_error_502():
    """Verifies that an upstream SOCKS failure returns 502 Bad Gateway."""
    async def _run():
        bridge = SocksHttpBridge("socks5://127.0.0.1:1080", host="127.0.0.1", port=0)
        host, port = await bridge.start()

        with patch("core.services.socks_bridge.Proxy.from_url") as mock_proxy_cls:
            mock_proxy = MagicMock()
            mock_proxy.connect = AsyncMock(side_effect=ProxyConnectionError("SOCKS server unreachable"))
            mock_proxy_cls.return_value = mock_proxy

            client_r, client_w = await asyncio.open_connection(host, port)
            client_w.write(b"CONNECT destination.com:443 HTTP/1.1\r\nHost: destination.com\r\n\r\n")
            await client_w.drain()

            resp = await client_r.read(512)
            assert b"502 Bad Gateway" in resp
            assert b"SOCKS proxy connection failed" in resp

            client_w.close()
            await client_w.wait_closed()

        await bridge.stop()

    asyncio.run(_run())


def test_bridge_socks_timeout_504():
    """Verifies that an upstream SOCKS timeout returns 504 Gateway Timeout."""
    async def _run():
        bridge = SocksHttpBridge("socks5://127.0.0.1:1080", host="127.0.0.1", port=0)
        host, port = await bridge.start()

        with patch("core.services.socks_bridge.Proxy.from_url") as mock_proxy_cls:
            mock_proxy = MagicMock()
            mock_proxy.connect = AsyncMock(side_effect=ProxyTimeoutError("SOCKS handshake timed out"))
            mock_proxy_cls.return_value = mock_proxy

            client_r, client_w = await asyncio.open_connection(host, port)
            client_w.write(b"GET http://slow-server.org/large HTTP/1.1\r\nHost: slow-server.org\r\n\r\n")
            await client_w.drain()

            resp = await client_r.read(512)
            assert b"504 Gateway Timeout" in resp

            client_w.close()
            await client_w.wait_closed()

        await bridge.stop()

    asyncio.run(_run())


def test_bridge_header_size_limit():
    """Verifies that sending an oversized header returns 400 Bad Request."""
    async def _run():
        bridge = SocksHttpBridge("socks5://127.0.0.1:1080", host="127.0.0.1", port=0)
        host, port = await bridge.start()

        client_r, client_w = await asyncio.open_connection(host, port)
        oversized = b"GET / HTTP/1.1\r\nX-Spam: " + (b"A" * (MAX_HEADER_SIZE + 100)) + b"\r\n\r\n"
        client_w.write(oversized)
        await client_w.drain()

        resp = await client_r.read(512)
        assert b"400 Bad Request" in resp

        client_w.close()
        await client_w.wait_closed()
        await bridge.stop()

    asyncio.run(_run())
