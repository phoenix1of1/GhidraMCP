Param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $ArgsFromCaller
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$PythonRunner = Join-Path $RepoRoot "scripts\run_discworld_extract.py"

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $PythonRunner @ArgsFromCaller
    exit $LASTEXITCODE
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python $PythonRunner @ArgsFromCaller
    exit $LASTEXITCODE
}

Write-Error "No Python interpreter found in PATH. Install Python 3 or use the py launcher."
exit 1
