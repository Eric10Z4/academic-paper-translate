$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$hermesRuntime = Join-Path $env:LOCALAPPDATA 'hermes\hermes-agent\venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $hermesRuntime)) {
    throw "Hermes Python runtime not found: $hermesRuntime"
}
& $hermesRuntime -B (Join-Path $PSScriptRoot 'zotero_translate.py') @args
exit $LASTEXITCODE
