# AgentBridge Fix2 - Add 5 guides to products.json + restart service
# ASCII-only PowerShell script (no Unicode in code, data comes from JSON file)
# Usage:
#   irm "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files/fix2.ps1?v=$(Get-Random)" -OutFile "$env:TEMP\fix2.ps1"
#   powershell -ExecutionPolicy Bypass -File "$env:TEMP\fix2.ps1"

param([string]$ApiPath = "F:\afie_proxy")

Write-Host "=== AgentBridge Fix2 ===" -ForegroundColor Cyan
Write-Host "API path: $ApiPath"
Write-Host ""

# --- Step 1: Download new-guides.json from GitHub ---
Write-Host "[1/4] Downloading new-guides.json..." -ForegroundColor Yellow

$baseUrl = "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files"
$guidesUrl = "$baseUrl/new-guides.json?v=$(Get-Random)"
$guidesTmp = Join-Path $env:TEMP "new-guides.json"

try {
    Invoke-WebRequest -Uri $guidesUrl -OutFile $guidesTmp -UseBasicParsing
    $guidesJson = Get-Content $guidesTmp -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Host "  [OK] Downloaded $($guidesJson.Count) guide entries" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Could not download new-guides.json: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host ""

# --- Step 2: Add guides to products.json ---
Write-Host "[2/4] Adding guides to products.json..." -ForegroundColor Yellow

# Try products.json first, then products-verified.json
$productsPath = Join-Path $ApiPath "data\products.json"
if (-not (Test-Path $productsPath)) {
    $altPath = Join-Path $ApiPath "data\products-verified.json"
    if (Test-Path $altPath) {
        $productsPath = $altPath
        Write-Host "  Using products-verified.json" -ForegroundColor DarkYellow
    } else {
        Write-Host "  [FAIL] No products JSON found in data\" -ForegroundColor Red
        $dataDir = Join-Path $ApiPath "data"
        if (Test-Path $dataDir) {
            Write-Host "  Files in data\:" -ForegroundColor DarkGray
            Get-ChildItem $dataDir -Filter "*.json" | ForEach-Object { Write-Host "    $($_.Name)" }
        }
        exit 1
    }
}

Write-Host "  Target: $productsPath" -ForegroundColor DarkGray

# Backup
$backupPath = $productsPath + ".bak-" + (Get-Date -Format 'yyyyMMdd-HHmmss')
Copy-Item $productsPath $backupPath -Force
Write-Host "  [OK] Backup saved" -ForegroundColor Green

# Parse existing JSON
$rawJson = Get-Content $productsPath -Raw -Encoding UTF8
$json = $rawJson | ConvertFrom-Json

# Check if already exists
$existing = $json.products | Where-Object { $_.id -eq "guide-working-in-china-2026-08" }
if ($existing) {
    Write-Host "  [OK] Guides already in products.json (skipping)" -ForegroundColor Green
} else {
    # Add each guide
    foreach ($guide in $guidesJson) {
        $json.products += $guide
        Write-Host "  Added: $($guide.id)" -ForegroundColor DarkGray
    }

    # Update total
    if ($json.total_products) {
        $json.total_products = $json.products.Count
    }

    # Write back
    $output = $json | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($productsPath, $output, [System.Text.UTF8Encoding]::new($false))

    Write-Host "  [OK] Added $($guidesJson.Count) guides to products.json" -ForegroundColor Green
    Write-Host "  Total products: $($json.products.Count)" -ForegroundColor DarkGray
}

Write-Host ""

# --- Step 3: Find and restart service ---
Write-Host "[3/4] Finding service name..." -ForegroundColor Yellow

$serviceName = ""
$serviceFound = $false

# Method 1: nssm list
try {
    $nssmOutput = & nssm list 2>$null
    foreach ($line in $nssmOutput) {
        $l = $line.ToString().Trim()
        if ($l -and $l -ne "SUCCESS" -and $l.Length -gt 1) {
            if ($l -match 'agent|bridge|afie|api|proxy|uvicorn|fastapi') {
                $serviceName = $l
                Write-Host "  Found (nssm): $l" -ForegroundColor DarkGray
                break
            }
        }
    }
} catch {}

# Method 2: sc.exe query
if (-not $serviceName) {
    $scOutput = & sc.exe query type= service state= all 2>$null
    foreach ($line in $scOutput) {
        $l = $line.ToString().Trim()
        if ($l -match "SERVICE_NAME:\s*(.+)") {
            $sname = $Matches[1].Trim()
            if ($sname -match 'agent|bridge|afie|api|proxy|uvicorn|fastapi|python') {
                $serviceName = $sname
                Write-Host "  Found (sc.exe): $sname" -ForegroundColor DarkGray
                break
            }
        }
    }
}

# Method 3: Get-Service
if (-not $serviceName) {
    $svcs = Get-Service | Where-Object { $_.Name -match 'agent|bridge|afie|api|proxy|uvicorn|fastapi|python' }
    foreach ($svc in $svcs) {
        $serviceName = $svc.Name
        Write-Host "  Found (Get-Service): $($svc.Name)" -ForegroundColor DarkGray
        break
    }
}

# Method 4: common names
if (-not $serviceName) {
    $names = @("afie_proxy","afie-proxy","afie","AgentBridge","agentbridge","AgentBridgeAPI","AgentBridge-API","agentbridge-api","api-server","apiserver")
    foreach ($n in $names) {
        $test = & sc.exe query $n 2>$null
        if ($test -match "SERVICE_NAME" -or $test -match "STATE") {
            $serviceName = $n
            Write-Host "  Found (common): $n" -ForegroundColor DarkGray
            break
        }
    }
}

if ($serviceName) {
    Write-Host "  Service: $serviceName" -ForegroundColor Green
    Write-Host "  Restarting..." -ForegroundColor Yellow
    try {
        & nssm restart $serviceName 2>$null
        Write-Host "  [OK] Restarted via nssm" -ForegroundColor Green
        $serviceFound = $true
    } catch {
        try {
            & sc.exe stop $serviceName 2>$null
            Start-Sleep -Seconds 3
            & sc.exe start $serviceName 2>$null
            Write-Host "  [OK] Restarted via sc.exe" -ForegroundColor Green
            $serviceFound = $true
        } catch {
            Write-Host "  [FAIL] Could not restart" -ForegroundColor Red
        }
    }
} else {
    Write-Host "  [WARN] Service not found. All services:" -ForegroundColor DarkYellow
    $allSvc = & sc.exe query type= service state= all 2>$null
    foreach ($line in $allSvc) {
        $l = $line.ToString().Trim()
        if ($l -match "SERVICE_NAME:\s*(.+)") {
            Write-Host "    $($Matches[1].Trim())" -ForegroundColor DarkGray
        }
    }
}

Write-Host ""

# --- Step 4: Verify ---
Write-Host "[4/4] Verifying..." -ForegroundColor Yellow
Start-Sleep -Seconds 4

$apiBase = "http://localhost:8000"

# products.json
try {
    $pf = Get-Content $productsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $gc = ($pf.products | Where-Object { $_.id -match "^guide-" }).Count
    Write-Host "  [OK] products.json: $($pf.products.Count) total, $gc guides" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] products.json check failed" -ForegroundColor DarkYellow
}

# /health
try {
    $r = Invoke-WebRequest -Uri "$apiBase/health" -UseBasicParsing -TimeoutSec 10
    Write-Host "  [OK] /health: $($r.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] /health failed" -ForegroundColor DarkYellow
}

# /llms.txt
try {
    $r = Invoke-WebRequest -Uri "$apiBase/llms.txt" -UseBasicParsing -TimeoutSec 10
    $lc = ($r.Content -split "`n").Count
    Write-Host "  [OK] /llms.txt: $lc lines" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] /llms.txt failed" -ForegroundColor DarkYellow
}

# /openapi.json
try {
    $r = Invoke-WebRequest -Uri "$apiBase/openapi.json" -UseBasicParsing -TimeoutSec 10
    $spec = $r.Content | ConvertFrom-Json
    $ec = $spec.paths."/v1/assets/{asset_id}".get.parameters[0].schema.enum.Count
    Write-Host "  [OK] /openapi.json: $ec assets in enum" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] /openapi.json failed" -ForegroundColor DarkYellow
}

# /catalog.json
try {
    $r = Invoke-WebRequest -Uri "$apiBase/catalog.json" -UseBasicParsing -TimeoutSec 10
    $cat = $r.Content | ConvertFrom-Json
    Write-Host "  [OK] /catalog.json: $($cat.assets.Count) assets" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] /catalog.json failed" -ForegroundColor DarkYellow
}

# Check 5 new guide assets
$guideIds = @(
    "guide-working-in-china-2026-08",
    "guide-hiring-china-2026-08",
    "guide-legal-rights-china-2026-08",
    "guide-study-in-china-2026-08",
    "guide-business-compliance-china-2026-08"
)

foreach ($gid in $guideIds) {
    try {
        $r = Invoke-WebRequest -Uri "$apiBase/v1/assets/$gid" -UseBasicParsing -TimeoutSec 10
        Write-Host "  [OK] /v1/assets/$gid : $($r.StatusCode)" -ForegroundColor Green
    } catch {
        $sc = 0
        if ($_.Exception.Response) { $sc = [int]$_.Exception.Response.StatusCode }
        if ($sc -eq 402) {
            Write-Host "  [OK] /v1/assets/$gid : 402 (payment wall = asset exists!)" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] /v1/assets/$gid : $($_.Exception.Message)" -ForegroundColor DarkYellow
        }
    }
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
