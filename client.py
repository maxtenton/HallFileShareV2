import asyncio
import functools
import os
import socket

import CLibs
from CLibs import Logger
import fileCheck
from protocol import send_all, recv_exact, recv_line, send_length
from dotenv import load_dotenv

global infile
infile = "client.py"
global Log
Log = Logger()

def Print(text : str) : 
    Log.print(string = f"{text}", file = infile)

load_dotenv()
PORT = 8080

NUM_WORKERS = int(os.getenv("CLIENT_WORKERS", "4"))

TEST_CLIENT = os.getenv("TEST_CLIENT", "0") == "1"


def _write_file(path: str, data: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def _read_file(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


def _chunk_list(items, n):
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
    reader, writer = await asyncio.open_connection(target_ip, PORT)
    try:
        greeting = await recv_line(reader)
        Print( text = greeting)
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
    if not files_chunk:
        return

    loop = asyncio.get_running_loop()
    reader, writer = await asyncio.open_connection(target_ip, PORT)
    try:
        await recv_line(reader)  # greeting
        await send_all(writer, b'FETCH\n')

        await send_length(writer, len(files_chunk))
        await recv_line(reader)  # ACK_AMNT

        for name in files_chunk:
            encoded = name.encode('utf-8')
            await send_length(writer, len(encoded))
            await recv_line(reader)          # ACK_LEN
            await send_all(writer, encoded)
            await recv_line(reader)          # ACK_NAME

        for name in files_chunk:
            file_len = int(await recv_line(reader))
            await send_all(writer, b'Received')

            if file_len == 0:
                Print( text = f"[worker {worker_id}] server could not provide: {name}")
                continue

            data = await recv_exact(reader, file_len)
            await send_all(writer, b'Received')

            out_path = os.path.join(base_path, name)
            await loop.run_in_executor(None, _write_file, out_path, data)
            Print( text = f"[worker {worker_id}] received {name} ({file_len} bytes)")
    finally:
        writer.close()
        await writer.wait_closed()


async def push_worker(target_ip: str, files_chunk: list[str], base_path: str, worker_id: int):
    if not files_chunk:
        return

    loop = asyncio.get_running_loop()
    reader, writer = await asyncio.open_connection(target_ip, PORT)
    try:
        await recv_line(reader)  # greeting
        await send_all(writer, b'PUSH\n')

        await send_length(writer, len(files_chunk))
        await recv_line(reader)  # ACK_AMNT

        for name in files_chunk:
            encoded = name.encode('utf-8')
            await send_length(writer, len(encoded))
            await recv_line(reader)          # ACK_LEN
            await send_all(writer, encoded)
            await recv_line(reader)          # ACK_NAME

        for name in files_chunk:
            full_path = os.path.join(base_path, name)
            try:
                data = await loop.run_in_executor(None, _read_file, full_path)
            except FileNotFoundError:
                Print( text = f"[push {worker_id}] local file vanished before send: {name}")
                await send_length(writer, 0)
                await recv_line(reader)
                continue

            await send_length(writer, len(data))
            await recv_line(reader)          # ack before data
            await send_all(writer, data)
            await recv_line(reader)          # ack after data
            Print( text = f"[push {worker_id}] sent {name} ({len(data)} bytes)")
    finally:
        writer.close()
        await writer.wait_closed()


async def start(TARGET: str = "127.0.0.1"):
    loop = asyncio.get_running_loop()

    try:
        Print( text = f"Connecting to {TARGET}:{PORT}...")
        server_files = await fetch_list(TARGET)
        Print( text = f"Server has {len(server_files)} files.")

        local_tree = await loop.run_in_executor(
            None, functools.partial(fileCheck.getFullFileTree, bTestClient=TEST_CLIENT)
        )
        Print( text = f"We have {len(local_tree)} files locally.")

        missing_locally = fileCheck.checkMissingFiles(local_tree, server_files)
        missing_remotely = fileCheck.checkFilesToPush(local_tree, server_files)
        Print( text = f"We are missing {len(missing_locally)} files (will download).")
        Print( text = f"Server is missing {len(missing_remotely)} files (will upload).")

        if not missing_locally and not missing_remotely:
            Print( text = "Already in sync.")
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

        Print( text = f"Syncing with {len(tasks)} parallel connection(s) ")
        Print( text = f"({len(fetch_chunks)} download, {len(push_chunks)} upload)..."
        )
        await asyncio.gather(*tasks)

        Print( text = "Sync complete.")

    except ConnectionRefusedError:
        Print( text = f"Error: Could not connect to {TARGET}:{PORT}. Is the server running?")
    except Exception as e:
        Print( text = f"An error occurred: {e}")


if __name__ == "__main__":
    target_ip = os.getenv('TARGET') or "127.0.0.1"
    try:
        target_ip = socket.gethostbyname(target_ip)
    except Exception:
        pass
    asyncio.run(start(TARGET=target_ip))