[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$pythonCommand = $null
$pythonPrefix = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCommand = (Get-Command py).Path
    $pythonPrefix = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = (Get-Command python).Path
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonCommand = (Get-Command python3).Path
} else {
    throw "Python 3.9 or newer is required."
}

& $pythonCommand @pythonPrefix -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.9 or newer is required."
}

$sourceDir = Join-Path $PSScriptRoot "plugins\codex-sync\skills\codex-sync"
$codexHome = if ($env:CODEX_HOME) {
    $env:CODEX_HOME
} else {
    if (-not $HOME) {
        throw "HOME is not set and CODEX_HOME was not provided."
    }
    Join-Path $HOME ".codex"
}
if (-not [System.IO.Path]::IsPathRooted($codexHome)) {
    throw "CODEX_HOME must be an absolute path when set."
}
$skillsDir = Join-Path $codexHome "skills"
$destination = Join-Path $skillsDir "codex-sync"

if (-not (Test-Path -LiteralPath (Join-Path $sourceDir "SKILL.md") -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $sourceDir "scripts\codex_sync.py") -PathType Leaf)) {
    throw "Codex Sync Skill files are missing from $sourceDir."
}

New-Item -ItemType Directory -Path $skillsDir -Force | Out-Null

if (Test-Path -LiteralPath $destination) {
    $item = Get-Item -LiteralPath $destination -Force
    if (-not $item.PSIsContainer -or
        (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "Refusing to replace non-directory or reparse-point target $destination."
    }
}

function Get-TreeManifest([string]$Root) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        return ""
    }
    $separators = [char[]]@('\', '/')
    $prefixLength = ([System.IO.Path]::GetFullPath($Root)).TrimEnd($separators).Length
    $lines = Get-ChildItem -LiteralPath $Root -Recurse -File -Force |
        Sort-Object FullName |
        ForEach-Object {
            $relative = $_.FullName.Substring($prefixLength).TrimStart($separators)
            $stream = [System.IO.File]::OpenRead($_.FullName)
            try {
                $sha256 = [System.Security.Cryptography.SHA256]::Create()
                try {
                    $hashBytes = $sha256.ComputeHash($stream)
                    $hash = ([System.BitConverter]::ToString($hashBytes)).Replace("-", "")
                } finally {
                    $sha256.Dispose()
                }
            } finally {
                $stream.Dispose()
            }
            "$relative`t$hash"
        }
    return ($lines -join "`n")
}

if ((Test-Path -LiteralPath $destination -PathType Container) -and
    (Get-TreeManifest $sourceDir) -ceq (Get-TreeManifest $destination)) {
    Write-Output "Codex Sync Skill is already current at $destination"
    exit 0
}

$stageDir = Join-Path $skillsDir (".codex-sync-install-" + [guid]::NewGuid().ToString("N"))
$stagePackage = Join-Path $stageDir "codex-sync"
$backup = $null

try {
    New-Item -ItemType Directory -Path $stagePackage -Force | Out-Null
    Get-ChildItem -LiteralPath $sourceDir -Force |
        Copy-Item -Destination $stagePackage -Recurse -Force

    $runtime = Join-Path $stagePackage "scripts\codex_sync.py"
    & $pythonCommand @pythonPrefix $runtime --help | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Staged runtime failed its self-check; the existing installation was not changed."
    }

    if (Test-Path -LiteralPath $destination -PathType Container) {
        $stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
        $backup = Join-Path $skillsDir (".codex-sync-backup-$stamp-" + $PID)
        Move-Item -LiteralPath $destination -Destination $backup
    }

    try {
        Move-Item -LiteralPath $stagePackage -Destination $destination
    } catch {
        if ($backup -and (Test-Path -LiteralPath $backup) -and
            -not (Test-Path -LiteralPath $destination)) {
            Move-Item -LiteralPath $backup -Destination $destination
        }
        throw
    }

    Write-Output "Installed Codex Sync Skill at $destination"
    if ($backup) {
        Write-Output "Previous installation preserved at $backup"
    }
    Write-Output "Restart Codex if the Skill does not appear immediately."
} finally {
    if (Test-Path -LiteralPath $stageDir) {
        Remove-Item -LiteralPath $stageDir -Recurse -Force
    }
}
