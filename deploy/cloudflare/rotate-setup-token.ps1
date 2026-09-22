param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $Root "wrangler.generated.json"
$UrlPath = Join-Path $Root ".worker-url"

if (-not (Test-Path $ConfigPath)) {
    throw "wrangler.generated.json was not found. Run deploy.ps1 first."
}
if (-not (Test-Path $UrlPath)) {
    throw ".worker-url was not found. Run deploy.ps1 again to refresh local deployment metadata."
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js is required."
}

$nodeScript = "const crypto=require('crypto'); console.log(crypto.randomBytes(32).toString('base64url'))"
$random = (& node -e $nodeScript).Trim()
if ($LASTEXITCODE -ne 0 -or -not $random) {
    throw "Could not generate a secure setup token."
}
$issued = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$setupToken = "v1.$issued.$random"

$setupToken | & npx --yes wrangler@4 secret put CWB_SETUP_TOKEN --config $ConfigPath | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Could not rotate CWB_SETUP_TOKEN."
}

$workerUrl = (Get-Content -Path $UrlPath -Raw).Trim().TrimEnd("/")
Write-Host ""
Write-Host "Fresh one-hour setup URL:"
Write-Host "$workerUrl/setup/github#token=$setupToken"
