param(
    [string]$WorkerName = "cwb-github-free",
    [string]$QueueName = "cwb-github-scans"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $Root "wrangler.generated.json"
$ToolsRoot = Join-Path $Root ".tools"
$NodeToolRoot = Join-Path $ToolsRoot "node22"
$WranglerVersion = "4.136.1"
$script:CwbNode = $null
$script:CwbNpx = $null

function Get-CwbNodeTools {
    $existingNode = Get-ChildItem -Path $NodeToolRoot -Filter "node.exe" -File -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($existingNode) {
        $nodeDir = $existingNode.Directory.FullName
        $npxPath = Join-Path $nodeDir "npx.cmd"
        if (Test-Path $npxPath) {
            return @{
                Node = $existingNode.FullName
                Npx = $npxPath
            }
        }
    }

    Write-Host "Preparing CWB-local Node.js 22 LTS on this drive..."
    New-Item -ItemType Directory -Force -Path $NodeToolRoot | Out-Null

    $releaseBase = "https://nodejs.org/dist/latest-v22.x"
    $checksumsPath = Join-Path $NodeToolRoot "SHASUMS256.txt"
    Invoke-WebRequest -Uri "$releaseBase/SHASUMS256.txt" -OutFile $checksumsPath

    $matchingLine = Get-Content $checksumsPath |
        Where-Object { $_ -match "^([0-9a-fA-F]{64})\s+(node-v22\.[0-9.]+-win-x64\.zip)$" } |
        Select-Object -First 1

    if (-not $matchingLine) {
        throw "Could not resolve the current Node.js 22 Windows x64 archive."
    }

    $null = $matchingLine -match "^([0-9a-fA-F]{64})\s+(node-v22\.[0-9.]+-win-x64\.zip)$"
    $expectedHash = $Matches[1].ToLowerInvariant()
    $archiveName = $Matches[2]
    $archivePath = Join-Path $NodeToolRoot $archiveName

    Invoke-WebRequest -Uri "$releaseBase/$archiveName" -OutFile $archivePath

    $actualHash = (Get-FileHash -Path $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        Remove-Item -Force $archivePath -ErrorAction SilentlyContinue
        throw "Node.js 22 archive SHA-256 verification failed."
    }

    Expand-Archive -Path $archivePath -DestinationPath $NodeToolRoot -Force
    Remove-Item -Force $archivePath, $checksumsPath -ErrorAction SilentlyContinue

    $nodeFile = Get-ChildItem -Path $NodeToolRoot -Filter "node.exe" -File -Recurse |
        Select-Object -First 1
    if (-not $nodeFile) {
        throw "Portable Node.js 22 extraction did not produce node.exe."
    }

    $npxPath = Join-Path $nodeFile.Directory.FullName "npx.cmd"
    if (-not (Test-Path $npxPath)) {
        throw "Portable Node.js 22 extraction did not produce npx.cmd."
    }

    return @{
        Node = $nodeFile.FullName
        Npx = $npxPath
    }
}

$nodeTools = Get-CwbNodeTools
$script:CwbNode = $nodeTools.Node
$script:CwbNpx = $nodeTools.Npx
$env:npm_config_cache = Join-Path $ToolsRoot "npm-cache"

$nodeVersion = (& $script:CwbNode --version).Trim()
Write-Host "Using CWB-local Node.js $nodeVersion"

function Invoke-Wrangler {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    & $script:CwbNpx --yes "wrangler@$WranglerVersion" @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Wrangler command failed: $($Arguments -join ' ')"
    }
}

function New-RandomBase64Url {
    param([int]$Bytes)
    $nodeScript = "const crypto=require('crypto'); console.log(crypto.randomBytes($Bytes).toString('base64url'))"
    $value = (& $script:CwbNode -e $nodeScript).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $value) {
        throw "Could not generate secure random value with Node.js."
    }
    return $value
}

function Set-GitHubRepositoryVariable {
    param(
        [string]$Token,
        [string]$Value
    )

    $headers = @{
        "Accept" = "application/vnd.github+json"
        "Authorization" = "Bearer $Token"
        "User-Agent" = "codex-workspace-bootstrap"
        "X-GitHub-Api-Version" = "2026-03-10"
    }
    $baseUri = "https://api.github.com/repos/kohli217/codex-workspace-bootstrap/actions/variables"
    $body = @{
        name = "CWB_TOKEN_ENDPOINT"
        value = $Value
    } | ConvertTo-Json -Compress

    try {
        Invoke-RestMethod -Method Patch -Uri "$baseUri/CWB_TOKEN_ENDPOINT" -Headers $headers -ContentType "application/json" -Body $body | Out-Null
        return
    }
    catch {
        $status = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $status = [int]$_.Exception.Response.StatusCode
        }
        if ($status -ne 404) {
            throw
        }
    }

    Invoke-RestMethod -Method Post -Uri $baseUri -Headers $headers -ContentType "application/json" -Body $body | Out-Null
}

Write-Host "Checking Cloudflare authentication..."
$whoami = & $script:CwbNpx --yes "wrangler@$WranglerVersion" whoami --json 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Cloudflare login is required. A browser window will open."
    Invoke-Wrangler login
    $whoami = & $script:CwbNpx --yes "wrangler@$WranglerVersion" whoami --json
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
$kvListRaw = & $script:CwbNpx --yes "wrangler@$WranglerVersion" kv namespace list --config $ConfigPath
if ($LASTEXITCODE -ne 0) {
    throw "Could not list Cloudflare KV namespaces."
}
$kvList = ($kvListRaw -join [Environment]::NewLine) | ConvertFrom-Json
$kv = $kvList | Where-Object { $_.title -eq $namespaceTitle } | Select-Object -First 1
if (-not $kv) {
    Invoke-Wrangler kv namespace create CWB_STATE --config $ConfigPath
    $kvListRaw = & $script:CwbNpx --yes "wrangler@$WranglerVersion" kv namespace list --config $ConfigPath
    if ($LASTEXITCODE -ne 0) {
        throw "Could not re-read Cloudflare KV namespaces."
    }
    $kvList = ($kvListRaw -join [Environment]::NewLine) | ConvertFrom-Json
    $kv = $kvList | Where-Object {
        $_.title -eq $namespaceTitle
    } | Select-Object -First 1
}
if (-not $kv -or -not $kv.id) {
    throw "Could not resolve the CWB_STATE KV namespace id."
}

Write-Host "Ensuring Cloudflare Queue..."
$queueList = (& $script:CwbNpx --yes "wrangler@$WranglerVersion" queues list --config $ConfigPath 2>&1) -join [Environment]::NewLine
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
    Write-Host "A fine-grained GitHub token is required for the free gateway."
    Write-Host "Opening GitHub with the token name, owner, expiration, and permissions prefilled."
    Write-Host "On Repository access, choose: Only select repositories -> codex-workspace-bootstrap"
    $tokenUrl = "https://github.com/settings/personal-access-tokens/new?name=CWB%20Cloudflare%20Dispatch&description=CWB%20free%20gateway%20workflow%20dispatch&target_name=kohli217&expires_in=366&actions=write&variables=write"
    Start-Process $tokenUrl
    $secure = Read-Host "After GitHub generates the token, paste it here" -AsSecureString
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

$issued = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$setupToken = "v1.$issued.$(New-RandomBase64Url -Bytes 32)"

Write-Host "Uploading Worker secrets..."
$setupToken | & $script:CwbNpx --yes "wrangler@$WranglerVersion" secret put CWB_SETUP_TOKEN --config $ConfigPath | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Could not store CWB_SETUP_TOKEN." }

$dispatchToken | & $script:CwbNpx --yes "wrangler@$WranglerVersion" secret put CWB_DISPATCH_TOKEN --config $ConfigPath | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Could not store CWB_DISPATCH_TOKEN." }
Write-Host "Deploying free Cloudflare Worker..."
$deployOutput = (& $script:CwbNpx --yes "wrangler@$WranglerVersion" deploy --config $ConfigPath 2>&1)
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
    throw "Deployment succeeded, but the workers.dev URL could not be parsed. Re-run the script after confirming the Worker is visible in Cloudflare."
}

$workerUrl = $urlMatch.Value.TrimEnd("/")
$workerUrl | Set-Content -Path (Join-Path $Root ".worker-url") -Encoding UTF8

Write-Host "Pinning the token broker URL in the CWB repository..."
Set-GitHubRepositoryVariable -Token $dispatchToken -Value "$workerUrl/tokens/github"
$dispatchToken = $null

Write-Host ""
Write-Host "CWB free GitHub App gateway is deployed."
Write-Host "Worker: $workerUrl"
Write-Host ""
Write-Host "Open this setup URL within one hour:"
Write-Host "$workerUrl/setup/github#token=$setupToken"
Write-Host ""
Write-Host "The setup token is not sent to Cloudflare in the URL request and expires after one hour."
