param(
    [string]$WorkerName = "cwb-github-free",
    [string]$QueueName = "cwb-github-scans",
    [switch]$ToolchainOnly
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
$env:npm_config_update_notifier = "false"
$env:NO_UPDATE_NOTIFIER = "1"

function Invoke-NativeCapture {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    # Windows PowerShell 5.1 can promote native stderr merged with 2>&1 into
    # NativeCommandError records. Capture stdout/stderr to separate local files
    # and use the process exit code as the source of truth instead.
    $captureId = [Guid]::NewGuid().ToString("N")
    $stdoutPath = Join-Path $ToolsRoot "$captureId.stdout"
    $stderrPath = Join-Path $ToolsRoot "$captureId.stderr"
    $exitCode = 1
    $stdoutLines = @()
    $stderrLines = @()
    $previousPreference = $ErrorActionPreference

    try {
        $ErrorActionPreference = "Continue"
        & $FilePath @Arguments 1> $stdoutPath 2> $stderrPath
        $exitCode = $LASTEXITCODE
        if (Test-Path $stdoutPath) {
            $stdoutLines = @(Get-Content -LiteralPath $stdoutPath)
        }
        if (Test-Path $stderrPath) {
            $stderrLines = @(Get-Content -LiteralPath $stderrPath)
        }
    }
    finally {
        $ErrorActionPreference = $previousPreference
        Remove-Item -Force $stdoutPath, $stderrPath -ErrorAction SilentlyContinue
    }

    return [PSCustomObject]@{
        ExitCode = $exitCode
        StdoutLines = $stdoutLines
        StderrLines = $stderrLines
    }
}

function Invoke-WranglerCapture {
    param([string[]]$Arguments)

    $allArguments = @("--yes", "wrangler@$WranglerVersion") + $Arguments
    return Invoke-NativeCapture -FilePath $script:CwbNpx -Arguments $allArguments
}

function Invoke-Wrangler {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    $result = Invoke-WranglerCapture -Arguments $Arguments
    $result.StdoutLines | Out-Host
    if ($result.ExitCode -ne 0) {
        $result.StderrLines | Out-Host
        throw "Wrangler command failed: $($Arguments -join ' ')"
    }
}

function Set-WranglerSecret {
    param(
        [string]$Name,
        [string]$Value
    )

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $Value | & $script:CwbNpx --yes "wrangler@$WranglerVersion" secret put $Name --config $ConfigPath | Out-Host
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) {
        throw "Could not store Wrangler secret $Name."
    }
}

function Find-WorkersDashboardUrl {
    param([string[]]$Lines)

    $text = $Lines -join [Environment]::NewLine
    $match = [regex]::Match(
        $text,
        "https://dash\.cloudflare\.com/([A-Za-z0-9]+)/workers/onboarding"
    )
    if ($match.Success) {
        $accountId = $match.Groups[1].Value
        return "https://dash.cloudflare.com/$accountId/workers-and-pages"
    }

    return "https://dash.cloudflare.com/?to=/:account/workers-and-pages"
}

function Resolve-CwbKvNamespace {
    param(
        [object[]]$Namespaces,
        [string]$PreferredTitle
    )

    $preferred = @($Namespaces | Where-Object { $_.title -eq $PreferredTitle }) |
        Select-Object -First 1
    if ($preferred) {
        return $preferred
    }

    # Compatibility with deployments created by CWB <= 0.7.0, where Wrangler
    # created the namespace with the binding name itself as the title.
    $legacy = @($Namespaces | Where-Object { $_.title -eq "CWB_STATE" }) |
        Select-Object -First 1
    if ($legacy) {
        Write-Host "Reusing existing legacy Workers KV namespace: CWB_STATE"
        return $legacy
    }

    return $null
}

function Test-WranglerSecretPresent {
    param(
        [string[]]$Lines,
        [string]$Name
    )

    try {
        $items = @(($Lines -join [Environment]::NewLine) | ConvertFrom-Json)
    }
    catch {
        return $false
    }

    return [bool](@($items | Where-Object { $_.name -eq $Name }).Count)
}

$nodeVersion = (& $script:CwbNode --version).Trim()
Write-Host "Using CWB-local Node.js $nodeVersion"

$wranglerVersionResult = Invoke-WranglerCapture -Arguments @("--version")
if ($wranglerVersionResult.ExitCode -ne 0) {
    $wranglerVersionResult.StdoutLines | Out-Host
    $wranglerVersionResult.StderrLines | Out-Host
    throw "CWB-local Wrangler smoke test failed."
}
Write-Host "Using CWB-local Wrangler $($wranglerVersionResult.StdoutLines -join ' ')"

if ($ToolchainOnly) {
    $stderrSmoke = Invoke-NativeCapture -FilePath $script:CwbNode -Arguments @(
        "-e",
        "process.stderr.write('CWB harmless stderr smoke\\n'); process.stdout.write('CWB stdout smoke\\n')"
    )
    if (
        $stderrSmoke.ExitCode -ne 0 -or
        ($stderrSmoke.StdoutLines -join [Environment]::NewLine) -notmatch "CWB stdout smoke" -or
        ($stderrSmoke.StderrLines -join [Environment]::NewLine) -notmatch "CWB harmless stderr smoke"
    ) {
        throw "Windows PowerShell native stderr capture smoke test failed."
    }

    $preferredTitle = "cwb-github-free-CWB_STATE"
    $preferredNamespace = [PSCustomObject]@{ title = $preferredTitle; id = "preferred-id" }
    $legacyNamespace = [PSCustomObject]@{ title = "CWB_STATE"; id = "legacy-id" }

    $resolvedPreferred = Resolve-CwbKvNamespace -Namespaces @($legacyNamespace, $preferredNamespace) -PreferredTitle $preferredTitle
    if (-not $resolvedPreferred -or $resolvedPreferred.id -ne "preferred-id") {
        throw "Workers KV namespace resolver did not prefer the canonical title."
    }

    $resolvedLegacy = Resolve-CwbKvNamespace -Namespaces @($legacyNamespace) -PreferredTitle $preferredTitle
    if (-not $resolvedLegacy -or $resolvedLegacy.id -ne "legacy-id") {
        throw "Workers KV namespace resolver did not reuse the legacy CWB_STATE title."
    }

    $sampleOnboarding = @(
        "ERROR You can register a workers.dev subdomain here:",
        "https://dash.cloudflare.com/0123456789abcdef0123456789abcdef/workers/onboarding"
    )
    $resolvedDashboard = Find-WorkersDashboardUrl -Lines $sampleOnboarding
    if ($resolvedDashboard -ne "https://dash.cloudflare.com/0123456789abcdef0123456789abcdef/workers-and-pages") {
        throw "workers.dev dashboard URL resolver smoke test failed."
    }

    Write-Host "CWB-local Windows Wrangler toolchain smoke test: PASS"
    Write-Host "Windows PowerShell harmless native stderr smoke test: PASS"
    $secretFixture = @(
        '[{"name":"CWB_SETUP_TOKEN","type":"secret_text"},{"name":"CWB_DISPATCH_TOKEN","type":"secret_text"}]'
    )
    if (-not (Test-WranglerSecretPresent -Lines $secretFixture -Name "CWB_DISPATCH_TOKEN")) {
        throw "Wrangler secret-list reuse smoke test failed."
    }
    if (Test-WranglerSecretPresent -Lines $secretFixture -Name "MISSING_SECRET") {
        throw "Wrangler secret-list missing-secret smoke test failed."
    }

    Write-Host "Workers KV namespace compatibility smoke test: PASS"
    Write-Host "Cloudflare existing-secret reuse smoke test: PASS"
    exit 0
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

Write-Host "Checking Cloudflare authentication..."
$whoamiResult = Invoke-WranglerCapture -Arguments @("whoami", "--json")
if ($whoamiResult.ExitCode -ne 0) {
    Write-Host "Cloudflare login is required. A browser window will open."
    Invoke-Wrangler login
    $whoamiResult = Invoke-WranglerCapture -Arguments @("whoami", "--json")
    if ($whoamiResult.ExitCode -ne 0) {
        $whoamiResult.StdoutLines | Out-Host
        $whoamiResult.StderrLines | Out-Host
        throw "Cloudflare authentication did not complete."
    }
}
$whoami = $whoamiResult.StdoutLines

$bootstrap = @{
    name = $WorkerName
    main = "src/index.mjs"
    compatibility_date = "2026-09-01"
    workers_dev = $true
}
$bootstrap | ConvertTo-Json -Depth 8 | Set-Content -Path $ConfigPath -Encoding UTF8

Write-Host "Ensuring Workers KV namespace..."
$namespaceTitle = "$WorkerName-CWB_STATE"
$kvListResult = Invoke-WranglerCapture -Arguments @("kv", "namespace", "list", "--config", $ConfigPath)
if ($kvListResult.ExitCode -ne 0) {
    $kvListResult.StdoutLines | Out-Host
    $kvListResult.StderrLines | Out-Host
    throw "Could not list Cloudflare KV namespaces."
}
$kvListRaw = $kvListResult.StdoutLines
$kvList = @(($kvListRaw -join [Environment]::NewLine) | ConvertFrom-Json)
$kv = Resolve-CwbKvNamespace -Namespaces $kvList -PreferredTitle $namespaceTitle
if (-not $kv) {
    Invoke-Wrangler kv namespace create $namespaceTitle --config $ConfigPath
    $kvListResult = Invoke-WranglerCapture -Arguments @("kv", "namespace", "list", "--config", $ConfigPath)
    if ($kvListResult.ExitCode -ne 0) {
        $kvListResult.StdoutLines | Out-Host
        $kvListResult.StderrLines | Out-Host
        throw "Could not re-read Cloudflare KV namespaces."
    }
    $kvListRaw = $kvListResult.StdoutLines
    $kvList = @(($kvListRaw -join [Environment]::NewLine) | ConvertFrom-Json)
    $kv = Resolve-CwbKvNamespace -Namespaces $kvList -PreferredTitle $namespaceTitle
}
if (-not $kv -or -not $kv.id) {
    throw "Could not resolve the CWB_STATE KV namespace id."
}
Write-Host "Using Workers KV namespace '$($kv.title)' ($($kv.id))"

Write-Host "Ensuring Cloudflare Queue..."
$queueListResult = Invoke-WranglerCapture -Arguments @("queues", "list", "--config", $ConfigPath)
if ($queueListResult.ExitCode -ne 0) {
    $queueListResult.StdoutLines | Out-Host
    $queueListResult.StderrLines | Out-Host
    throw "Could not list Cloudflare Queues."
}
$queueList = $queueListResult.StdoutLines -join [Environment]::NewLine
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

$dispatchSecretExists = $false
$secretListResult = Invoke-WranglerCapture -Arguments @(
    "secret", "list", "--format", "json", "--config", $ConfigPath
)
if ($secretListResult.ExitCode -eq 0) {
    $dispatchSecretExists = Test-WranglerSecretPresent -Lines $secretListResult.StdoutLines -Name "CWB_DISPATCH_TOKEN"
}

$dispatchToken = $env:CWB_DISPATCH_TOKEN
if (-not $dispatchToken -and -not $dispatchSecretExists) {
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
elseif (-not $dispatchToken -and $dispatchSecretExists) {
    Write-Host "Reusing existing Cloudflare secret: CWB_DISPATCH_TOKEN"
}

if (-not $dispatchToken -and -not $dispatchSecretExists) {
    throw "GitHub dispatch token was empty."
}

$issued = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$setupToken = "v1.$issued.$(New-RandomBase64Url -Bytes 32)"

Write-Host "Uploading Worker secrets..."
Set-WranglerSecret -Name "CWB_SETUP_TOKEN" -Value $setupToken
if ($dispatchToken) {
    Set-WranglerSecret -Name "CWB_DISPATCH_TOKEN" -Value $dispatchToken
}
Write-Host "Deploying free Cloudflare Worker..."
$deployResult = Invoke-WranglerCapture -Arguments @("deploy", "--config", $ConfigPath)
$deployResult.StdoutLines | Out-Host
if ($deployResult.ExitCode -ne 0) {
    $deployResult.StderrLines | Out-Host
    $combinedDeployLines = @(
        $deployResult.StdoutLines + $deployResult.StderrLines
    )
    if (($combinedDeployLines -join [Environment]::NewLine) -match "workers\.dev subdomain") {
        $workersDashboardUrl = Find-WorkersDashboardUrl -Lines $combinedDeployLines
        Write-Host ""
        Write-Host "Cloudflare requires one-time workers.dev subdomain registration."
        Write-Host "Opening the current Workers & Pages dashboard in your browser..."
        Start-Process $workersDashboardUrl
        throw "In Workers & Pages, set Your subdomain -> Change, then rerun this deployment command."
    }
    throw "Cloudflare Worker deployment failed."
}

$deployText = $deployResult.StdoutLines -join [Environment]::NewLine
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
$pinBody = @{ token = $setupToken } | ConvertTo-Json -Compress
$pinSucceeded = $false
for ($attempt = 1; $attempt -le 5; $attempt++) {
    try {
        Invoke-RestMethod -Method Post -Uri "$workerUrl/setup/repository-variable" -ContentType "application/json" -Body $pinBody | Out-Null
        $pinSucceeded = $true
        break
    }
    catch {
        if ($attempt -eq 5) {
            throw "Worker deployed, but CWB_TOKEN_ENDPOINT could not be pinned through the Worker."
        }
        Start-Sleep -Seconds 2
    }
}
if (-not $pinSucceeded) {
    throw "Worker deployed, but CWB_TOKEN_ENDPOINT pinning did not complete."
}
$dispatchToken = $null

Write-Host ""
Write-Host "CWB free GitHub App gateway is deployed."
Write-Host "Worker: $workerUrl"
Write-Host ""
Write-Host "Open this setup URL within one hour:"
Write-Host "$workerUrl/setup/github#token=$setupToken"
Write-Host ""
Write-Host "The setup token is not sent to Cloudflare in the URL request and expires after one hour."
