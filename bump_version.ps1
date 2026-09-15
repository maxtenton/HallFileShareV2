param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("b","m","s")]
    [string]$Scale
)

$versionFile = Join-Path $PSScriptRoot "version_info.json"

if (-not (Test-Path $versionFile)) {
    Write-Error "version_info.json not found at $versionFile"
    exit 1
}

$json = Get-Content -Raw -Path $versionFile | ConvertFrom-Json

$parts = $json.version -split '\.'
if ($parts.Count -ne 3) {
    Write-Error "version field is not in X.Y.Z format: $($json.version)"
    exit 1
}

[int]$major = $parts[0]
[int]$minor = $parts[1]
[int]$patch = $parts[2]

switch ($Scale) {
    "b" { $major++; $minor = 0; $patch = 0 }   # big update
    "m" { $minor++; $patch = 0 }               # medium update
    "s" { $patch++ }                           # small update
}

$newVersion = "$major.$minor.$patch"
$json.version = $newVersion

$jsonText = $json | ConvertTo-Json -Depth 10
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($versionFile, $jsonText, $utf8NoBom)


Write-Host "Version updated to $newVersion"
