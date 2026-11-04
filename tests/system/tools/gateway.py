"""Expose fixed QA ports without giving the product network an internet route."""

import asyncio
import ssl
from functools import partial

TARGETS = {
    58000: ("api", 8000),
    53100: ("web", 3000),
    55433: ("postgres", 5432),
    58001: ("llm-proxy", 8000),
    58002: ("mock-mail", 8000),
}


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while chunk := await reader.read(65536):
            writer.write(chunk)
            await writer.drain()
    finally:
        writer.close()


async def relay(
    host: str, port: int, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    try:
        remote_reader, remote_writer = await asyncio.open_connection(host, port)
        await asyncio.gather(pipe(reader, remote_writer), pipe(remote_reader, writer))
    except (OSError, asyncio.IncompleteReadError):
        writer.close()


async def main() -> None:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain("/tls/cert.pem", "/tls/key.pem")
    servers = [
        await asyncio.start_server(
            partial(relay, host, port), "0.0.0.0", local, ssl=None if local == 55433 else context
        )
        for local, (host, port) in TARGETS.items()
    ]
    await asyncio.gather(*(server.serve_forever() for server in servers))


if __name__ == "__main__":
    asyncio.run(main())
