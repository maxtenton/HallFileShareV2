import os
import pathlib
import socket

folderInUser = "HallFileShare"


class PathTools:
    def getPath(bTestServer=False, bTestClient=False):
        """Build the shared-folder path.

        For testing, pass bTestServer=True or bTestClient=True to suffix the
        folder name with "Server" / "Client" respectively, so you can run
        both ends on the same machine without them reading/writing the same
        directory. Leave both False for normal (non-test) use.
        """
        if bTestServer and bTestClient:
            raise ValueError("bTestServer and bTestClient cannot both be True")

        suffix = "Server" if bTestServer else "Client" if bTestClient else ""
        folder = folderInUser + suffix
        return os.path.join("C:\\Users", os.getlogin(), folder)

    def removeUserFromPath(path):
        p = pathlib.Path(path)
        nP = pathlib.Path(*p.parts[4:])
        return str(nP)

    def createFullFileTree(path):
        """Build the file tree fresh each call.

        NOTE: previously this appended to a module-level global list, so
        calling it more than once (e.g. once per server request) would
        duplicate every entry. It now returns a new list each time, which
        also makes it safe to call from a worker thread via
        loop.run_in_executor().
        """
        tree = []
        for root, dirs, files in os.walk(path):
            for file in files:
                tree.append(PathTools.removeUserFromPath(os.path.join(root, file)))
        return tree


class NetTools:
    def getLocalIP():
        """Best-effort detection of this machine's LAN IP.

        The old version only matched 192.168.x.x addresses and crashed with
        an IndexError on any other private range (10.x.x.x, 172.16-31.x.x,
        VPN adapters, etc). This uses the "connect a UDP socket, don't
        actually send anything" trick, which reliably reports the IP the OS
        would use to reach the outside world, regardless of subnet.
        """
        candidates = []

        # Primary method: ask the OS which interface would be used for
        # outbound traffic. Doesn't require internet access - UDP connect()
        # doesn't send packets, it just picks a route.
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                if ip and not ip.startswith("127."):
                    return ip
        except OSError:
            pass

        # Fallback: scan all addresses associated with the hostname for a
        # plausible private-network IP.
        try:
            local_hostname = socket.gethostname()
            ip_addresses = socket.gethostbyname_ex(local_hostname)[2]
            for ip in ip_addresses:
                if ip.startswith("127."):
                    continue
                if (
                    ip.startswith("192.168.")
                    or ip.startswith("10.")
                    or any(ip.startswith(f"172.{i}.") for i in range(16, 32))
                ):
                    candidates.append(ip)
        except socket.gaierror:
            pass

        if candidates:
            return candidates[0]

        raise RuntimeError(
            "Could not detect a local IP address. Pass an IP explicitly "
            "instead of relying on auto-detection (e.g. server.main(target_ip=...))."
        )