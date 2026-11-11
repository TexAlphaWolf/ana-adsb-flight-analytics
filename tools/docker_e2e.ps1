# End to end inside the image, from Windows PowerShell: a day of traces is generated, analysed and scored against its truth, the
# same day is read from a tar archive, a report is made (and rebuilt exactly from its JSON), the two implementations are compared
# and the benchmark runs small (read-only root, no capabilities, no network). Needs Docker Desktop.
# Usage: .\tools\docker_e2e.ps1 [-Image adsbstat]
param([string]$Image = "adsbstat")
$ErrorActionPreference = "Stop"

$id = Get-Random
$vol = "adsbstat-e2e-$id"
$secure = @("--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--network", "none", "-v", "${vol}:/data")

# Windows PowerShell 5.1 turns a program's message on stderr into an error under "Stop": the commands that are expected to
# fail run with errors not terminating, and only their exit code is looked at.
function Invoke-AdsbCode([int[]]$Allowed, [string[]]$AdsbArgs) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = docker run --rm @secure $Image @AdsbArgs 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($Allowed -notcontains $code) { throw "adsbstat $AdsbArgs exited with $code : $out" }
    ($out | Out-String)
}
function Invoke-Adsb([string[]]$AdsbArgs) { Invoke-AdsbCode @(0) $AdsbArgs }
function Read-Volume($path) {
    $out = docker run --rm --entrypoint cat -v "${vol}:/data" $Image $path 2>$null
    if ($LASTEXITCODE -ne 0) { throw "cannot read $path" }
    ($out | Out-String)
}
function Assert-Contains($text, $needle) { if ($text -notmatch [regex]::Escape($needle)) { throw "expected '$needle' in: $text" } }

try {
    docker volume create $vol | Out-Null
    docker run --rm --user 0 -v "${vol}:/data" --entrypoint chown $Image 10001 /data
    if ($LASTEXITCODE -ne 0) { throw "could not prepare the volume" }

    Assert-Contains (Invoke-Adsb @("generate", "/data/day", "--aircraft", "40", "--seed", "3")) "42 trace files, 91 flights"
    $rep = Invoke-Adsb @("analyze", "/data/day", "--out", "/data/out")
    Assert-Contains $rep "42 aircraft, 29,462 position reports, 91 flights"
    Assert-Contains $rep "against the truth: 91 of 91 flights found, 0 extra"
    Assert-Contains (Read-Volume "/data/out/report.json") '"kind": "report"'
    $md = Read-Volume "/data/out/report.md"
    Invoke-Adsb @("render", "/data/out/report.json", "-o", "/data/out/again.md") | Out-Null
    if ((Read-Volume "/data/out/again.md") -ne $md) { throw "the report rebuilt from the JSON is not identical" }

    # the same day from a tar archive, the way the real archives come
    docker run --rm --entrypoint python -v "${vol}:/data" $Image -c "import tarfile; t = tarfile.open('/data/day.tar.aa', 'w'); t.add('/data/day/traces', arcname='traces'); t.close()"
    if ($LASTEXITCODE -ne 0) { throw "could not make the tar archive" }
    Assert-Contains (Invoke-Adsb @("analyze", "/data/day.tar.aa", "--airports", "/data/day/airports.csv")) "42 aircraft, 29,462 position reports, 91 flights"
    Assert-Contains (Invoke-Adsb @("analyze")) "demo day"

    Assert-Contains (Invoke-Adsb @("verify", "--draws", "5")) "6 of 6 comparisons agree with the literal implementation"

    Invoke-Adsb @("bench", "--sizes", "20,40", "--ref-aircraft", "40", "--repeat", "1", "--draws", "2", "--seeds", "2", "--out", "/data/bench") | Out-Null
    Assert-Contains (Read-Volume "/data/bench/bench.json") '"ok": true'

    Invoke-AdsbCode @(2) @("analyze", "/data/nope") | Out-Null
    Write-Host "docker end-to-end: OK"
}
finally {
    $ErrorActionPreference = "Continue"
    docker volume rm -f $vol 2>&1 | Out-Null
}
