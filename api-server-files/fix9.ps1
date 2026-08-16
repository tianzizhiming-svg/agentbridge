# AgentBridge Fix9 - Copy updated openapi.json + catalog.json to server
# GitHub files have 99 assets, server still serves old 94-asset versions
# Usage:
#   irm "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files/fix9.ps1" -OutFile "$env:TEMP\fix9.ps1"
#   powershell -ExecutionPolicy Bypass -File "$env:TEMP\fix9.ps1"

param([string]$ApiPath = "F:\afie_proxy")

Write-Host "=== AgentBridge Fix9 (Update API files) ===" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Download fresh openapi.json and catalog.json ---
Write-Host "[1/3] Downloading fresh API files..." -ForegroundColor Yellow

$baseUrl = "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files"
$tmpDir = Join-Path $env:TEMP "ab_fix9"
if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null

$files = @("openapi.json", "catalog.json", "llms.txt")
foreach ($f in $files) {
    $url = "$baseUrl/$f?v=$(Get-Random)"
    $dest = Join-Path $tmpDir $f
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
        $sz = (Get-Item $dest).Length
        Write-Host "  [OK] $f ($sz bytes)" -ForegroundColor Green
    } catch {
        Write-Host "  [FAIL] $f : $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""

# --- Step 2: Copy to correct locations ---
Write-Host "[2/3] Copying files to server..." -ForegroundColor Yellow

# openapi.json -> root + docs/
$srcOpenapi = Join-Path $tmpDir "openapi.json"
$dstOpenapi1 = Join-Path $ApiPath "openapi.json"
$dstOpenapi2 = Join-Path $ApiPath "docs\openapi.json"

# Backup existing
if (Test-Path $dstOpenapi1) { Copy-Item $dstOpenapi1 "$dstOpenapi1.bak-fix9" -Force }
if (Test-Path $dstOpenapi2) { Copy-Item $dstOpenapi2 "$dstOpenapi2.bak-fix9" -Force }

Copy-Item $srcOpenapi $dstOpenapi1 -Force
Write-Host "  [OK] openapi.json -> root" -ForegroundColor Green

$docsDir = Join-Path $ApiPath "docs"
if (-not (Test-Path $docsDir)) { New-Item -ItemType Directory -Path $docsDir -Force | Out-Null }
Copy-Item $srcOpenapi $dstOpenapi2 -Force
Write-Host "  [OK] openapi.json -> docs\" -ForegroundColor Green

# catalog.json -> root + data/
$srcCatalog = Join-Path $tmpDir "catalog.json"
$dstCatalog1 = Join-Path $ApiPath "catalog.json"
$dstCatalog2 = Join-Path $ApiPath "data\catalog.json"

if (Test-Path $dstCatalog1) { Copy-Item $dstCatalog1 "$dstCatalog1.bak-fix9" -Force }
if (Test-Path $dstCatalog2) { Copy-Item $dstCatalog2 "$dstCatalog2.bak-fix9" -Force }

Copy-Item $srcCatalog $dstCatalog1 -Force
Write-Host "  [OK] catalog.json -> root" -ForegroundColor Green

$dataDir = Join-Path $ApiPath "data"
if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir -Force | Out-Null }
Copy-Item $srcCatalog $dstCatalog2 -Force
Write-Host "  [OK] catalog.json -> data\" -ForegroundColor Green

# llms.txt -> root
$srcLlms = Join-Path $tmpDir "llms.txt"
$dstLlms = Join-Path $ApiPath "llms.txt"
if (Test-Path $dstLlms) { Copy-Item $dstLlms "$dstLlms.bak-fix9" -Force }
Copy-Item $srcLlms $dstLlms -Force
Write-Host "  [OK] llms.txt -> root" -ForegroundColor Green

Write-Host ""

# --- Step 3: Restart and verify ---
Write-Host "[3/3] Restarting service..." -ForegroundColor Yellow

& nssm stop AgentBridge 2>$null
Start-Sleep -Seconds 3
& nssm start AgentBridge 2>$null

$maxWait = 30
$waited = 0
$ready = $false

while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 2
    $waited += 2
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 5
        if ($r.StatusCode -eq 200) {
            $ready = $true
            Write-Host "  [OK] Service ready after ${waited}s" -ForegroundColor Green
            break
        }
    } catch {
        Write-Host "  Waiting... (${waited}s)" -ForegroundColor DarkGray
    }
}

if ($ready) {
    Write-Host ""
    Write-Host "=== Verification ===" -ForegroundColor Cyan

    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/llms.txt" -UseBasicParsing -TimeoutSec 10
        $lc = ($r.Content -split "`n").Count
        Write-Host "  [OK] /llms.txt: $lc lines" -ForegroundColor Green
    } catch { Write-Host "  [WARN] /llms.txt failed" -ForegroundColor DarkYellow }

    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/openapi.json" -UseBasicParsing -TimeoutSec 10
        $spec = $r.Content | ConvertFrom-Json
        $ec = $spec.paths."/v1/assets/{asset_id}".get.parameters[0].schema.enum.Count
        Write-Host "  [OK] /openapi.json: $ec assets in enum" -ForegroundColor Green
    } catch { Write-Host "  [WARN] /openapi.json failed" -ForegroundColor DarkYellow }

    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/catalog.json" -UseBasicParsing -TimeoutSec 10
        $cat = $r.Content | ConvertFrom-Json
        Write-Host "  [OK] /catalog.json: $($cat.assets.Count) assets" -ForegroundColor Green
    } catch { Write-Host "  [WARN] /catalog.json failed" -ForegroundColor DarkYellow }

    $guideIds = @(
        "guide-working-in-china-2026-08",
        "guide-hiring-china-2026-08",
        "guide-legal-rights-china-2026-08",
        "guide-study-in-china-2026-08",
        "guide-business-compliance-china-2026-08"
    )
    foreach ($gid in $guideIds) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:8000/v1/assets/$gid" -UseBasicParsing -TimeoutSec 10
            Write-Host "  [OK] /v1/assets/$gid : $($r.StatusCode)" -ForegroundColor Green
        } catch {
            $sc = 0
            if ($_.Exception.Response) { $sc = [int]$_.Exception.Response.StatusCode }
            if ($sc -eq 402) {
                Write-Host "  [OK] /v1/assets/$gid : 402 (exists!)" -ForegroundColor Green
            } else {
                Write-Host "  [WARN] /v1/assets/$gid" -ForegroundColor DarkYellow
            }
        }
    }
} else {
    Write-Host "  [FAIL] Service not responding" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
