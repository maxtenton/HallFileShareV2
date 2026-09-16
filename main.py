import requests
import json
import os
import sys
import tempfile
import subprocess
from dotenv import load_dotenv
from socket import gethostname

load_dotenv()

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
# Non-frozen sync (safe to overwrite the running .py, so this stays in-process)
# ---------------------------------------------------------------------------
def clear_dest_dir(dest_dir: str):
    import stat

    script_path = os.path.abspath(__file__)

    if not os.path.isdir(dest_dir):
        return

    for root, dirs, files in os.walk(dest_dir, topdown=True):
        dirs[:] = [d for d in dirs if d != ".git"]

        for name in files:
            file_path = os.path.join(root, name)
            if os.path.abspath(file_path) == script_path:
                continue
            try:
                os.remove(file_path)
            except PermissionError:
                try:
                    os.chmod(file_path, stat.S_IWRITE)
                    os.remove(file_path)
                except OSError as e:
                    print(f"Warning: could not delete {file_path} ({e})")

    for root, dirs, files in os.walk(dest_dir, topdown=False):
        if ".git" in os.path.relpath(root, dest_dir).split(os.sep):
            continue
        if os.path.abspath(root) != os.path.abspath(dest_dir):
            try:
                os.rmdir(root)
            except OSError:
                pass


def sync_repo(owner: str, repo: str, dest_dir: str, branch: str = None):
    if branch is None:
        branch = get_default_branch(owner, repo)
        print(f"Using default branch: {branch}")

    print(f"Clearing existing files in: {os.path.abspath(dest_dir)}")
    clear_dest_dir(dest_dir)

    tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    resp = requests.get(tree_url)
    resp.raise_for_status()
    tree_data = resp.json()

    if tree_data.get("truncated"):
        print("Warning: tree response was truncated (very large repo).")

    files = [item for item in tree_data["tree"] if item["type"] == "blob"]
    print(f"Found {len(files)} files. Downloading...")

    for i, item in enumerate(files, 1):
        rel_path = item["path"]
        local_path = os.path.join(dest_dir, rel_path)
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)

        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{rel_path}"
        file_resp = requests.get(raw_url)

        if file_resp.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(file_resp.content)
            print(f"[{i}/{len(files)}] Saved: {rel_path}")
        else:
            print(f"[{i}/{len(files)}] Failed ({file_resp.status_code}): {rel_path}")

    print(f"\nDone. Files saved to: {os.path.abspath(dest_dir)}")


# ---------------------------------------------------------------------------
# Frozen (.exe) update: hand off to an external PowerShell updater, then exit
# ---------------------------------------------------------------------------
UPDATER_SCRIPT = r"""
param(
    [Parameter(Mandatory=$true)][int]$ParentPid,
    [Parameter(Mandatory=$true)][string]$Owner,
    [Parameter(Mandatory=$true)][string]$Repo,
    [Parameter(Mandatory=$true)][string]$Branch,
    [Parameter(Mandatory=$true)][string]$RootDir,
    [Parameter(Mandatory=$true)][string]$ExeName
)

$ErrorActionPreference = "Stop"

function Write-Log($msg) {
    $timestamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$timestamp] $msg"
}

Write-Log "Updater started. Waiting for main app (PID $ParentPid) to exit..."
try {
    Wait-Process -Id $ParentPid -Timeout 30 -ErrorAction SilentlyContinue
} catch {}
Start-Sleep -Seconds 1   # let Windows release the file lock on the old exe

# Files/folders at the root of $RootDir that should never be touched
# (e.g. local machine config that isn't tracked in the repo)
$preserve = @()

Write-Log "Clearing $RootDir (preserving: $($preserve -join ', '))..."
Get-ChildItem -Path $RootDir -Force | ForEach-Object {
    if ($preserve -notcontains $_.Name) {
        try {
            Remove-Item -Path $_.FullName -Recurse -Force -ErrorAction Stop
        } catch {
            Write-Log "Warning: could not remove $($_.FullName): $_"
        }
    }
}

Write-Log "Fetching file list from $Owner/$Repo (${Branch})..."
$treeUrl = "https://api.github.com/repos/$Owner/$Repo/git/trees/${Branch}?recursive=1"
$tree = Invoke-RestMethod -Uri $treeUrl

$files = $tree.tree | Where-Object { $_.type -eq "blob" }
Write-Log "Found $($files.Count) files. Downloading..."

$i = 0
foreach ($f in $files) {
    $i++
    $relPath = $f.path
    $localPath = Join-Path $RootDir $relPath
    $localDir = Split-Path $localPath -Parent
    if ($localDir -and -not (Test-Path $localDir)) {
        New-Item -ItemType Directory -Path $localDir -Force | Out-Null
    }
    $rawUrl = "https://raw.githubusercontent.com/$Owner/$Repo/$Branch/$relPath"
    try {
        Invoke-WebRequest -Uri $rawUrl -OutFile $localPath -UseBasicParsing
        Write-Log "[$i/$($files.Count)] Saved: $relPath"
    } catch {
        Write-Log "[$i/$($files.Count)] Failed: $relPath ($_)"
    }
}

Write-Log "Update complete. Relaunching $ExeName..."
$exePath = Join-Path $RootDir $ExeName
Start-Process -FilePath $exePath -WorkingDirectory $RootDir

Write-Log "Cleaning up updater..."
Start-Sleep -Seconds 1
Remove-Item -Path $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"""


def trigger_update_and_exit(owner: str, repo: str, branch: str):
    """
    Writes the updater script to a temp location (outside the folder being
    wiped), launches it hidden and detached, then exits this process so the
    updater can safely replace everything including this .exe.
    """
    root_dir = os.path.dirname(os.path.abspath(sys.executable))
    exe_name = os.path.basename(sys.executable)

    updater_path = os.path.join(tempfile.gettempdir(), "hallfileshare_updater.ps1")
    with open(updater_path, "w", encoding="utf-8") as f:
        f.write(UPDATER_SCRIPT)

    print(f"Launching updater for {owner}/{repo} ({branch})...")
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden",
            "-File", updater_path,
            "-ParentPid", str(os.getpid()),
            "-Owner", owner,
            "-Repo", repo,
            "-Branch", branch,
            "-RootDir", root_dir,
            "-ExeName", exe_name,
        ],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
    )

    print("Update launched in background. Exiting so files can be replaced...")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run_target():
    target = os.getenv("TARGET")
    print(f"Hostname: {gethostname()}")
    if target == gethostname():
        subprocess.run(["python", "server.py"])
    else:
        subprocess.run(["python", "client.py"])


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
            print("Newer version available - handing off to updater...")
            trigger_update_and_exit(owner, repo, BRANCH)
            # trigger_update_and_exit calls sys.exit(); nothing below runs
        else:
            print("Version is latest")
            run_target()

    else:
        owner, repo = SOURCE_OWNER, SOURCE_REPO
        version_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{BRANCH}/version_info.json"
        repoData = fetch_json(version_url)
        activeData = load_json("version_info.json")

        if activeData["version"] != repoData["version"]:
            print("Need to fetch newer version")
            sync_repo(owner, repo, "./", branch=BRANCH)
        else:
            print("Version is latest")
            run_target()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise  # normal exits (e.g. from trigger_update_and_exit) pass through untouched
    except Exception:
        import traceback

        error_text = traceback.format_exc()
        print("\n" + "=" * 60)
        print("FATAL ERROR:")
        print(error_text)
        print("=" * 60)

        # Always log to a file next to the exe/script, so the error survives
        # even if the console window closes before you can read it
        log_dir = os.path.dirname(os.path.abspath(sys.executable if is_frozen() else __file__))
        log_path = os.path.join(log_dir, "error_log.txt")
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                import datetime
                f.write(f"\n--- {datetime.datetime.now().isoformat()} ---\n")
                f.write(error_text)
            print(f"This error was also saved to: {log_path}")
        except OSError:
            pass

        if is_frozen():
            # Keep the window open so a double-clicked .exe doesn't just vanish
            input("\nPress Enter to close this window...")
        sys.exit(1)