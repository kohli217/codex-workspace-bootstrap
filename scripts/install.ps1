param(
    [string]$Version = "1.0.0",
    [switch]$UserInstall
)

$ErrorActionPreference = "Stop"

Write-Host "codex-workspace-bootstrap installer"
Write-Host "Checking Python..."

$python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
} else {
    throw "Python was not found. Install Python 3.10 or later and run this script again."
}

& $python --version

if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') {
    throw "Version must use semantic version format such as 1.0.0."
}

$wheel = "https://github.com/kohli217/codex-workspace-bootstrap/releases/download/v$Version/codex_workspace_bootstrap-$Version-py3-none-any.whl"

$argsList = @("-m", "pip", "install")
if ($UserInstall) {
    $argsList += "--user"
}
$argsList += $wheel

Write-Host "Installing release v$Version..."
& $python @argsList

if ($LASTEXITCODE -ne 0) {
    throw "pip installation failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Installation complete."
Write-Host "Try:"
Write-Host "  cwb preflight ."
