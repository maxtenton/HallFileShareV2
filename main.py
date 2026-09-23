import requests
import json
import os
import sys
import subprocess
from dotenv import load_dotenv
from socket import gethostname
from CLibs import Logger
import asyncio

global infile
infile = "main.py"
global Log
Log = Logger()

load_dotenv()

def Print(text : str) : 
    Log.print(string = f"{text}", file = infile)
# ---------------------------------------------------------------------------
# Config — adjust to match your repos
# ---------------------------------------------------------------------------
SOURCE_OWNER = "maxtenton"
SOURCE_REPO = "HallFileShareV2"          # repo used when running as main.py
FROZEN_OWNER = "maxtenton"
FROZEN_REPO = "HallFileShareV2Cooked"    # repo used when running as main.exe
BRANCH = "master"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.loads(f.read())


def fetch_json(url):
    resp = requests.get(url)
    resp.raise_for_status()
    return json.loads(resp.content.decode("utf-8-sig"))


def get_default_branch(owner: str, repo: str) -> str:
    url = f"https://api.github.com/repos/{owner}/{repo}"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()["default_branch"]


# ---------------------------------------------------------------------------
# Update: hand off to the standalone installer.ps1 (shipped alongside this
# app), then exit so it can safely replace files including this exe/script.
# ---------------------------------------------------------------------------
def run_installer_and_exit():
    root_dir = os.path.dirname(os.path.abspath(sys.executable if is_frozen() else __file__))
    installer_path = os.path.join(root_dir, "installer.ps1")

    if not os.path.isfile(installer_path):
        Print( text =f"ERROR: installer.ps1 not found at {installer_path}")
        Print( text ="Make sure installer.ps1 (and installer.bat) are shipped alongside this app.")
        sys.exit(1)

    Print( text =f"Launching installer: {installer_path}")
    subprocess.Popen(
    [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", installer_path,
    ],
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
)

    Print( text ="Installer launched. Exiting so it can update files...")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run_target():
    target = os.getenv("TARGET")
    Print( text =f"Hostname: {gethostname()}")
    if target == gethostname():
        import server
        asyncio.run(server.main())
    else:
        import client
        asyncio.run(client.start())


def main():
    if is_frozen():
        owner, repo = FROZEN_OWNER, FROZEN_REPO
        # PyInstaller 6.x --onedir builds place bundled data (including --add-data
        # files) inside an "_internal" subfolder by default. sys._MEIPASS points
        # at that folder at runtime, even if it's ever renamed via --contents-directory.
        internal_dir = getattr(sys, "_MEIPASS", os.path.join(
            os.path.dirname(os.path.abspath(sys.executable)), "_internal"
        ))
        version_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{BRANCH}/_internal/version_info.json"
        repoData = fetch_json(version_url)
        activeData = load_json(os.path.join(internal_dir, "version_info.json"))

        if activeData["version"] != repoData["version"]:
            Print( text ="Newer version available - handing off to installer...")
            run_installer_and_exit()
            # run_installer_and_exit calls sys.exit(); nothing below runs
        else:
            Print( text ="Version is latest")
            run_target()

    else:
        owner, repo = SOURCE_OWNER, SOURCE_REPO
        version_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{BRANCH}/version_info.json"
        repoData = fetch_json(version_url)
        activeData = load_json("version_info.json")

        if activeData["version"] != repoData["version"]:
            Print( text ="Newer version available - handing off to installer...")
            run_installer_and_exit()
            # run_installer_and_exit calls sys.exit(); nothing below runs
        else:
            Print( text ="Version is latest")
            run_target()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise  # normal exits (e.g. from trigger_update_and_exit) pass through untouched
    except Exception:
        import traceback

        error_text = traceback.format_exc()
        Print( text ="FATAL ERROR:")
        Print( text =error_text)

        # Always log to a file next to the exe/script, so the error survives
        # even if the console window closes before you can read it
        log_dir = os.path.dirname(os.path.abspath(sys.executable if is_frozen() else __file__))
        log_path = os.path.join(log_dir, "error_log.txt")
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                import datetime
                f.write(f"\n--- {datetime.datetime.now().isoformat()} ---\n")
                f.write(error_text)
            Print( text =f"This error was also saved to: {log_path}")
        except OSError:
            pass

        if is_frozen():
            # Keep the window open so a double-clicked .exe doesn't just vanish
            input("\nPress Enter to close this window...")
        sys.exit(1)