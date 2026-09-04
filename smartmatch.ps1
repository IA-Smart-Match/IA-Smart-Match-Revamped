<#
.SYNOPSIS
    SmartMatch launcher for Windows PowerShell.

.DESCRIPTION
    The same command set as ./smartmatch.sh, for a Windows machine running
    Docker Desktop. The two files are held in step by
    tests/unit/test_launcher_parity.py, which reads the command list and the
    health-check identifiers out of both and fails the build if they differ.

    Windows without WSL has Docker Desktop and PowerShell but no bash, which is
    why this file reimplements the health suite rather than calling
    scripts/compose_health.sh. HTTP is done with curl.exe — shipped in Windows
    since 1803 — rather than Invoke-WebRequest, because Windows PowerShell 5.1
    throws on a non-2xx response and has no -SkipHttpErrorCheck, so a health
    probe written against it reads a 503 as an exception instead of as a
    status code.

    This is a launcher, not a deployment tool. Everything happens on this
    machine against the local-only stack docker-compose.yml describes:
    ALLOW_CLOUD_DEPLOY=false is untouched, no image is published, and nothing
    reaches outside the compose network.

.PARAMETER Command
    install, start, stop, restart, status, health, verify, or logs.

.EXAMPLE
    .\smartmatch.ps1 install
    .\smartmatch.ps1 install -Developer
    .\smartmatch.ps1 status -Json
    .\smartmatch.ps1 health -Wait
    .\smartmatch.ps1 verify -Full
    .\smartmatch.ps1 logs api

.NOTES
    Exit codes, identical to smartmatch.sh:
      0  success
      1  the stack is unhealthy, or a verification failed
      2  usage error
      3  a prerequisite is missing (docker, or compose v2)
      4  a published port is already held by something that is not this stack
      5  timed out waiting for the stack to become healthy

    `stop` never removes a volume. Discarding the database is
    `docker compose down -v`, typed out by hand, on purpose.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string] $Command = '',

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]] $Rest = @(),

    [switch] $Developer,
    [switch] $Json,
    [switch] $Wait,
    [switch] $Full,
    [switch] $Follow,
    [int]    $Timeout = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:ExitOk        = 0
$script:ExitUnhealthy = 1
$script:ExitUsage     = 2
$script:ExitPrereq    = 3
$script:ExitPort      = 4
$script:ExitTimeout   = 5

$script:RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$script:ApiBase    = if ($env:SMARTMATCH_API_BASE)    { $env:SMARTMATCH_API_BASE }    else { 'http://127.0.0.1:8080' }
$script:WorkerBase = if ($env:SMARTMATCH_WORKER_BASE) { $env:SMARTMATCH_WORKER_BASE } else { 'http://127.0.0.1:8081' }
$script:WebBase    = if ($env:SMARTMATCH_WEB_BASE)    { $env:SMARTMATCH_WEB_BASE }    else { 'http://127.0.0.1:5173' }

# The compose file's own x-compose-dev-identity literal. It authenticates
# nothing outside the compose network.
$script:ApiBearer  = if ($env:SMARTMATCH_API_BEARER) { $env:SMARTMATCH_API_BEARER } else { 'compose-api' }
$script:PilotEmail = 'compose-pilot-coordinator@example.invalid'

# Resolved exactly the way compose resolves ${SMARTMATCH_RELEASE}: the process
# environment first, then ./.env, then docker-compose.yml's own `compose-dev`
# default. Any other order makes this check disagree with the value compose
# actually passed to the container and turns a correct stack red.
function Resolve-ExpectedRelease {
    if ($env:SMARTMATCH_RELEASE) { return $env:SMARTMATCH_RELEASE }
    $envFile = Join-Path $script:RepoRoot '.env'
    if (Test-Path $envFile) {
        $match = Select-String -LiteralPath $envFile -Pattern '^\s*SMARTMATCH_RELEASE\s*=\s*"?([^"#]*)"?' |
            Select-Object -Last 1
        if ($match) {
            $value = $match.Matches[0].Groups[1].Value.Trim()
            if ($value) { return $value }
        }
    }
    return 'compose-dev'
}
$script:ExpectedRelease = Resolve-ExpectedRelease
$script:HeartbeatMaxAgeSeconds = if ($env:SMARTMATCH_HEARTBEAT_MAX_AGE_SECONDS) { [int] $env:SMARTMATCH_HEARTBEAT_MAX_AGE_SECONDS } else { 300 }
$script:CurlTimeout = if ($env:SMARTMATCH_CURL_TIMEOUT) { [int] $env:SMARTMATCH_CURL_TIMEOUT } else { 10 }
$script:ReadyTimeout = if ($env:SMARTMATCH_READY_TIMEOUT) { [int] $env:SMARTMATCH_READY_TIMEOUT } else { 900 }

# The published ports of docker-compose.yml, all bound to 127.0.0.1.
$script:PublishedPorts = [ordered] @{
    5432 = 'postgres'
    8080 = 'api'
    8081 = 'worker'
    5173 = 'web'
}

$script:ComposeServices = @('db', 'migrate', 'seed', 'seed-logins', 'api', 'worker', 'scheduler', 'seed-review', 'web')

# One-shots whose exit code decides whether the stack is in its expected state.
#
# `seed-logins` is deliberately absent: it seeds the OPTIONAL pilot logins from
# SMARTMATCH_PILOT_*_EMAIL/_PASSWORD and exits 2 when none is configured, which
# is the default and what CI runs. Counting it would report a perfectly healthy
# stack as broken. scripts/compose_health.sh leaves it out of the health suite
# for the same reason. It is still displayed.
$script:OneShotServices = @('migrate', 'seed', 'seed-review')
$script:OptionalServices = @('seed-logins')

# CHECK_IDS — the contract shared with scripts/compose_health.sh. Adding a
# check here and not there (or the reverse) is a failing unit test, which is
# what stops Windows and Linux from quietly checking different things.
$script:CheckIds = @(
    'db-healthy',
    'migrations-at-head',
    'migrate-exited-ok',
    'seed-exited-ok',
    'seed-review-exited-ok',
    'api-health',
    'worker-health',
    'scheduler-heartbeat',
    'frontend-root',
    'frontend-spa-route',
    'frontend-api-proxy'
)

function Write-Info { param([string] $Message) Write-Host $Message }

# Machine-readable output goes straight to stdout rather than onto the
# pipeline. A function that both emits an object and returns a value returns
# BOTH to its caller, so `if (Invoke-HealthCommand ...)` would be testing a
# two-element array — which is always truthy — and the JSON would be swallowed
# by the `if` instead of being printed. Writing to the console stream directly
# keeps the return value the only thing on the pipeline.
function Write-Payload { param([string] $Text) [Console]::Out.WriteLine($Text) }
function Write-Warn { param([string] $Message) Write-Host $Message -ForegroundColor Yellow }
function Stop-WithCode {
    param([int] $Code, [string] $Message)
    Write-Host $Message -ForegroundColor Red
    exit $Code
}

# --- prerequisites ----------------------------------------------------------

function Assert-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Stop-WithCode $script:ExitPrereq "docker is not installed or not on PATH. Run .\setup.ps1 first."
    }
    & docker compose version *> $null
    if ($LASTEXITCODE -ne 0) {
        Stop-WithCode $script:ExitPrereq "docker compose v2 is unavailable. The legacy docker-compose.exe is not a substitute; update Docker Desktop."
    }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        Stop-WithCode $script:ExitPrereq "the Docker daemon is not reachable. Start Docker Desktop and wait for it to report 'Engine running', then retry."
    }
}

function Test-PortInUse {
    param([int] $Port)
    try {
        $connections = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
        return ($null -ne $connections)
    } catch {
        # Get-NetTCPConnection is absent on some editions; fall back to a probe.
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $client.Connect('127.0.0.1', $Port)
            return $true
        } catch {
            return $false
        } finally {
            $client.Dispose()
        }
    }
}

function Test-StackHasContainers {
    $ids = & docker compose ps -aq 2>$null
    return -not [string]::IsNullOrWhiteSpace(($ids -join ''))
}

function Assert-PortsFree {
    # Only meaningful before this stack owns the ports; once it is up they are
    # legitimately busy, and a check that could not tell the difference would
    # make `restart` fail on a healthy machine.
    if (Test-StackHasContainers) { return }

    $busy = @()
    foreach ($port in $script:PublishedPorts.Keys) {
        if (Test-PortInUse -Port ([int] $port)) {
            $busy += "$port (wanted by $($script:PublishedPorts[$port]))"
        }
    }
    if ($busy.Count -gt 0) {
        Write-Warn "These published ports are already held by something else:"
        foreach ($entry in $busy) { Write-Warn "  $entry" }
        Write-Warn ""
        Write-Warn "The most common cause is a native PostgreSQL on 5432 — docker-compose.yml's"
        Write-Warn "header says it outright: pick one database. Stop the other service, or"
        Write-Warn "change the published port in docker-compose.yml and set"
        Write-Warn "SMARTMATCH_DATABASE_URL to match."
        exit $script:ExitPort
    }
}

function Test-Configuration {
    & docker compose config -q
    if ($LASTEXITCODE -ne 0) {
        Stop-WithCode $script:ExitUsage "docker-compose.yml is not valid; the output above names the reference that did not resolve."
    }
    Write-Info "configuration: docker-compose.yml parses and every reference resolves"

    if (Test-Path (Join-Path $script:RepoRoot '.env')) {
        Write-Info "configuration: .env present (left exactly as it is; nothing here writes to it)"
    } else {
        Write-Info "configuration: no .env — the appliance runs on docker-compose.yml's own defaults."
        Write-Info "               Copy .env.example to .env only if you need the pilot logins."
    }
}

# --- HTTP and compose readers ----------------------------------------------

function Invoke-HttpGet {
    param([string] $Url, [string[]] $Headers = @())
    $arguments = @('-s', '-m', "$script:CurlTimeout", '-w', "`n%{http_code}")
    foreach ($header in $Headers) { $arguments += @('-H', $header) }
    $arguments += $Url

    $raw = & curl.exe @arguments 2>$null
    if ($null -eq $raw) { return @{ Code = '000'; Body = '' } }
    $text = ($raw -join "`n")
    $index = $text.LastIndexOf("`n")
    if ($index -lt 0) { return @{ Code = '000'; Body = $text } }
    return @{
        Code = $text.Substring($index + 1).Trim()
        Body = $text.Substring(0, $index)
    }
}

function Get-ComposeField {
    param([string] $Service, [string] $Field)
    $value = & docker compose ps -a --format "{{.$Field}}" $Service 2>$null
    if ($null -eq $value) { return '' }
    return (($value | Select-Object -First 1) -as [string]).Trim()
}

function Get-ExpectedMigrationHead {
    # The revision no other revision names as its down_revision. Both are
    # declared at column zero in db/migrations/versions/, which is what makes
    # this readable without importing alembic — this launcher must work on a
    # machine that has Docker Desktop and nothing else.
    $directory = Join-Path $script:RepoRoot 'db/migrations/versions'
    if (-not (Test-Path $directory)) { return $null }

    $revisions = @()
    $downs = @()
    foreach ($file in Get-ChildItem -Path $directory -Filter '*.py') {
        foreach ($line in Get-Content -LiteralPath $file.FullName) {
            if ($line -match '^revision = "([^"]+)"') { $revisions += $Matches[1] }
            elseif ($line -match '^down_revision = "([^"]+)"') { $downs += $Matches[1] }
        }
    }
    $heads = @($revisions | Where-Object { $downs -notcontains $_ })
    if ($heads.Count -ne 1) { return $null }
    return $heads[0]
}

function Invoke-PsqlScalar {
    param([string] $Sql)
    $value = & docker compose exec -T db psql 'postgresql://smartmatch:smartmatch@localhost:5432/smartmatch' -tAc $Sql 2>$null
    if ($null -eq $value) { return '' }
    return (($value -join '') -replace '\s', '')
}

function ConvertFrom-JsonSafe {
    param([string] $Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    try { return $Text | ConvertFrom-Json } catch { return $null }
}

# --- the checks -------------------------------------------------------------

function New-CheckResult {
    param([string] $Id, [bool] $Ok, [string] $Detail)
    return [pscustomobject] @{ Id = $Id; Status = $(if ($Ok) { 'pass' } else { 'fail' }); Detail = $Detail }
}

function Test-DbHealthy {
    $health = Get-ComposeField -Service 'db' -Field 'Health'
    $state = Get-ComposeField -Service 'db' -Field 'State'
    if ($health -eq 'healthy') {
        return New-CheckResult 'db-healthy' $true 'postgres container reports healthy'
    }
    $stateText = if ($state) { $state } else { 'absent' }
    $healthText = if ($health) { $health } else { 'none' }
    return New-CheckResult 'db-healthy' $false "postgres container state='$stateText' health='$healthText'"
}

function Test-MigrationsAtHead {
    $head = Get-ExpectedMigrationHead
    if (-not $head) {
        return New-CheckResult 'migrations-at-head' $false 'could not resolve a single migration head from db/migrations/versions/'
    }
    $actual = Invoke-PsqlScalar 'select version_num from alembic_version'
    if ($actual -eq $head) {
        return New-CheckResult 'migrations-at-head' $true "alembic_version=$actual"
    }
    $actualText = if ($actual) { $actual } else { 'unreadable' }
    return New-CheckResult 'migrations-at-head' $false "alembic_version='$actualText' but head is '$head'"
}

function Test-OneShotExitedOk {
    param([string] $Id, [string] $Service)
    $state = Get-ComposeField -Service $Service -Field 'State'
    $code = Get-ComposeField -Service $Service -Field 'ExitCode'
    if ($state -eq 'exited' -and $code -eq '0') {
        return New-CheckResult $Id $true "$Service exited 0"
    }
    $stateText = if ($state) { $state } else { 'absent' }
    $codeText = if ($code) { $code } else { 'unknown' }
    return New-CheckResult $Id $false "$Service state='$stateText' exit=$codeText (``docker compose logs $Service`` names the stage)"
}

function Test-ApiHealth {
    $response = Invoke-HttpGet -Url "$script:ApiBase/api/health"
    if ($response.Code -ne '200') {
        return New-CheckResult 'api-health' $false "GET $script:ApiBase/api/health -> $($response.Code)"
    }
    $document = ConvertFrom-JsonSafe $response.Body
    if ($null -eq $document) {
        return New-CheckResult 'api-health' $false "the api health body was not JSON: $($response.Body)"
    }
    if ($document.status -ne 'ok') {
        return New-CheckResult 'api-health' $false "api reported status='$($document.status)'"
    }
    if ($document.release -ne $script:ExpectedRelease) {
        return New-CheckResult 'api-health' $false "api reports release='$($document.release)' but this checkout expects '$script:ExpectedRelease' — the containers are older than the code"
    }
    return New-CheckResult 'api-health' $true "200 status=ok release=$($document.release)"
}

function Test-WorkerHealth {
    $response = Invoke-HttpGet -Url "$script:WorkerBase/health"
    if ($response.Code -ne '200') {
        return New-CheckResult 'worker-health' $false "GET $script:WorkerBase/health -> $($response.Code)"
    }
    $document = ConvertFrom-JsonSafe $response.Body
    if ($null -eq $document -or $document.status -ne 'ok') {
        return New-CheckResult 'worker-health' $false "worker health body was not status=ok: $($response.Body)"
    }
    return New-CheckResult 'worker-health' $true '200 status=ok'
}

function Test-SchedulerHeartbeat {
    # GET /operations/dispatch reports what THIS worker process last completed.
    # In compose the sidecar drives that same process, so a populated, recent
    # last_completed is exactly "the scheduler is still dispatching". It is not
    # the production absence alert — see docs/operations/deploy-runbook.md §J8.
    $response = Invoke-HttpGet -Url "$script:WorkerBase/operations/dispatch"
    if ($response.Code -ne '200') {
        return New-CheckResult 'scheduler-heartbeat' $false "GET $script:WorkerBase/operations/dispatch -> $($response.Code)"
    }
    $document = ConvertFrom-JsonSafe $response.Body
    if ($null -eq $document) {
        return New-CheckResult 'scheduler-heartbeat' $false "the heartbeat body was not JSON: $($response.Body)"
    }
    if (-not $document.configured) {
        return New-CheckResult 'scheduler-heartbeat' $false 'the worker reports configured=false: it cannot dispatch at all'
    }
    if ($null -eq $document.last_completed) {
        return New-CheckResult 'scheduler-heartbeat' $false 'the worker has completed no dispatch pass; the scheduler sidecar is not driving it'
    }
    try {
        $finished = [datetimeoffset]::Parse($document.last_completed.finished_at)
    } catch {
        return New-CheckResult 'scheduler-heartbeat' $false "could not read the heartbeat timestamp '$($document.last_completed.finished_at)'"
    }
    $age = [int] ([datetimeoffset]::UtcNow - $finished).TotalSeconds
    if ($age -le $script:HeartbeatMaxAgeSeconds) {
        return New-CheckResult 'scheduler-heartbeat' $true "last completed pass ${age}s ago"
    }
    return New-CheckResult 'scheduler-heartbeat' $false "the last completed dispatch pass was ${age}s ago (limit $($script:HeartbeatMaxAgeSeconds)s); the scheduler has stopped"
}

function Test-FrontendRoot {
    $response = Invoke-HttpGet -Url "$script:WebBase/"
    if ($response.Code -eq '200') {
        return New-CheckResult 'frontend-root' $true 'GET / -> 200'
    }
    return New-CheckResult 'frontend-root' $false "GET $script:WebBase/ -> $($response.Code) (``docker compose logs web`` shows whether npm ci or vite failed)"
}

function Test-FrontendSpaRoute {
    $response = Invoke-HttpGet -Url "$script:WebBase/coordinator-portal"
    if ($response.Code -eq '200') {
        return New-CheckResult 'frontend-spa-route' $true 'GET /coordinator-portal -> 200'
    }
    return New-CheckResult 'frontend-spa-route' $false "GET $script:WebBase/coordinator-portal -> $($response.Code): the dev server is not serving deep routes"
}

function Test-FrontendApiProxy {
    $response = Invoke-HttpGet -Url "$script:WebBase/v1/me" -Headers @("Authorization: Bearer $script:ApiBearer")
    if ($response.Code -ne '200') {
        return New-CheckResult 'frontend-api-proxy' $false "GET $script:WebBase/v1/me -> $($response.Code): the dev server's /v1 proxy is not reaching the API"
    }
    $document = ConvertFrom-JsonSafe $response.Body
    if ($null -ne $document -and $document.email -eq $script:PilotEmail) {
        return New-CheckResult 'frontend-api-proxy' $true "proxied /v1/me authenticated as $($document.email)"
    }
    $who = if ($null -ne $document) { $document.email } else { 'nobody' }
    return New-CheckResult 'frontend-api-proxy' $false "proxied /v1/me authenticated as '$who', not the seeded principal"
}

function Invoke-HealthChecks {
    return @(
        (Test-DbHealthy),
        (Test-MigrationsAtHead),
        (Test-OneShotExitedOk -Id 'migrate-exited-ok' -Service 'migrate'),
        (Test-OneShotExitedOk -Id 'seed-exited-ok' -Service 'seed'),
        (Test-OneShotExitedOk -Id 'seed-review-exited-ok' -Service 'seed-review'),
        (Test-ApiHealth),
        (Test-WorkerHealth),
        (Test-SchedulerHeartbeat),
        (Test-FrontendRoot),
        (Test-FrontendSpaRoute),
        (Test-FrontendApiProxy)
    )
}

function Invoke-HealthCommand {
    param([bool] $WaitForHealthy, [bool] $AsJson, [int] $TimeoutSeconds)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $attempt = 0
    $results = @()
    $healthy = $false

    while ($true) {
        $attempt++
        $results = Invoke-HealthChecks
        $healthy = -not ($results | Where-Object { $_.Status -ne 'pass' })
        if ($healthy) { break }
        if (-not $WaitForHealthy) { break }
        if ((Get-Date) -ge $deadline) {
            if (-not $AsJson) { Write-Warn "health: gave up after ${TimeoutSeconds}s ($attempt attempts)" }
            break
        }
        if (-not $AsJson) { Write-Warn "health: attempt $attempt incomplete, retrying..." }
        Start-Sleep -Seconds 5
    }

    if ($AsJson) {
        Write-Payload (
            [pscustomobject] @{
                healthy          = [bool] $healthy
                release_expected = $script:ExpectedRelease
                checks           = $results
            } | ConvertTo-Json -Depth 4 -Compress
        )
    } else {
        foreach ($result in $results) {
            $mark = if ($result.Status -eq 'pass') { 'PASS' } else { 'FAIL' }
            Write-Info ("  {0,-4} {1,-22} {2}" -f $mark, $result.Id, $result.Detail)
        }
        if ($healthy) {
            Write-Info "health: all $($results.Count) checks passed"
        } else {
            Write-Info 'health: FAILED'
        }
    }

    return [bool] $healthy
}

# --- commands ---------------------------------------------------------------

function Show-Urls {
    Write-Info ''
    Write-Info 'SmartMatch is up:'
    Write-Info '  frontend   http://127.0.0.1:5173/           <- open this'
    Write-Info '  portal     http://127.0.0.1:5173/coordinator-portal'
    Write-Info '  api        http://127.0.0.1:8080/api/health'
    Write-Info '  worker     http://127.0.0.1:8081/health'
    Write-Info '  database   postgresql://smartmatch:smartmatch@127.0.0.1:5432/smartmatch'
    Write-Info ''
    Write-Info 'The frontend authenticates with the compose-only fixture bearer token.'
    Write-Info 'There is no login and no identity provider — see docker-compose.yml.'
}

function Wait-ForHealthy {
    Write-Info "waiting for the stack to become healthy (up to $($script:ReadyTimeout)s)..."
    Write-Info 'first run is slow: the images build and the web service runs npm ci.'
    if (Invoke-HealthCommand -WaitForHealthy $true -AsJson $false -TimeoutSeconds $script:ReadyTimeout) {
        Show-Urls
        return
    }
    Write-Warn ''
    Write-Warn "The stack did not become healthy within $($script:ReadyTimeout)s."
    Write-Warn ".\smartmatch.ps1 status shows which service is stuck and"
    Write-Warn ".\smartmatch.ps1 logs <service> shows why."
    exit $script:ExitTimeout
}

function Invoke-Start {
    Assert-Docker
    Assert-PortsFree
    Write-Info 'starting the appliance (building images that are missing or stale)...'
    & docker compose up --build -d
    if ($LASTEXITCODE -ne 0) { Stop-WithCode $script:ExitUnhealthy "docker compose up failed; .\smartmatch.ps1 logs has the reason" }
    Wait-ForHealthy
}

function Invoke-Stop {
    Assert-Docker
    Write-Info 'stopping the appliance (data volumes are kept)...'
    & docker compose stop
    if ($LASTEXITCODE -ne 0) { Stop-WithCode $script:ExitUnhealthy 'docker compose stop failed' }
    Write-Info "stopped. .\smartmatch.ps1 start brings it back with the same database."
}

function Invoke-Install {
    param([bool] $WithDeveloperTools)

    Assert-Docker
    Test-Configuration
    Assert-PortsFree

    Write-Info ''
    Write-Info 'building images...'
    & docker compose build
    if ($LASTEXITCODE -ne 0) { Stop-WithCode $script:ExitUnhealthy 'the image build failed' }

    Write-Info 'starting services...'
    & docker compose up -d
    if ($LASTEXITCODE -ne 0) { Stop-WithCode $script:ExitUnhealthy "docker compose up failed; .\smartmatch.ps1 logs has the reason" }

    Wait-ForHealthy

    if ($WithDeveloperTools) { Install-DeveloperToolchain }

    Write-Info 'install complete.'
}

function Install-DeveloperToolchain {
    Write-Info ''
    Write-Info '== developer install =='

    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Stop-WithCode $script:ExitPrereq "python is not installed. .\setup.ps1 -Developer installs Python 3.11."
    }
    $pythonVersion = (& python -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>$null)
    if ($pythonVersion -notin @('3.11', '3.12')) {
        Stop-WithCode $script:ExitPrereq "python is $pythonVersion; pyproject.toml requires >=3.11,<3.13 and everything is verified against 3.11."
    }
    Write-Info "python: $pythonVersion"

    Write-Info 'creating .venv and installing hash-verified dependencies (slow; do not interrupt)...'
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Stop-WithCode $script:ExitPrereq 'python -m venv failed' }

    $pip = Join-Path $script:RepoRoot '.venv\Scripts\pip.exe'
    & $pip install -q --upgrade pip
    if ($LASTEXITCODE -ne 0) { Stop-WithCode $script:ExitUnhealthy 'pip upgrade failed' }
    & $pip install -q --require-hashes -r requirements/dev.txt
    if ($LASTEXITCODE -ne 0) { Stop-WithCode $script:ExitUnhealthy 'the hash-verified dependency install failed' }
    & $pip install -q --no-deps -e python/smartmatch_domain -e python/smartmatch_authz -e python/smartmatch_providers -e python/smartmatch_persistence
    if ($LASTEXITCODE -ne 0) { Stop-WithCode $script:ExitUnhealthy 'the editable workspace install failed' }

    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Stop-WithCode $script:ExitPrereq "node is not installed. .\setup.ps1 -Developer installs Node 22 (the version in .nvmrc)."
    }
    $nodeMajor = [int] (& node -p 'process.versions.node.split(".")[0]')
    if ($nodeMajor -lt 20) {
        Stop-WithCode $script:ExitPrereq "node is v$nodeMajor; the frontend needs >=20 and .nvmrc pins 22."
    }
    Write-Info "node: v$(& node -p 'process.versions.node')"

    Write-Info 'installing frontend dependencies from the lockfile...'
    Push-Location (Join-Path $script:RepoRoot 'apps/web/legacy-frontend')
    try {
        & npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { Stop-WithCode $script:ExitUnhealthy 'npm ci failed in apps/web/legacy-frontend' }
    } finally {
        Pop-Location
    }

    # `make check` is the gate set. Windows has no make by default, so the
    # gates are invoked directly out of the virtualenv rather than pretending
    # a Makefile is portable.
    Write-Info ''
    Write-Info 'running the local gates...'
    $venvBin = Join-Path $script:RepoRoot '.venv\Scripts'
    $domainPath = 'python/smartmatch_domain;python/smartmatch_authz;python/smartmatch_providers;python/smartmatch_persistence'
    $gates = @(
        @{ Name = 'format'; Command = (Join-Path $venvBin 'ruff.exe'); Arguments = @('format', '--check', '.') },
        @{ Name = 'lint'; Command = (Join-Path $venvBin 'ruff.exe'); Arguments = @('check', '.') },
        @{ Name = 'typecheck'; Command = (Join-Path $venvBin 'mypy.exe'); Arguments = @('python/', 'services/') },
        @{ Name = 'tests'; Command = (Join-Path $venvBin 'pytest.exe'); Arguments = @('tests/', '-m', 'not integration and not e2e') },
        @{ Name = 'scan'; Command = (Join-Path $venvBin 'python.exe'); Arguments = @('tools/scan_forbidden.py') },
        @{ Name = 'memory'; Command = (Join-Path $venvBin 'python.exe'); Arguments = @('tools/agent_memory_check.py') },
        @{ Name = 'licenses'; Command = (Join-Path $venvBin 'python.exe'); Arguments = @('tools/supply_chain.py', 'licenses') },
        @{ Name = 'infra-check'; Command = (Join-Path $venvBin 'python.exe'); Arguments = @('tools/env_isolation_check.py') }
    )
    $env:PYTHONPATH = $domainPath
    foreach ($gate in $gates) {
        Write-Info "  gate: $($gate.Name)"
        & $gate.Command @($gate.Arguments)
        if ($LASTEXITCODE -ne 0) {
            Stop-WithCode $script:ExitUnhealthy "gate '$($gate.Name)' failed — the toolchain installed, but the tree does not pass its own gates."
        }
    }
    Write-Info 'developer install complete.'
}

function Invoke-Status {
    param([bool] $AsJson)
    Assert-Docker

    $rows = @()
    $ok = $true
    foreach ($service in $script:ComposeServices) {
        $state = Get-ComposeField -Service $service -Field 'State'
        $health = Get-ComposeField -Service $service -Field 'Health'
        $code = Get-ComposeField -Service $service -Field 'ExitCode'
        if (-not $state) { $state = 'absent' }

        # A one-shot that exited 0 is correct, not down. Conflating the two is
        # how a status display teaches people to ignore it.
        if ($script:OptionalServices -contains $service) {
            # Reported, never counted. See $script:OneShotServices above.
        } elseif ($script:OneShotServices -contains $service) {
            if ($state -ne 'exited' -or $code -ne '0') { $ok = $false }
        } elseif ($state -ne 'running') {
            $ok = $false
        }

        $rows += [pscustomobject] @{
            service   = $service
            state     = $state
            health    = $(if ($health) { $health } else { 'none' })
            exit_code = $(if ($code) { $code } else { $null })
        }
    }

    if ($AsJson) {
        Write-Payload ([pscustomobject] @{ services = $rows; ok = $ok } | ConvertTo-Json -Depth 4 -Compress)
    } else {
        foreach ($row in $rows) {
            Write-Info ("  {0,-12} state={1,-10} health={2,-10} exit={3}" -f $row.service, $row.state, $row.health, $(if ($null -ne $row.exit_code) { $row.exit_code } else { '-' }))
        }
        if ($ok) { Write-Info 'all services are in their expected state.' }
        else { Write-Info 'at least one service is not in its expected state.' }
    }

    if (-not $ok) { exit $script:ExitUnhealthy }
}

function Invoke-Verify {
    param([bool] $FullPath)
    Assert-Docker
    Test-Configuration

    Write-Info ''
    Write-Info '== health =='
    if (-not (Invoke-HealthCommand -WaitForHealthy $false -AsJson $false -TimeoutSeconds 0)) {
        Stop-WithCode $script:ExitUnhealthy 'the health suite failed; the stack is not serving correctly.'
    }

    if ($FullPath) {
        Write-Info ''
        Write-Info '== full smoke path (this WRITES to the appliance database) =='
        # scripts/compose_smoke.sh is bash. Git for Windows ships one, and
        # setup.ps1 installs Git, so this is available on a machine set up the
        # documented way — but it is stated rather than assumed.
        $bash = Get-Command bash -ErrorAction SilentlyContinue
        if (-not $bash) {
            Stop-WithCode $script:ExitPrereq "verify -Full needs bash to run scripts/compose_smoke.sh. Git for Windows provides one; run .\setup.ps1, or run the script from WSL."
        }
        & $bash.Source 'scripts/compose_smoke.sh'
        if ($LASTEXITCODE -ne 0) { Stop-WithCode $script:ExitUnhealthy 'the end-to-end smoke path failed.' }
    } else {
        Write-Info ''
        Write-Info "verify passed. 'verify -Full' additionally runs scripts/compose_smoke.sh,"
        Write-Info 'which imports, dispatches, reviews, and asserts the metrics move — and'
        Write-Info 'which writes to the appliance database, unlike everything above.'
    }
}

function Invoke-Logs {
    param([string] $Service, [bool] $FollowLogs)
    Assert-Docker

    $arguments = @('compose', 'logs', '--no-color', '--tail', '200')
    if ($FollowLogs) { $arguments += '--follow' }
    if ($Service) {
        if ($script:ComposeServices -notcontains $Service) {
            Stop-WithCode $script:ExitUsage "logs: '$Service' is not a service in this stack. Known: $($script:ComposeServices -join ', ')"
        }
        $arguments += $Service
    }
    & docker @arguments
}

function Show-Usage {
    Write-Info @'
SmartMatch launcher (Windows PowerShell)

  .\smartmatch.ps1 install [-Developer]  Validate, build, start, wait for health, print URLs.
  .\smartmatch.ps1 start                 Bring the stack up.
  .\smartmatch.ps1 stop                  Stop the stack, KEEPING the data volumes.
  .\smartmatch.ps1 restart               stop then start.
  .\smartmatch.ps1 status [-Json]        Per-service state and health.
  .\smartmatch.ps1 health [-Wait]        The bounded health suite. Non-mutating.
  .\smartmatch.ps1 verify [-Full]        health, plus (-Full) the end-to-end smoke path.
  .\smartmatch.ps1 logs [service] [-Follow]

Exit codes: 0 ok, 1 unhealthy, 2 usage, 3 missing prerequisite,
            4 port collision, 5 timed out.
'@
}

# --- dispatch ---------------------------------------------------------------

if ($Rest -and $Rest.Count -gt 0) {
    # Remaining arguments are only meaningful for `logs <service>`; anything
    # else is a typo, and silently ignoring it is how a wrong flag becomes a
    # confident, wrong answer.
    if ($Command -ne 'logs') {
        Write-Warn "unexpected argument(s): $($Rest -join ' ')"
        Show-Usage
        exit $script:ExitUsage
    }
}

if ($Timeout -gt 0) { $script:ReadyTimeout = $Timeout }

switch ($Command) {
    'install' { Invoke-Install -WithDeveloperTools ([bool] $Developer); break }
    'start'   { Invoke-Start; break }
    'stop'    { Invoke-Stop; break }
    'restart' { Invoke-Stop; Invoke-Start; break }
    'status'  { Invoke-Status -AsJson ([bool] $Json); break }
    'health'  {
        $timeoutSeconds = if ($Timeout -gt 0) { $Timeout } else { 600 }
        if (-not (Invoke-HealthCommand -WaitForHealthy ([bool] $Wait) -AsJson ([bool] $Json) -TimeoutSeconds $timeoutSeconds)) {
            exit $script:ExitUnhealthy
        }
        break
    }
    'verify'  { Invoke-Verify -FullPath ([bool] $Full); break }
    'logs'    {
        $service = if ($Rest -and $Rest.Count -gt 0) { $Rest[0] } else { '' }
        Invoke-Logs -Service $service -FollowLogs ([bool] $Follow)
        break
    }
    { $_ -in @('help', '-h', '--help', '') } { Show-Usage; if ($Command -eq '') { exit $script:ExitUsage }; break }
    default {
        Write-Warn "unknown command: $Command"
        Show-Usage
        exit $script:ExitUsage
    }
}

exit $script:ExitOk
