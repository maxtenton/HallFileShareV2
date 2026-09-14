import requests
import json
import os
from dotenv import load_dotenv
from socket import gethostname

load_dotenv()

url = "https://raw.githubusercontent.com/maxtenton/HallFileShareV2/master/version_info.json"
response = requests.get(url)
repoData = response.json()
global activeData
with open("version_info.json", "r") as f:
    activeData = json.loads(f.read())

if activeData["version"] != repoData["version"]:
    print("Need to fetch newer version")
else:
    print("Version is latest")
    target = os.getenv("TARGET")
    print(gethostname())