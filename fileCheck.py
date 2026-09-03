import CLibs


def getFullFileTree(bTestServer=False, bTestClient=False):
    """Blocking. Call this via loop.run_in_executor(...) from async code."""
    path = CLibs.PathTools.getPath(bTestServer=bTestServer, bTestClient=bTestClient)
    return CLibs.PathTools.createFullFileTree(path)


def checkMissingFiles(local_tree, target_files):
    """Files the local side is missing (needs to download).

    local_tree: the caller's own file list (from getFullFileTree(), computed once)
    target_files: the remote list to diff against
    """
    local_set = set(local_tree)
    missing = []
    for file in target_files:
        if file not in local_set and not file.startswith(".git"):
            missing.append(file)
    return missing


def checkFilesToPush(local_tree, target_files):
    """Files the local side has that the remote side doesn't (needs to upload).

    local_tree: the caller's own file list
    target_files: the remote list to diff against
    """
    remote_set = set(target_files)
    to_push = []
    for file in local_tree:
        if file not in remote_set and not file.startswith(".git"):
            to_push.append(file)
    return to_push