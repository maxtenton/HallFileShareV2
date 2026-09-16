param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Destination
)

try {
    Move-Item -LiteralPath $Source -Destination $Destination -Force -ErrorAction Stop
    exit 0
} catch {
    Write-Host "MOVE FAILED: $($_.Exception.Message)"
    exit 1
}
