import CLibs


def getFullFileTree(bTestServer=False, bTestClient=False):
    path = CLibs.PathTools.getPath(bTestServer=bTestServer, bTestClient=bTestClient)
    return CLibs.PathTools.createFullFileTree(path)


def checkMissingFiles(local_tree, target_files):
    local_set = set(local_tree)
    missing = []
    for file in target_files:
        if file not in local_set and not file.startswith(".git"):
            missing.append(file)
    return missing


def checkFilesToPush(local_tree, target_files):
    remote_set = set(target_files)
    to_push = []
    for file in local_tree:
        if file not in remote_set and not file.startswith(".git"):
            to_push.append(file)
    return to_push