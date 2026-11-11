# The full measurement on your own computer, in Docker (no network, read-only root, no capabilities), from Windows PowerShell:
# how fast a day of traces is analysed, how many injected faults are handled, how fast the files are read, and that the two
# implementations agree. It takes a few minutes and a few GB of memory for the largest size.
# Usage: .\tools\run_full.ps1 [-Sizes 100,300,1000,2000] [-RefAircraft 100] [-Repeat 5] [-Draws 25] [-Seeds 20] [-Out results]
param(
    [string]$Sizes = "100,300,1000,2000",
    [int]$RefAircraft = 100,
    [int]$Repeat = 5,
    [int]$Draws = 25,
    [int]$Seeds = 20,
    [string]$Out = "results"
)
# Windows PowerShell 5.1 turns anything a program writes on stderr into an error under "Stop": docker and adsbstat print
# their progress there, so only the exit code is looked at.
$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$outFull = (Resolve-Path -LiteralPath $Out).Path

docker build -t adsbstat .
if ($LASTEXITCODE -ne 0) { Write-Host "docker build failed"; exit 1 }

Write-Host "== bench (sizes $Sizes aircraft, $Repeat runs each, $Draws random cases compared, $Seeds generated days for accuracy) =="
docker run --rm --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --network none -v "${outFull}:/out" adsbstat bench --sizes $Sizes --ref-aircraft $RefAircraft --repeat $Repeat --draws $Draws --seeds $Seeds --out /out
if ($LASTEXITCODE -ne 0) { Write-Host "bench failed (exit code $LASTEXITCODE)"; exit 1 }
Write-Host "Done. Send me $Out\bench.json, $Out\bench.md and $Out\summary.png."
