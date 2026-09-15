import requests
import json
import os
from dotenv import load_dotenv
from socket import gethostname
import subprocess

load_dotenv()

url = "https://raw.githubusercontent.com/maxtenton/HallFileShareV2/master/version_info.json"
response = requests.get(url)
repoData = response.json()
global activeData
with open("version_info.json", "r") as f:
    activeData = json.loads(f.read())

def get_default_branch(owner: str, repo: str) -> str:
    url = f"https://api.github.com/repos/{owner}/{repo}"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()["default_branch"]
 
 
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
 
    # Get the full recursive file tree in one call
    tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    resp = requests.get(tree_url)
    resp.raise_for_status()
    tree_data = resp.json()
 
    if tree_data.get("truncated"):
        print("Warning: tree response was truncated (very large repo). "
              "Some files may be missing.")
 
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


if activeData["version"] != repoData["version"]:
    print("Need to fetch newer version")
    sync_repo("maxtenton", "HallFileShareV2", "./", branch="master")
        
else:
    print("Version is latest")
    target = os.getenv("TARGET")
    print(f"Hostname : {gethostname()}")
    if target == gethostname():
        subprocess.run(["python", "server.py"])
    else:
        subprocess.run(["python", "client.py"])
