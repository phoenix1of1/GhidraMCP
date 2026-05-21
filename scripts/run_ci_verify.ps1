$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Refresh = Join-Path $ScriptDir "refresh_snapshot_baselines.ps1"
$Tests = Join-Path $ScriptDir "run_regression_tests.ps1"
$StaticBaselineValidator = Join-Path $ScriptDir "validate_static_progress_baseline.py"

$DatasetPath = $null
$SkipStaticBaseline = $false
for ($i = 0; $i -lt $args.Count; $i++) {
    if ($args[$i] -eq "-DatasetPath" -and ($i + 1) -lt $args.Count) {
        $DatasetPath = $args[$i + 1]
        $i++
    }
    elseif ($args[$i] -eq "--skip-static-baseline") {
        $SkipStaticBaseline = $true
    }
}

if ($env:SKIP_STATIC_BASELINE -eq "1") {
    $SkipStaticBaseline = $true
}

function Resolve-PythonExe {
    $candidates = @(
        (Join-Path (Split-Path -Parent $ScriptDir) ".venv\Scripts\python.exe"),
        (Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) ".venv\Scripts\python.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    return $null
}

$RefreshArgs = @("-File", $Refresh, "--check", "--only", "all")
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

if (-not $SkipStaticBaseline) {
    $PythonExe = Resolve-PythonExe
    if (-not $PythonExe) {
        Write-Error "Static baseline validation requested but no Python executable was found. Use --skip-static-baseline to bypass."
        exit 1
    }

    Write-Host "[verify] Validating static recovery baseline"
    & $PythonExe $StaticBaselineValidator --python $PythonExe
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Static baseline validation failed."
        exit $LASTEXITCODE
    }
}
else {
    Write-Host "[verify] Skipping static recovery baseline validation"
}

Write-Host "[verify] Running regression tests"
& pwsh @TestArgs
exit $LASTEXITCODE
