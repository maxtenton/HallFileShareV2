import asyncio
from CLibs import Logger

global file, Log
file = "protocol.py"
Log = Logger()


async def send_all(writer: asyncio.StreamWriter, data: bytes):
    writer.write(data)
    await writer.drain()


async def recv_exact(reader: asyncio.StreamReader, length: int) -> bytes:
    if length == 0:
        return b''
    try:
        return await reader.readexactly(length)
    except asyncio.IncompleteReadError as e:
        Log.print(string = "Connection closed before full payload received", file = file)
        raise RuntimeError("Connection closed before full payload received") from e


async def recv_line(reader: asyncio.StreamReader) -> str:
    line = await reader.readline()
    if not line:
        Log.print(string = "Connection closed while reading header", file = file)
        raise RuntimeError("Connection closed while reading header")
    return line.decode('utf-8').strip()


async def send_length(writer: asyncio.StreamWriter, length: int):
    await send_all(writer, f"{length}\n".encode('utf-8'))
