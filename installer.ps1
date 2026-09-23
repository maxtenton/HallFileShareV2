param()

$ErrorActionPreference = "Stop"

$Owner = "maxtenton"
$SourceRepo = "HallFileShareV2"       # repo used to update main.py (source mode)
$FrozenRepo = "HallFileShareV2Cooked" # repo used to update main.exe (compiled mode)
$Branch = "master"

$RootDir = $PSScriptRoot
$InstallerFiles = @("installer.ps1", "installer.bat")

function Write-Log($msg) {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] $msg"
}

function Get-RemoteVersion($url) {
    try {
        return (Invoke-RestMethod -Uri $url).version
    } catch {
        Write-Log "Could not reach $url ($_)"
        throw
    }
}

function Get-LocalVersion($path) {
    if (-not (Test-Path $path)) {
        return $null
    }
    return (Get-Content -Raw -Path $path | ConvertFrom-Json).version
}

function Clear-DestDir($destDir, $preserve) {
    if (-not (Test-Path $destDir)) { return }
    Get-ChildItem -Path $destDir -Force | ForEach-Object {
        if ($_.Name -eq ".git") { return }
        if ($preserve -contains $_.Name) { return }
        try {
            Remove-Item -Path $_.FullName -Recurse -Force -ErrorAction Stop
        } catch {
            Write-Log "Warning: could not remove $($_.FullName): $_"
        }
    }
}

function Sync-Repo($owner, $repo, $branch, $destDir, $preserve) {
    Write-Log "Clearing $destDir (preserving: $($preserve -join ', '), .git)..."
    Clear-DestDir -destDir $destDir -preserve $preserve

    Write-Log "Fetching file list from $owner/$repo (${branch})..."
    $treeUrl = "https://api.github.com/repos/$owner/$repo/git/trees/${branch}?recursive=1"
    $tree = Invoke-RestMethod -Uri $treeUrl
    $files = $tree.tree | Where-Object { $_.type -eq "blob" }
    Write-Log "Found $($files.Count) files. Downloading..."

    $i = 0
    foreach ($f in $files) {
        $i++
        $relPath = $f.path
        $localPath = Join-Path $destDir $relPath
        $localDir = Split-Path $localPath -Parent
        if ($localDir -and -not (Test-Path $localDir)) {
            New-Item -ItemType Directory -Path $localDir -Force | Out-Null
        }
        $rawUrl = "https://raw.githubusercontent.com/$owner/$repo/$branch/$relPath"
        try {
            Invoke-WebRequest -Uri $rawUrl -OutFile $localPath -UseBasicParsing
            Write-Log "[$i/$($files.Count)] Saved: $relPath"
        } catch {
            Write-Log "[$i/$($files.Count)] Failed: $relPath ($_)"
        }
    }
    Write-Log "Done syncing $destDir"
}

# ---------------------------------------------------------------------------
$hasExe = Test-Path (Join-Path $RootDir "main.exe")
$hasPy = Test-Path (Join-Path $RootDir "main.py")

if (-not $hasExe -and -not $hasPy) {
    Write-Log "Neither main.exe nor main.py found next to this installer. Nothing to update."
    Read-Host "Press Enter to exit"
    exit 0
}

$updatedSomething = $false

# --- main.exe (compiled) ---
if ($hasExe) {
    Write-Log "Checking main.exe version..."
    $localVersionPath = Join-Path $RootDir "_internal\version_info.json"
    $localVersion = Get-LocalVersion $localVersionPath
    $remoteUrl = "https://raw.githubusercontent.com/$Owner/$FrozenRepo/$Branch/_internal/version_info.json"
    $remoteVersion = Get-RemoteVersion $remoteUrl

    if ($localVersion -ne $remoteVersion) {
        Write-Log "Updating main.exe: $localVersion -> $remoteVersion"

        Write-Log "Closing any running main.exe..."
        Get-Process -Name "main" -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-Sleep -Seconds 1

        Sync-Repo -owner $Owner -repo $FrozenRepo -branch $Branch -destDir $RootDir `
            -preserve (@(".env") + $InstallerFiles)
        $updatedSomething = $true

        Write-Log "Relaunching main.exe..."
        Start-Process -FilePath (Join-Path $RootDir "main.exe") -WorkingDirectory $RootDir
    } else {
        Write-Log "main.exe is already up to date ($localVersion)."
    }
}

# --- main.py (source) ---
if ($hasPy) {
    Write-Log "Checking main.py version..."
    $localVersionPath = Join-Path $RootDir "version_info.json"
    $localVersion = Get-LocalVersion $localVersionPath
    $remoteUrl = "https://raw.githubusercontent.com/$Owner/$SourceRepo/$Branch/version_info.json"
    $remoteVersion = Get-RemoteVersion $remoteUrl

    if ($localVersion -ne $remoteVersion) {
        Write-Log "Updating main.py: $localVersion -> $remoteVersion"
        Sync-Repo -owner $Owner -repo $SourceRepo -branch $Branch -destDir $RootDir `
            -preserve (@(".env") + $InstallerFiles)
        $updatedSomething = $true
    } else {
        Write-Log "main.py is already up to date ($localVersion)."
    }
}

if (-not $updatedSomething) {
    Write-Log "Everything is already up to date."
}

Read-Host "`nPress Enter to exit"