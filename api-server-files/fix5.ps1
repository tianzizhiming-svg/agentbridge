# AgentBridge Fix5 - Use Python instead of PowerShell to modify products.json
# PowerShell ConvertTo-Json may corrupt the file, Python json module is reliable
# Usage:
#   irm "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files/fix5.ps1" -OutFile "$env:TEMP\fix5.ps1"
#   powershell -ExecutionPolicy Bypass -File "$env:TEMP\fix5.ps1"

param([string]$ApiPath = "F:\afie_proxy")

Write-Host "=== AgentBridge Fix5 (Python-based) ===" -ForegroundColor Cyan
Write-Host "API path: $ApiPath"
Write-Host ""

# --- Step 1: Restore from backup if products.json is broken ---
Write-Host "[1/5] Checking products.json validity..." -ForegroundColor Yellow

$productsPath = Join-Path $ApiPath "data\products.json"

# Find latest backup
$backups = Get-ChildItem (Join-Path $ApiPath "data") -Filter "products.json.bak-*" | Sort-Object LastWriteTime -Descending
if ($backups.Count -gt 0) {
    $latestBackup = $backups[0].FullName
    Write-Host "  Latest backup: $latestBackup" -ForegroundColor DarkGray
}

# Test if current products.json is valid
$jsonValid = $false
try {
    $testContent = Get-Content $productsPath -Raw -Encoding UTF8
    $testContent | ConvertFrom-Json | Out-Null
    $jsonValid = $true
    Write-Host "  [OK] products.json is valid JSON" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] products.json is broken: $($_.Exception.Message)" -ForegroundColor DarkYellow
    if ($backups.Count -gt 0) {
        Write-Host "  Restoring from backup..." -ForegroundColor DarkYellow
        Copy-Item $latestBackup $productsPath -Force
        Write-Host "  [OK] Restored from backup" -ForegroundColor Green
    }
}

Write-Host ""

# --- Step 2: Download new-guides.json ---
Write-Host "[2/5] Downloading new-guides.json..." -ForegroundColor Yellow

$baseUrl = "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files"
$guidesUrl = "$baseUrl/new-guides.json?v=$(Get-Random)"
$guidesTmp = Join-Path $env:TEMP "new-guides.json"

try {
    Invoke-WebRequest -Uri $guidesUrl -OutFile $guidesTmp -UseBasicParsing
    Write-Host "  [OK] Downloaded new-guides.json" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host ""

# --- Step 3: Use Python to merge ---
Write-Host "[3/5] Merging guides via Python..." -ForegroundColor Yellow

$pythonScript = @"
import json
import sys

products_path = r'$productsPath'
guides_path = r'$guidesTmp'

# Read existing products
with open(products_path, 'r', encoding='utf-8') as f:
    raw = f.read()

# Parse - could be array or object
data = json.loads(raw)

if isinstance(data, list):
    products = data
    is_flat = True
elif isinstance(data, dict) and 'products' in data:
    products = data['products']
    is_flat = False
else:
    print('ERROR: Unknown JSON structure')
    sys.exit(1)

# Check if guides already exist
existing_ids = set(p.get('id', '') for p in products)
guide0 = 'guide-working-in-china-2026-08'
if guide0 in existing_ids:
    print('Guides already exist, skipping')
else:
    # Read new guides
    with open(guides_path, 'r', encoding='utf-8') as f:
        new_guides = json.load(f)

    # Add each guide
    for g in new_guides:
        products.append(g)
        print(f'  Added: {g["id"]}')

    # Write back
    if is_flat:
        output = json.dumps(products, ensure_ascii=False, indent=2)
    else:
        data['products'] = products
        if 'total_products' in data:
            data['total_products'] = len(products)
        output = json.dumps(data, ensure_ascii=False, indent=2)

    with open(products_path, 'w', encoding='utf-8') as f:
        f.write(output)

    print(f'  Total products: {len(products)}')
    print('  Done')
"@

$pyTmp = Join-Path $env:TEMP "ab_fix5.py"
[System.IO.File]::WriteAllText($pyTmp, $pythonScript, [System.Text.UTF8Encoding]::new($false))

$pyResult = & python $pyTmp 2>&1
foreach ($line in $pyResult) {
    Write-Host "  $line" -ForegroundColor DarkGray
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Python merge completed" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Python merge failed (exit $LASTEXITCODE)" -ForegroundColor Red
    Write-Host "  Trying to restore from backup..." -ForegroundColor DarkYellow
    if ($backups.Count -gt 0) {
        Copy-Item $latestBackup $productsPath -Force
        Write-Host "  [OK] Restored from backup" -ForegroundColor Green
    }
    exit 1
}

Write-Host ""

# --- Step 4: Restart service ---
Write-Host "[4/5] Restarting AgentBridge service..." -ForegroundColor Yellow

Write-Host "  Stopping..." -ForegroundColor DarkGray
& nssm stop AgentBridge 2>$null
Start-Sleep -Seconds 3

Write-Host "  Starting..." -ForegroundColor DarkGray
& nssm start AgentBridge 2>$null

# Wait for service
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
    Write-Host "  Trying sc.exe start..." -ForegroundColor DarkYellow
    & sc.exe start AgentBridge 2>$null
    Start-Sleep -Seconds 5
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 10
        if ($r.StatusCode -eq 200) {
            $ready = $true
            Write-Host "  [OK] Service ready after sc.exe start" -ForegroundColor Green
        }
    } catch {
        Write-Host "  [FAIL] Service still not responding" -ForegroundColor Red
        Write-Host "  Check: cd $ApiPath && python main.py" -ForegroundColor Yellow
        Write-Host "  This will show the startup error" -ForegroundColor Yellow
    }
}

Write-Host ""

# --- Step 5: Verify ---
Write-Host "[5/5] Verifying..." -ForegroundColor Yellow

$apiBase = "http://localhost:8000"

try {
    $r = Invoke-WebRequest -Uri "$apiBase/health" -UseBasicParsing -TimeoutSec 10
    Write-Host "  [OK] /health: $($r.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] /health failed" -ForegroundColor DarkYellow
}

try {
    $r = Invoke-WebRequest -Uri "$apiBase/llms.txt" -UseBasicParsing -TimeoutSec 10
    $lc = ($r.Content -split "`n").Count
    Write-Host "  [OK] /llms.txt: $lc lines" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] /llms.txt failed" -ForegroundColor DarkYellow
}

try {
    $r = Invoke-WebRequest -Uri "$apiBase/openapi.json" -UseBasicParsing -TimeoutSec 10
    $spec = $r.Content | ConvertFrom-Json
    $ec = $spec.paths."/v1/assets/{asset_id}".get.parameters[0].schema.enum.Count
    Write-Host "  [OK] /openapi.json: $ec assets in enum" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] /openapi.json failed" -ForegroundColor DarkYellow
}

try {
    $r = Invoke-WebRequest -Uri "$apiBase/catalog.json" -UseBasicParsing -TimeoutSec 10
    $cat = $r.Content | ConvertFrom-Json
    Write-Host "  [OK] /catalog.json: $($cat.assets.Count) assets" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] /catalog.json failed" -ForegroundColor DarkYellow
}

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
