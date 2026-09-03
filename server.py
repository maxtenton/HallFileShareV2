import asyncio
import functools
import os
from concurrent.futures import ThreadPoolExecutor

import CLibs
import fileCheck
from protocol import send_all, recv_exact, recv_line, send_length
from dotenv import load_dotenv

load_dotenv()

PORT = 8080

# Set TEST_SERVER=1 in .env when running the server on the same machine as
# the client for testing - this suffixes the shared folder with "Server" so
# the two don't collide.
TEST_SERVER = os.getenv("TEST_SERVER", "0") == "1"

BASE_DIR = CLibs.PathTools.getPath(bTestServer=TEST_SERVER)  # server's base file directory

# Blocking disk reads run here so they don't block the asyncio event loop
# while other connections are mid-transfer.
DISK_THREADS = int(os.getenv("SERVER_THREADS", "4"))
executor = ThreadPoolExecutor(max_workers=DISK_THREADS, thread_name_prefix="disk-io")


def _read_file(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


def _write_file(path: str, data: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


async def handle_list(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Send the full remote file tree to the client."""
    loop = asyncio.get_running_loop()
    files = await loop.run_in_executor(
        executor, functools.partial(fileCheck.getFullFileTree, bTestServer=TEST_SERVER)
    )

    await send_length(writer, len(files))
    await reader.read(1024)  # wait for ACK

    for file in files:
        encoded = file.encode('utf-8')
        await send_length(writer, len(encoded))
        await reader.read(1024)          # wait for "Ready"
        await send_all(writer, encoded)
        await reader.read(1024)          # wait for "Received"


async def handle_fetch(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Receive a batch of requested filenames and stream their contents back.

    A single client may open several FETCH connections concurrently, each
    carrying a different slice of the missing-file list — that's what
    parallelizes the transfer.
    """
    loop = asyncio.get_running_loop()

    file_amnt = int(await recv_line(reader))
    await send_all(writer, b'ACK_AMNT\n')

    requested = []
    for _ in range(file_amnt):
        length = int(await recv_line(reader))
        await send_all(writer, b'ACK_LEN\n')
        name = (await recv_exact(reader, length)).decode('utf-8')
        await send_all(writer, b'ACK_NAME\n')
        requested.append(name)

    peer = writer.get_extra_info('peername')
    print(f"[{peer}] fetch worker requested {len(requested)} files")

    for name in requested:
        full_path = os.path.join(BASE_DIR, name)
        try:
            data = await loop.run_in_executor(executor, _read_file, full_path)
            await send_length(writer, len(data))
            await reader.read(1024)      # ACK
            await send_all(writer, data)
            await reader.read(1024)      # ACK
            print(f"[{peer}] sent {name} ({len(data)} bytes)")
        except FileNotFoundError:
            print(f"[{peer}] not found: {full_path}")
            await send_length(writer, 0)
            await reader.read(1024)


async def handle_push(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Receive a batch of filenames + contents from the client and write
    them into BASE_DIR. This is the mirror image of handle_fetch: here the
    client is the sender and the server is the receiver.

    A single client may open several PUSH connections concurrently, each
    uploading a different slice of the files the server is missing.
    """
    loop = asyncio.get_running_loop()

    file_amnt = int(await recv_line(reader))
    await send_all(writer, b'ACK_AMNT\n')

    names = []
    for _ in range(file_amnt):
        length = int(await recv_line(reader))
        await send_all(writer, b'ACK_LEN\n')
        name = (await recv_exact(reader, length)).decode('utf-8')
        await send_all(writer, b'ACK_NAME\n')
        names.append(name)

    peer = writer.get_extra_info('peername')
    print(f"[{peer}] push worker will receive {len(names)} files")

    for name in names:
        file_len = int(await recv_line(reader))
        await send_all(writer, b'Received\n')  # must be newline-terminated: client reads acks via recv_line()

        if file_len == 0:
            print(f"[{peer}] client had no data for {name}, skipping")
            continue

        data = await recv_exact(reader, file_len)
        await send_all(writer, b'Received\n')  # must be newline-terminated: client reads acks via recv_line()

        out_path = os.path.join(BASE_DIR, name)
        await loop.run_in_executor(executor, _write_file, out_path, data)
        print(f"[{peer}] stored {name} ({file_len} bytes)")


async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info('peername')
    print(f"Connection from {peer}")
    try:
        await send_all(writer, b'Connection established\n')
        role = (await recv_line(reader)).upper()

        if role == 'LIST':
            await handle_list(reader, writer)
        elif role == 'FETCH':
            await handle_fetch(reader, writer)
        elif role == 'PUSH':
            await handle_push(reader, writer)
        else:
            print(f"[{peer}] unknown role '{role}', closing")
    except (asyncio.IncompleteReadError, ConnectionError, RuntimeError) as e:
        print(f"[{peer}] connection error: {e}")
    except Exception as e:
        print(f"[{peer}] unexpected error: {e}")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        print(f"[{peer}] connection closed")


async def main(target_ip: str | None = None):
    # Bind to all interfaces by default so the server doesn't depend on
    # correctly guessing "the" LAN IP - that only matters for what you tell
    # clients to connect to, not what the socket binds to.
    bind_ip = target_ip or "0.0.0.0"
    server = await asyncio.start_server(handle_connection, bind_ip, PORT)

    try:
        detected_ip = CLibs.NetTools.getLocalIP()
        print(f"Server listening on {bind_ip}:{PORT} (reachable at {detected_ip}:{PORT} on your LAN)")
    except RuntimeError:
        print(f"Server listening on {bind_ip}:{PORT}")
        print("(Could not auto-detect a LAN IP - check your network settings if clients can't connect.)")

    print("Serving multiple concurrent connections (LIST + parallel FETCH workers).")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")