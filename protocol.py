"""
Shared length-prefixed framing helpers for asyncio streams.

Every message is either:
  - a newline-terminated ASCII line (used for short headers/acks), or
  - a length-prefixed blob (length sent first via a line, then the raw bytes)
"""
import asyncio


async def send_all(writer: asyncio.StreamWriter, data: bytes):
    """Write bytes and flush. asyncio's StreamWriter.write() already buffers
    everything, so we just need to drain (the asyncio equivalent of making
    sure a partial send loop isn't needed)."""
    writer.write(data)
    await writer.drain()


async def recv_exact(reader: asyncio.StreamReader, length: int) -> bytes:
    """Receive exactly `length` bytes."""
    if length == 0:
        return b''
    try:
        return await reader.readexactly(length)
    except asyncio.IncompleteReadError as e:
        raise RuntimeError("Connection closed before full payload received") from e


async def recv_line(reader: asyncio.StreamReader) -> str:
    """Receive a newline-terminated line (header/ack)."""
    line = await reader.readline()
    if not line:
        raise RuntimeError("Connection closed while reading header")
    return line.decode('utf-8').strip()


async def send_length(writer: asyncio.StreamWriter, length: int):
    """Send an integer length as a newline-terminated string."""
    await send_all(writer, f"{length}\n".encode('utf-8'))
