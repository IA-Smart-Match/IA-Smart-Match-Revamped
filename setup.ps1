<#
.SYNOPSIS
    First-time prerequisite setup for Windows.

.DESCRIPTION
    Run this once on a new machine, then use .\smartmatch.ps1 for everything
    else. It installs through winget — the package manager that ships with
    Windows 10 21H2 and later — and validates whatever is already installed, so
    it is safe to re-run: a second run should install nothing.

    Without -Developer it installs Git and Docker Desktop. With -Developer it
    additionally validates Python 3.11 and Node 22, which are only needed to run
    the gates on the host; the appliance itself needs neither, because Docker
    Compose is this project's runtime dependency installer.

    What it deliberately does not do:

      * It never writes .env. If one exists it is left untouched; if none
        exists it stays absent, because docker-compose.yml runs on its own
        defaults and an .env is only needed for the optional pilot logins.
        Overwriting one would destroy the single file that is never in version
        control and never recoverable.
      * It installs no application dependency. PostgreSQL 16, the Python
        service dependencies, the migrations, the seed data, the scheduler, and
        the frontend's npm ci all happen inside containers.
      * It provisions nothing outside this machine.

    Docker Desktop's installation requires a reboot before the engine runs, and
    winget-installed tools are not on PATH in an already-open terminal. Both are
    reported at the end rather than papered over, because the failures they
    cause look like a broken install.

.PARAMETER Developer
    Also set up the host toolchain: Python 3.11 and Node 22.

.PARAMETER Check
    Validate only. Installs nothing and exits nonzero if a prerequisite is
    missing.

.EXAMPLE
    .\setup.ps1
    .\setup.ps1 -Developer
    .\setup.ps1 -Check
#>

[CmdletBinding()]
param(
    [switch] $Developer,
    [switch] $Check
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:Missing = New-Object System.Collections.Generic.List[string]
$script:Notes = New-Object System.Collections.Generic.List[string]

$script:NodeMajor = 22       # .nvmrc
$script:PythonSeries = '3.11' # .python-version, and both container images

function Write-Info { param([string] $Message) Write-Host $Message }
function Write-Warn { param([string] $Message) Write-Host $Message -ForegroundColor Yellow }
function Add-Note { param([string] $Message) $script:Notes.Add($Message) | Out-Null }
function Add-Missing { param([string] $Message) $script:Missing.Add($Message) | Out-Null }

function Test-Command {
    param([string] $Name)
    return [bool] (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Assert-Winget {
    if (Test-Command 'winget') { return $true }
    Add-Note 'winget is not available. It ships with Windows 10 21H2 and later as "App Installer"; install it from the Microsoft Store, or install Git and Docker Desktop by hand and re-run with -Check.'
    return $false
}

function Test-WingetPackageInstalled {
    param([string] $Id)
    # `winget list --id X --exact` writes a "No installed package found"
    # message and exits nonzero when the package is absent. Both are checked:
    # the exit code alone is not reliable across winget versions.
    $output = & winget list --id $Id --exact --accept-source-agreements 2>&1 | Out-String
    return ($LASTEXITCODE -eq 0 -and $output -match [regex]::Escape($Id))
}

function Install-WingetPackage {
    param([string] $Id, [string] $Label)

    # winget is checked BEFORE anything invokes it. Test-WingetPackageInstalled
    # runs `winget list`, and with $ErrorActionPreference = 'Stop' a machine
    # without winget would die there with a CommandNotFoundException instead of
    # getting the guidance Assert-Winget exists to give.
    if (-not (Assert-Winget)) {
        Add-Missing "$Label (winget id $Id)"
        return $false
    }
    if (Test-WingetPackageInstalled -Id $Id) {
        Write-Info "$Label`: already installed (winget id $Id)"
        return $true
    }
    if ($Check) {
        Add-Missing "$Label (winget id $Id)"
        return $false
    }

    Write-Info "installing $Label via winget..."
    # Routed to the host rather than left on the pipeline: this function
    # returns a boolean, and winget's progress output would otherwise be
    # returned alongside it and make `if (Install-WingetPackage ...)` test an
    # array instead of the result.
    & winget install --id $Id --exact --silent `
        --accept-package-agreements --accept-source-agreements 2>&1 |
        ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        Add-Missing "$Label (winget install exited $LASTEXITCODE)"
        return $false
    }
    Add-Note "$Label was just installed. A winget-installed tool is not on PATH in an already-open terminal — open a NEW PowerShell window before running .\smartmatch.ps1."
    return $true
}

# --- validators -------------------------------------------------------------

function Initialize-Git {
    if (Test-Command 'git') {
        Write-Info "git: $(& git --version)"
        return
    }
    if ($Check) { Add-Missing 'git'; return }
    [void] (Install-WingetPackage -Id 'Git.Git' -Label 'Git')
}

function Initialize-DockerDesktop {
    if (Test-Command 'docker') {
        Write-Info "docker: $(& docker --version)"

        & docker compose version *> $null
        if ($LASTEXITCODE -ne 0) {
            Add-Missing 'docker compose v2 plugin — update Docker Desktop; the legacy docker-compose.exe is not a substitute'
        } else {
            Write-Info "compose: $(& docker compose version --short)"
        }

        & docker info *> $null
        if ($LASTEXITCODE -ne 0) {
            Add-Note 'Docker Desktop is installed but the engine is not running. Start Docker Desktop and wait for it to report "Engine running" before .\smartmatch.ps1 install.'
        } else {
            Write-Info 'docker daemon: reachable'
        }
        return
    }

    if ($Check) { Add-Missing 'Docker Desktop'; return }

    if (Install-WingetPackage -Id 'Docker.DockerDesktop' -Label 'Docker Desktop') {
        Add-Note 'RESTART REQUIRED: Docker Desktop needs a reboot (and WSL 2 or Hyper-V enabled) before its engine will start. Reboot, launch Docker Desktop once, wait for "Engine running", then run .\smartmatch.ps1 install.'
    }
}

function Initialize-Python {
    if (Test-Command 'python') {
        $version = (& python -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>$null)
        if ($version -in @('3.11', '3.12')) {
            Write-Info "python: $version"
            return
        }
        Add-Note "python is $version; pyproject.toml requires >=3.11,<3.13, so 3.13 does not work. Installing Python $script:PythonSeries alongside it."
    }
    if ($Check) { Add-Missing "Python $script:PythonSeries"; return }
    [void] (Install-WingetPackage -Id "Python.Python.$script:PythonSeries" -Label "Python $script:PythonSeries")
}

function Initialize-Node {
    if (Test-Command 'node') {
        $major = [int] (& node -p 'process.versions.node.split(".")[0]')
        if ($major -ge 20) {
            Write-Info "node: v$(& node -p 'process.versions.node')"
            return
        }
        Add-Note "node is v$major; .nvmrc pins $script:NodeMajor and the frontend needs >=20. Installing Node $script:NodeMajor."
    }
    if ($Check) { Add-Missing "Node >= 20 (.nvmrc pins $script:NodeMajor)"; return }
    [void] (Install-WingetPackage -Id "OpenJS.NodeJS.LTS" -Label "Node.js LTS")
}

function Show-EnvFileState {
    if (Test-Path (Join-Path $script:RepoRoot '.env')) {
        Write-Info '.env: present — left exactly as it is. Nothing in this script writes to it.'
    } else {
        Write-Info '.env: absent, which is fine. docker-compose.yml runs on its own defaults.'
        Write-Info '      Copy .env.example to .env only if you want the optional pilot logins.'
    }
}

# --- run --------------------------------------------------------------------

Write-Info 'SmartMatch prerequisite setup (Windows)'
Write-Info "repository: $script:RepoRoot"
if ($Check) {
    Write-Info 'mode: -Check (validating only; nothing will be installed)'
} elseif ($Developer) {
    Write-Info 'mode: -Developer (appliance prerequisites plus the host toolchain)'
} else {
    Write-Info 'mode: appliance prerequisites only'
}
Write-Info ''

Initialize-Git
Initialize-DockerDesktop

if ($Developer) {
    Write-Info ''
    Write-Info '-- developer toolchain --'
    Initialize-Python
    Initialize-Node
}

Write-Info ''
Show-EnvFileState

if ($script:Notes.Count -gt 0) {
    Write-Info ''
    Write-Info '== read these =='
    foreach ($entry in $script:Notes) { Write-Warn "  * $entry" }
}

if ($script:Missing.Count -gt 0) {
    Write-Info ''
    Write-Warn 'missing prerequisites:'
    foreach ($entry in $script:Missing) { Write-Warn "  - $entry" }
    exit 1
}

Write-Info ''
if ($Check) {
    Write-Info 'every prerequisite is present.'
} else {
    Write-Info 'setup complete. Next:'
    Write-Info '  .\smartmatch.ps1 install              start the appliance'
    Write-Info '  .\smartmatch.ps1 install -Developer   ...and install the host toolchain'
}
exit 0
