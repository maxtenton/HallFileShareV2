import os
import pathlib
import socket
import datetime

folderInUser = "HallFileShare"


class PathTools:
    def getPath(bTestServer=False, bTestClient=False):
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
        tree = []
        for root, dirs, files in os.walk(path):
            for file in files:
                tree.append(PathTools.removeUserFromPath(os.path.join(root, file)))
        return tree


class NetTools:
    def getLocalIP():
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


class Logger:


    def getCurrentTime(self):
        x = datetime.datetime.now()
        dateFormatted = x.strftime("%d.%m.%Y : %H:%M:%S")
        return dateFormatted

    def print(self, string : str, file : str):
        print(string)
        with open("main.log", "a") as f:
            f.write(f"[{self.getCurrentTime()}] [{file}] : {string}\n")