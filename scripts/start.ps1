param([switch]$Demo, [int]$Port = 8000, [switch]$Build)
$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectDir
try {
    $pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Missing .venv. Run: uv sync --group dev' }
    if ($Build -or -not (Test-Path -LiteralPath 'app\web\dist\index.html')) {
        Push-Location -LiteralPath 'app\web'
        try {
            if (-not (Test-Path -LiteralPath 'node_modules')) { & npm.cmd ci; if ($LASTEXITCODE) { throw 'npm ci failed' } }
            & npm.cmd run build
            if ($LASTEXITCODE) { throw 'Frontend build failed' }
        } finally { Pop-Location }
    }
    Write-Host "AgentHub: http://127.0.0.1:$Port (Ctrl+C to stop)"
    $launchArgs = @('-m', 'agenthub', '--port', "$Port")
    if ($Demo) { $launchArgs += '--demo' }
    & $pythonExe @launchArgs
    if ($LASTEXITCODE) { throw "AgentHub exited: $LASTEXITCODE" }
} finally { Pop-Location }
