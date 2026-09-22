param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $Root "wrangler.generated.json"
$UrlPath = Join-Path $Root ".worker-url"
$ToolsRoot = Join-Path $Root ".tools"
$NodeToolRoot = Join-Path $ToolsRoot "node22"
$WranglerVersion = "4.136.1"

if (-not (Test-Path $ConfigPath)) {
    throw "wrangler.generated.json was not found. Run deploy.ps1 first."
}
if (-not (Test-Path $UrlPath)) {
    throw ".worker-url was not found. Run deploy.ps1 again to refresh local deployment metadata."
}
$nodeFile = Get-ChildItem -Path $NodeToolRoot -Filter "node.exe" -File -Recurse -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $nodeFile) {
    throw "CWB-local Node.js 22 was not found. Run deploy.ps1 first."
}
$npxPath = Join-Path $nodeFile.Directory.FullName "npx.cmd"
if (-not (Test-Path $npxPath)) {
    throw "CWB-local npx.cmd was not found. Run deploy.ps1 again."
}
$env:npm_config_cache = Join-Path $ToolsRoot "npm-cache"

$nodeScript = "const crypto=require('crypto'); console.log(crypto.randomBytes(32).toString('base64url'))"
$random = (& $nodeFile.FullName -e $nodeScript).Trim()
if ($LASTEXITCODE -ne 0 -or -not $random) {
    throw "Could not generate a secure setup token."
}
$issued = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$setupToken = "v1.$issued.$random"

$setupToken | & $npxPath --yes "wrangler@$WranglerVersion" secret put CWB_SETUP_TOKEN --config $ConfigPath | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Could not rotate CWB_SETUP_TOKEN."
}

$workerUrl = (Get-Content -Path $UrlPath -Raw).Trim().TrimEnd("/")
Write-Host ""
Write-Host "Fresh one-hour setup URL:"
Write-Host "$workerUrl/setup/github#token=$setupToken"
