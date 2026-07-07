$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # speed up Invoke-WebRequest
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location -Path $PSScriptRoot

function Find-Python {
    # Skip WindowsApps (Microsoft Store alias stub) - unreliable, may hang on Store popup.
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notlike '*\WindowsApps\*') {
        try { $v = & $cmd.Source --version 2>$null; if ($LASTEXITCODE -eq 0 -and $v -match 'Python 3') { return $cmd.Source } } catch {}
    }
    foreach ($v in 'Python313','Python312','Python311') {
        $p = Join-Path $env:LOCALAPPDATA "Programs\Python\$v\python.exe"
        if (Test-Path $p) {
            try { $vv = & $p --version 2>$null; if ($LASTEXITCODE -eq 0 -and $vv -match 'Python 3') { return $p } } catch {}
        }
    }
    return $null
}

# 0. Edge check (soft warning)
$edge = @(
    'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    'C:\Program Files\Microsoft\Edge\Application\msedge.exe'
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) {
    Write-Warning 'Microsoft Edge not found. The script launches Edge; install it from https://www.microsoft.com/edge first.'
}

# 1+2. Python + venv (skip entirely if .venv already exists)
if (Test-Path '.venv\Scripts\python.exe') {
    Write-Host '[1/4] .venv already exists, skip Python install' -ForegroundColor Green
} else {
    $py = Find-Python
    if (-not $py) {
        Write-Host '[1/4] Python not found. Downloading Python 3.12.7 ...' -ForegroundColor Cyan
        $installer = Join-Path $env:TEMP 'python-3.12.7-amd64.exe'
        $urls = @(
            'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe',
            'https://mirrors.huaweicloud.com/python/3.12.7/python-3.12.7-amd64.exe'
        )
        $ok = $false
        foreach ($u in $urls) {
            try {
                Write-Host "  trying $u"
                Invoke-WebRequest -Uri $u -OutFile $installer -UseBasicParsing
                $ok = $true; break
            } catch {
                Write-Host '  failed, trying next mirror...' -ForegroundColor Yellow
            }
        }
        if (-not $ok) { throw 'Failed to download Python. Please install Python 3.12 manually, then re-run setup.' }
        Write-Host '[1/4] Installing Python silently (current user, no admin needed) ...'
        Start-Process -FilePath $installer -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=1','Include_pip=1' -Wait
        $py = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
        if (-not (Test-Path $py)) { throw "Python installed but python.exe not found at $py" }
    }
    Write-Host "[1/4] Python ready: $py" -ForegroundColor Green
    Write-Host '[2/4] Creating virtualenv .venv ...'
    & $py -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
}

# 3. dependencies
Write-Host '[3/4] Installing dependencies (Tsinghua mirror for speed) ...'
& '.venv\Scripts\python.exe' -m pip install -U pip -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed' }
& '.venv\Scripts\python.exe' -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) { throw 'dependency install failed' }

# 4. done
Write-Host '[4/4] Environment installed successfully.' -ForegroundColor Green
