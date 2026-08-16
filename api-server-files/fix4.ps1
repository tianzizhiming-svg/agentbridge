# AgentBridge Fix4 - Add 5 guides to products.json + restart service
# Handles flat array JSON structure + gives service more time to start
# Usage:
#   irm "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files/fix4.ps1" -OutFile "$env:TEMP\fix4.ps1"
#   powershell -ExecutionPolicy Bypass -File "$env:TEMP\fix4.ps1"

param([string]$ApiPath = "F:\afie_proxy")

Write-Host "=== AgentBridge Fix4 ===" -ForegroundColor Cyan
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
Write-Host "  [OK] Backup saved: $backupPath" -ForegroundColor Green

# Parse existing JSON
$rawJson = Get-Content $productsPath -Raw -Encoding UTF8
$json = $rawJson | ConvertFrom-Json

# Detect structure: flat array [...] or object { "products": [...] }
$isFlatArray = $false
if ($json -is [System.Array]) {
    $isFlatArray = $true
    Write-Host "  Detected: flat array structure" -ForegroundColor DarkGray
    $products = $json
} else {
    Write-Host "  Detected: object with products property" -ForegroundColor DarkGray
    $products = $json.products
}

# Check if already exists
$existing = $products | Where-Object { $_.id -eq "guide-working-in-china-2026-08" }
if ($existing) {
    Write-Host "  [OK] Guides already in products.json (skipping)" -ForegroundColor Green
} else {
    # Add each guide
    foreach ($guide in $guidesJson) {
        $products += $guide
        Write-Host "  Added: $($guide.id)" -ForegroundColor DarkGray
    }

    # Write back - handle both structures
    if ($isFlatArray) {
        $output = $products | ConvertTo-Json -Depth 10
        # If single item, ConvertTo-Json returns single line, force array
        if ($products.Count -eq 1) {
            $output = "[" + $output + "]"
        }
    } else {
        $json.products = $products
        if ($json.total_products) {
            $json.total_products = $products.Count
        }
        $output = $json | ConvertTo-Json -Depth 10
    }

    [System.IO.File]::WriteAllText($productsPath, $output, [System.Text.UTF8Encoding]::new($false))

    Write-Host "  [OK] Added $($guidesJson.Count) guides to products.json" -ForegroundColor Green
    Write-Host "  Total products: $($products.Count)" -ForegroundColor DarkGray
}

Write-Host ""

# --- Step 3: Restart AgentBridge service ---
Write-Host "[3/4] Restarting AgentBridge service..." -ForegroundColor Yellow

$serviceName = "AgentBridge"

# Stop
Write-Host "  Stopping $serviceName..." -ForegroundColor DarkGray
& nssm stop $serviceName 2>$null
Start-Sleep -Seconds 3

# Check it stopped
$svcState = & sc.exe query $serviceName 2>$null
if ($svcState -match "STOPPED") {
    Write-Host "  [OK] Service stopped" -ForegroundColor Green
} else {
    Write-Host "  Service still running, force stop..." -ForegroundColor DarkYellow
    & sc.exe stop $serviceName 2>$null
    Start-Sleep -Seconds 3
}

# Start
Write-Host "  Starting $serviceName..." -ForegroundColor DarkGray
& nssm start $serviceName 2>$null

# Wait for service to be ready
Write-Host "  Waiting for service to be ready..." -ForegroundColor DarkGray
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

if (-not $ready) {
    Write-Host "  [WARN] Service not responding after ${maxWait}s" -ForegroundColor DarkYellow
    Write-Host "  Check service status: sc.exe query $serviceName" -ForegroundColor DarkGray
    Write-Host "  Check logs: nssm dump $serviceName" -ForegroundColor DarkGray
    # Try one more start
    & sc.exe start $serviceName 2>$null
    Start-Sleep -Seconds 5
}

Write-Host ""

# --- Step 4: Verify ---
Write-Host "[4/4] Verifying..." -ForegroundColor Yellow

$apiBase = "http://localhost:8000"

# products.json
try {
    $pf = Get-Content $productsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($pf -is [System.Array]) {
        $gc = ($pf | Where-Object { $_.id -match "^guide-" }).Count
        $tc = $pf.Count
    } else {
        $gc = ($pf.products | Where-Object { $_.id -match "^guide-" }).Count
        $tc = $pf.products.Count
    }
    Write-Host "  [OK] products.json: $tc total, $gc guides" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] products.json check failed: $($_.Exception.Message)" -ForegroundColor DarkYellow
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
