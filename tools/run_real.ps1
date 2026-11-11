# Analyse a real day of ADS-B traces (a .tar.aa part of an adsb.lol globe_history release) with OurAirports' airports.csv, in
# Docker (no network, read-only root, no capabilities, the input mounted read-only), from Windows PowerShell.
# Usage: .\tools\run_real.ps1 -Tar C:\path\v2025.05.18-planes-readsb-prod-0.tar.aa -Airports C:\path\airports.csv
#        [-Bbox "35,6,48,19"] [-Limit 0] [-Out results\real]
# -Bbox keeps only the positions inside lat0,lon0,lat1,lon1 (default: Italy and its surroundings); "" keeps everything.
# -Limit stops after that many aircraft (0 = all of them).
param(
    [Parameter(Mandatory = $true)][string]$Tar,
    [Parameter(Mandatory = $true)][string]$Airports,
    [string]$Bbox = "35,6,48,19",
    [int]$Limit = 0,
    [string]$Out = "results\real"
)
$ErrorActionPreference = "Continue"
$tarFull = (Resolve-Path -LiteralPath $Tar).Path
$apFull = (Resolve-Path -LiteralPath $Airports).Path
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$outFull = (Resolve-Path -LiteralPath $Out).Path

docker build -t adsbstat .
if ($LASTEXITCODE -ne 0) { Write-Host "docker build failed"; exit 1 }

$extra = @()
if ($Bbox -ne "") { $extra += @("--bbox", $Bbox) }
if ($Limit -gt 0) { $extra += @("--limit", "$Limit") }
$name = Split-Path -Leaf $tarFull

Write-Host "== real day: $name (this can take several minutes) =="
docker run --rm --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --network none `
    -v "${tarFull}:/in/${name}:ro" -v "${apFull}:/in/airports.csv:ro" -v "${outFull}:/out" `
    adsbstat analyze "/in/$name" --airports /in/airports.csv --name $name @extra --out /out
if ($LASTEXITCODE -ne 0) { Write-Host "analysis failed (exit code $LASTEXITCODE)"; exit 1 }
Write-Host "Done. Send me $Out\report.json, $Out\report.md, $Out\summary.png and the lines printed above."
