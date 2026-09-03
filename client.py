import asyncio
import functools
import os
import socket

import CLibs
import fileCheck
from protocol import send_all, recv_exact, recv_line, send_length
from dotenv import load_dotenv

load_dotenv()
PORT = 8080

# How many parallel connections to use for downloading files.
# Override with the CLIENT_WORKERS env var if you want to tune it.
NUM_WORKERS = int(os.getenv("CLIENT_WORKERS", "4"))

# Set TEST_CLIENT=1 in .env when running the client on the same machine as
# the server for testing - this suffixes the shared folder with "Client" so
# the two don't collide.
TEST_CLIENT = os.getenv("TEST_CLIENT", "0") == "1"


def _write_file(path: str, data: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def _read_file(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


def _chunk_list(items, n):
    """Split items into up to n roughly-equal, non-empty chunks."""
    if n <= 0:
        n = 1
    n = min(n, len(items)) or 1
    k, m = divmod(len(items), n)
    chunks = []
    idx = 0
    for i in range(n):
        size = k + (1 if i < m else 0)
        if size == 0:
            continue
        chunks.append(items[idx:idx + size])
        idx += size
    return chunks


async def fetch_list(target_ip: str) -> list[str]:
    """Open a LIST connection and retrieve the server's full file tree."""
    reader, writer = await asyncio.open_connection(target_ip, PORT)
    try:
        greeting = await recv_line(reader)
        print(greeting)
        await send_all(writer, b'LIST\n')

        file_amnt = int(await recv_line(reader))
        await send_all(writer, b'ACK')

        server_files = []
        for _ in range(file_amnt):
            name_len = int(await recv_line(reader))
            await send_all(writer, b'Ready')
            name = (await recv_exact(reader, name_len)).decode('utf-8')
            server_files.append(name)
            await send_all(writer, b'Received')

        return server_files
    finally:
        writer.close()
        await writer.wait_closed()


async def fetch_worker(target_ip: str, files_chunk: list[str], base_path: str, worker_id: int):
    """Open one FETCH connection and download this worker's slice of files."""
    if not files_chunk:
        return

    loop = asyncio.get_running_loop()
    reader, writer = await asyncio.open_connection(target_ip, PORT)
    try:
        await recv_line(reader)  # greeting
        await send_all(writer, b'FETCH\n')

        # Tell the server which files this connection wants.
        await send_length(writer, len(files_chunk))
        await recv_line(reader)  # ACK_AMNT

        for name in files_chunk:
            encoded = name.encode('utf-8')
            await send_length(writer, len(encoded))
            await recv_line(reader)          # ACK_LEN
            await send_all(writer, encoded)
            await recv_line(reader)          # ACK_NAME

        # Receive the actual file contents.
        for name in files_chunk:
            file_len = int(await recv_line(reader))
            await send_all(writer, b'Received')

            if file_len == 0:
                print(f"[worker {worker_id}] server could not provide: {name}")
                continue

            data = await recv_exact(reader, file_len)
            await send_all(writer, b'Received')

            out_path = os.path.join(base_path, name)
            # Offload the blocking disk write to a thread.
            await loop.run_in_executor(None, _write_file, out_path, data)
            print(f"[worker {worker_id}] received {name} ({file_len} bytes)")
    finally:
        writer.close()
        await writer.wait_closed()


async def push_worker(target_ip: str, files_chunk: list[str], base_path: str, worker_id: int):
    """Open one PUSH connection and upload this worker's slice of files.

    Mirror image of fetch_worker: here the client is the sender and the
    server is the receiver.
    """
    if not files_chunk:
        return

    loop = asyncio.get_running_loop()
    reader, writer = await asyncio.open_connection(target_ip, PORT)
    try:
        await recv_line(reader)  # greeting
        await send_all(writer, b'PUSH\n')

        # Tell the server which files this connection is about to send.
        await send_length(writer, len(files_chunk))
        await recv_line(reader)  # ACK_AMNT

        for name in files_chunk:
            encoded = name.encode('utf-8')
            await send_length(writer, len(encoded))
            await recv_line(reader)          # ACK_LEN
            await send_all(writer, encoded)
            await recv_line(reader)          # ACK_NAME

        # Send the actual file contents.
        for name in files_chunk:
            full_path = os.path.join(base_path, name)
            try:
                data = await loop.run_in_executor(None, _read_file, full_path)
            except FileNotFoundError:
                print(f"[push {worker_id}] local file vanished before send: {name}")
                await send_length(writer, 0)
                await recv_line(reader)
                continue

            await send_length(writer, len(data))
            await recv_line(reader)          # ack before data
            await send_all(writer, data)
            await recv_line(reader)          # ack after data
            print(f"[push {worker_id}] sent {name} ({len(data)} bytes)")
    finally:
        writer.close()
        await writer.wait_closed()


async def start(TARGET: str = "127.0.0.1"):
    loop = asyncio.get_running_loop()

    try:
        print(f"Connecting to {TARGET}:{PORT}...")
        server_files = await fetch_list(TARGET)
        print(f"Server has {len(server_files)} files.")

        # Building the local file tree is blocking (os.walk) - run it in a thread.
        local_tree = await loop.run_in_executor(
            None, functools.partial(fileCheck.getFullFileTree, bTestClient=TEST_CLIENT)
        )
        print(f"We have {len(local_tree)} files locally.")

        missing_locally = fileCheck.checkMissingFiles(local_tree, server_files)
        missing_remotely = fileCheck.checkFilesToPush(local_tree, server_files)
        print(f"We are missing {len(missing_locally)} files (will download).")
        print(f"Server is missing {len(missing_remotely)} files (will upload).")

        if not missing_locally and not missing_remotely:
            print("Already in sync.")
            return

        base_path = CLibs.PathTools.getPath(bTestClient=TEST_CLIENT)

        fetch_chunks = _chunk_list(missing_locally, NUM_WORKERS)
        push_chunks = _chunk_list(missing_remotely, NUM_WORKERS)

        tasks = [
            fetch_worker(TARGET, chunk, base_path, i)
            for i, chunk in enumerate(fetch_chunks)
        ] + [
            push_worker(TARGET, chunk, base_path, i)
            for i, chunk in enumerate(push_chunks)
        ]

        print(
            f"Syncing with {len(tasks)} parallel connection(s) "
            f"({len(fetch_chunks)} download, {len(push_chunks)} upload)..."
        )
        await asyncio.gather(*tasks)

        print("Sync complete.")

    except ConnectionRefusedError:
        print(f"Error: Could not connect to {TARGET}:{PORT}. Is the server running?")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    target_ip = os.getenv('TARGET') or "127.0.0.1"
    try:
        target_ip = socket.gethostbyname(target_ip)
    except Exception:
        pass
    asyncio.run(start(TARGET=target_ip))