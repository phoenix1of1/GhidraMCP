$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Refresh = Join-Path $ScriptDir "refresh_snapshot_baselines.ps1"
$Tests = Join-Path $ScriptDir "run_regression_tests.ps1"

$DatasetPath = $null
for ($i = 0; $i -lt $args.Count; $i++) {
    if ($args[$i] -eq "-DatasetPath" -and ($i + 1) -lt $args.Count) {
        $DatasetPath = $args[$i + 1]
        $i++
    }
}

$RefreshArgs = @("-File", $Refresh, "--check")
$TestArgs = @("-File", $Tests)

if ($DatasetPath) {
    $RefreshArgs += @("--input", $DatasetPath)
    $TestArgs += @("--input", $DatasetPath)
}

Write-Host "[verify] Dry-checking snapshot drift"
& pwsh @RefreshArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "Snapshot dry-check failed. Baselines were not modified."
    exit $LASTEXITCODE
}

Write-Host "[verify] Running regression tests"
& pwsh @TestArgs
exit $LASTEXITCODE
