Param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $ArgsFromCaller
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runner = Join-Path $ScriptDir "run_regression_tests.py"

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $Runner @ArgsFromCaller
    exit $LASTEXITCODE
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python $Runner @ArgsFromCaller
    exit $LASTEXITCODE
}

Write-Error "No Python interpreter found in PATH. Install Python 3 or use the py launcher."
exit 1
