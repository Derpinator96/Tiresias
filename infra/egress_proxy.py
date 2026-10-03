"""Egress allowlist proxy for the ai container (doc, "Services, APIs and network isolation":
only ai may reach the internet, and only to the LLM API).

HTTP CONNECT only, deny by default. A tunnel opens only to a host in egress.allowed_hosts on a
port in egress.allowed_ports (config.yaml); any other host or port gets 403, any other method
405, a malformed request 400. TLS runs end to end through the tunnel, so the proxy sees the host
name and port, never the request content. Each decision is printed (host and port only).

ai has no internet route of its own: it shares only the internal `ai-proxy` network with this
proxy, and reaches the LLM through HTTPS_PROXY (httpx 0.28.1 honours it, trust_env on).
Stdlib only, run in the shared Python image:  python /app/egress_proxy.py PORT
"""
from __future__ import annotations

import asyncio
import sys

from common.config import cfg

# SIMPLIFIED part, on screen: the proxy checks the host name in the CONNECT line, not the traffic
# inside TLS (SNI and Host header are not compared with it).
LABEL = "AI egress: allowlist proxy, CONNECT to the LLM API host only (checks the host name, not the traffic inside TLS)"
REASONS = {400: "Bad Request", 403: "Forbidden", 405: "Method Not Allowed", 502: "Bad Gateway"}


def decide(head: bytes, hosts: list[str], ports: list[int]) -> tuple[int, str, int]:
    """(status, host, port) for a request head: 200 opens the tunnel, anything else denies."""
    try:
        method, target, _version = head.split(b"\r\n", 1)[0].decode("ascii").split(" ")
    except (UnicodeDecodeError, ValueError):
        return 400, "", 0
    if method != "CONNECT":
        return 405, "", 0
    host, sep, port = target.rpartition(":")
    if not sep or not port.isdigit():
        return 400, "", 0
    host = host.lower().rstrip(".")
    allowed = {h.lower().rstrip(".") for h in hosts}
    return (200 if host in allowed and int(port) in ports else 403), host, int(port)


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except ConnectionError:
        pass
    finally:
        writer.close()


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    timeout = float(cfg("egress.connect_timeout_s"))
    try:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError):
        writer.close()
        return
    status, host, port = decide(head, cfg("egress.allowed_hosts"), cfg("egress.allowed_ports"))
    if status == 200:
        try:
            up_reader, up_writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        except (OSError, asyncio.TimeoutError):
            status = 502
    print(f"{'allow' if status == 200 else 'deny'} {status} {host or '-'}:{port}", flush=True)
    if status != 200:
        writer.write(f"HTTP/1.1 {status} {REASONS[status]}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
        await writer.drain()
        writer.close()
        return
    writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
    await writer.drain()
    # ponytail: no idle timeout on an open tunnel (LLM calls run for minutes); add one if
    # tunnels are ever seen to leak.
    await asyncio.gather(_pipe(reader, up_writer), _pipe(up_reader, writer))


async def serve(port: int) -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", port)
    print(f"egress proxy on {port}: CONNECT to {cfg('egress.allowed_hosts')} ports {cfg('egress.allowed_ports')}, "
          "everything else denied", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(serve(int(sys.argv[1])))
