"""
Sync all files from a public GitHub repo to a local directory.

Usage:
    python github_sync.py

Or import and call sync_repo() directly with your own parameters.
"""

import os
import requests


def get_default_branch(owner: str, repo: str) -> str:
    """Look up the repo's default branch (main, master, etc.)."""
    url = f"https://api.github.com/repos/{owner}/{repo}"
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()["default_branch"]


def clear_dest_dir(dest_dir: str):
    """
    Remove all files/folders under dest_dir, except the currently running
    script itself (in case it lives inside dest_dir) and any .git directory
    (never touch git's internal data).
    """
    import stat

    script_path = os.path.abspath(__file__)

    if not os.path.isdir(dest_dir):
        return

    for root, dirs, files in os.walk(dest_dir, topdown=True):
        # Don't descend into .git at all
        dirs[:] = [d for d in dirs if d != ".git"]

        for name in files:
            file_path = os.path.join(root, name)
            if os.path.abspath(file_path) == script_path:
                continue  # never delete the running script
            try:
                os.remove(file_path)
            except PermissionError:
                # Windows sometimes marks files read-only; clear the flag and retry
                try:
                    os.chmod(file_path, stat.S_IWRITE)
                    os.remove(file_path)
                except OSError as e:
                    print(f"Warning: could not delete {file_path} ({e})")

    # Second pass, bottom-up, to remove now-empty directories
    for root, dirs, files in os.walk(dest_dir, topdown=False):
        if ".git" in os.path.relpath(root, dest_dir).split(os.sep):
            continue  # skip anything under .git
        if os.path.abspath(root) != os.path.abspath(dest_dir):
            try:
                os.rmdir(root)
            except OSError:
                pass  # not empty (e.g. contains the script, or .git)


def sync_repo(owner: str, repo: str, dest_dir: str, branch: str = None):
    """
    Replace the contents of dest_dir with every file in a public GitHub
    repo, preserving the repo's folder structure. Any existing files in
    dest_dir are deleted first, except the script currently running this
    sync (so you can safely run it from inside dest_dir).
    """
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


if __name__ == "__main__":
    OWNER = "maxtenton"
    REPO = "HallFileShareV2"
    BRANCH = "master"
    DEST_DIR = "./synced_repo"

    sync_repo(OWNER, REPO, DEST_DIR, branch=BRANCH)