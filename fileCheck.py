import CLibs
from CLibs import Logger

global file
file = "fileCheck.py"
global Log
Log = Logger()


def getFullFileTree(bTestServer=False, bTestClient=False):
    path = CLibs.PathTools.getPath(bTestServer=bTestServer, bTestClient=bTestClient)
    Log.print(string = "Got file tree", file = file)
    return CLibs.PathTools.createFullFileTree(path)


def checkMissingFiles(local_tree, target_files):
    local_set = set(local_tree)
    Log.print(string = "Checking missing files", file = file)
    missing = []
    for infile in target_files:
        Log.print(string = f"Checking if {infile} is missing", file = file)
        if infile not in local_set and not infile.startswith(".git"):
            missing.append(infile)
    Log.print(string = "Got all missing files", file = file)
    return missing


def checkFilesToPush(local_tree, target_files):
    remote_set = set(target_files)
    Log.print(string = "Checking files to push", file = file)
    to_push = []
    for infile in local_tree:
        Log.print(string = f"Checking {infile}", file = file)
        if infile not in remote_set and not infile.startswith(".git"):
            to_push.append(infile)
    Log.print(string = "Got all files to push", file = file)
    return to_push