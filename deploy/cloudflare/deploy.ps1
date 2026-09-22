param(
    [string]$WorkerName = "cwb-github-free",
    [string]$QueueName = "cwb-github-scans"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $Root "wrangler.generated.json"

function Invoke-Wrangler {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    & npx --yes wrangler@4 @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Wrangler command failed: $($Arguments -join ' ')"
    }
}

function New-RandomBase64Url {
    param([int]$Bytes)
    $nodeScript = "const crypto=require('crypto'); console.log(crypto.randomBytes($Bytes).toString('base64url'))"
    $value = (& node -e $nodeScript).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $value) {
        throw "Could not generate secure random value with Node.js."
    }
    return $value
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js is required. Install Node.js 18+ and run this script again."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm/npx is required. Install Node.js with npm and run this script again."
}

Write-Host "Checking Cloudflare authentication..."
$whoami = & npx --yes wrangler@4 whoami --json 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Cloudflare login is required. A browser window will open."
    Invoke-Wrangler login
    $whoami = & npx --yes wrangler@4 whoami --json
    if ($LASTEXITCODE -ne 0) {
        throw "Cloudflare authentication did not complete."
    }
}

$bootstrap = @{
    name = $WorkerName
    main = "src/index.mjs"
    compatibility_date = "2026-09-01"
    workers_dev = $true
}
$bootstrap | ConvertTo-Json -Depth 8 | Set-Content -Path $ConfigPath -Encoding UTF8

Write-Host "Ensuring Workers KV namespace..."
$namespaceTitle = "$WorkerName-CWB_STATE"
$kvListRaw = & npx --yes wrangler@4 kv namespace list --config $ConfigPath
if ($LASTEXITCODE -ne 0) {
    throw "Could not list Cloudflare KV namespaces."
}
$kvList = $kvListRaw | ConvertFrom-Json
$kv = $kvList | Where-Object { $_.title -eq $namespaceTitle } | Select-Object -First 1
if (-not $kv) {
    Invoke-Wrangler kv namespace create CWB_STATE --config $ConfigPath
    $kvListRaw = & npx --yes wrangler@4 kv namespace list --config $ConfigPath
    if ($LASTEXITCODE -ne 0) {
        throw "Could not re-read Cloudflare KV namespaces."
    }
    $kvList = $kvListRaw | ConvertFrom-Json
    $kv = $kvList | Where-Object {
        $_.title -eq $namespaceTitle -or $_.title -like "*CWB_STATE"
    } | Select-Object -First 1
}
if (-not $kv -or -not $kv.id) {
    throw "Could not resolve the CWB_STATE KV namespace id."
}

Write-Host "Ensuring Cloudflare Queue..."
$queueList = (& npx --yes wrangler@4 queues list --config $ConfigPath 2>&1) -join [Environment]::NewLine
if ($LASTEXITCODE -ne 0) {
    throw "Could not list Cloudflare Queues."
}
if ($queueList -notmatch [regex]::Escape($QueueName)) {
    Invoke-Wrangler queues create $QueueName --message-retention-period-secs 86400 --config $ConfigPath
}

$config = @{
    name = $WorkerName
    main = "src/index.mjs"
    compatibility_date = "2026-09-01"
    workers_dev = $true
    kv_namespaces = @(
        @{
            binding = "CWB_STATE"
            id = [string]$kv.id
        }
    )
    queues = @{
        producers = @(
            @{
                binding = "SCAN_QUEUE"
                queue = $QueueName
            }
        )
        consumers = @(
            @{
                queue = $QueueName
                max_batch_size = 1
                max_batch_timeout = 1
                max_retries = 20
                max_concurrency = 1
            }
        )
    }
}
$config | ConvertTo-Json -Depth 12 | Set-Content -Path $ConfigPath -Encoding UTF8

$dispatchToken = $env:CWB_DISPATCH_TOKEN
if (-not $dispatchToken) {
    Write-Host ""
    Write-Host "A fine-grained GitHub token is required only to start the public CWB workflow."
    Write-Host "Scope it to kohli217/codex-workspace-bootstrap only, with Actions: Read and write."
    $secure = Read-Host "Paste the fine-grained GitHub token" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $dispatchToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}
if (-not $dispatchToken) {
    throw "GitHub dispatch token was empty."
}

$masterKey = New-RandomBase64Url -Bytes 32
$issued = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$setupToken = "v1.$issued.$(New-RandomBase64Url -Bytes 32)"

Write-Host "Uploading encrypted Worker secrets..."
$masterKey | & npx --yes wrangler@4 secret put CWB_MASTER_KEY --config $ConfigPath | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Could not store CWB_MASTER_KEY." }

$setupToken | & npx --yes wrangler@4 secret put CWB_SETUP_TOKEN --config $ConfigPath | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Could not store CWB_SETUP_TOKEN." }

$dispatchToken | & npx --yes wrangler@4 secret put CWB_DISPATCH_TOKEN --config $ConfigPath | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Could not store CWB_DISPATCH_TOKEN." }
$dispatchToken = $null

Write-Host "Deploying free Cloudflare Worker..."
$deployOutput = (& npx --yes wrangler@4 deploy --config $ConfigPath 2>&1)
$deployOutput | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Cloudflare Worker deployment failed."
}

$deployText = $deployOutput -join [Environment]::NewLine
$urlMatch = [regex]::Match(
    $deployText,
    "https://[A-Za-z0-9-]+\.[A-Za-z0-9.-]+\.workers\.dev"
)
if (-not $urlMatch.Success) {
    Write-Host ""
    Write-Host "Deployment succeeded, but the workers.dev URL could not be parsed automatically."
    Write-Host "Open Cloudflare Workers & Pages, select '$WorkerName', and copy its workers.dev URL."
    exit 0
}

$workerUrl = $urlMatch.Value.TrimEnd("/")
Write-Host ""
Write-Host "CWB free GitHub App gateway is deployed."
Write-Host "Worker: $workerUrl"
Write-Host ""
Write-Host "Open this setup URL within one hour:"
Write-Host "$workerUrl/setup/github#token=$setupToken"
Write-Host ""
Write-Host "The setup token is not sent to Cloudflare in the URL request and expires after one hour."
