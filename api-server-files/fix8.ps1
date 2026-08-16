# AgentBridge Fix8 - Register 5 guides in main.py via Python (safe encoding)
# The restored backup doesn't have the 5 new guides. Add them safely.
# Usage:
#   irm "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files/fix8.ps1" -OutFile "$env:TEMP\fix8.ps1"
#   powershell -ExecutionPolicy Bypass -File "$env:TEMP\fix8.ps1"

param([string]$ApiPath = "F:\afie_proxy")

Write-Host "=== AgentBridge Fix8 (Register guides in main.py) ===" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Download new-guides.json ---
Write-Host "[1/4] Downloading new-guides.json..." -ForegroundColor Yellow

$baseUrl = "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files"
$guidesUrl = "$baseUrl/new-guides.json?v=$(Get-Random)"
$guidesTmp = Join-Path $env:TEMP "new-guides.json"

try {
    Invoke-WebRequest -Uri $guidesUrl -OutFile $guidesTmp -UseBasicParsing
    Write-Host "  [OK] Downloaded" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host ""

# --- Step 2: Add guides to products.json via Python ---
Write-Host "[2/4] Adding guides to products.json..." -ForegroundColor Yellow

$productsPath = Join-Path $ApiPath "data\products.json"

$pyMerge = @'
import json, sys

products_path = sys.argv[1]
guides_path = sys.argv[2]

with open(products_path, "r", encoding="utf-8") as f:
    raw = f.read()

data = json.loads(raw)

if isinstance(data, list):
    products = data
    is_flat = True
elif isinstance(data, dict) and "products" in data:
    products = data["products"]
    is_flat = False
else:
    print("ERROR: unknown structure")
    sys.exit(1)

existing_ids = set(p.get("id", "") for p in products)
if "guide-working-in-china-2026-08" in existing_ids:
    print("Guides already in products.json, skipping")
else:
    with open(guides_path, "r", encoding="utf-8") as f:
        new_guides = json.load(f)
    for g in new_guides:
        products.append(g)
        print(f"  Added: {g['id']}")

    if is_flat:
        output = json.dumps(products, ensure_ascii=False, indent=2)
    else:
        data["products"] = products
        if "total_products" in data:
            data["total_products"] = len(products)
        output = json.dumps(data, ensure_ascii=False, indent=2)

    with open(products_path, "w", encoding="utf-8", newline="") as f:
        f.write(output)

print(f"  Total products: {len(products)}")
'@

$pyTmp = Join-Path $env:TEMP "ab_fix8_merge.py"
[System.IO.File]::WriteAllText($pyTmp, $pyMerge, [System.Text.UTF8Encoding]::new($false))

# Backup products.json
$prodBak = $productsPath + ".bak-fix8"
Copy-Item $productsPath $prodBak -Force

$pyResult = & python $pyTmp $productsPath $guidesTmp 2>&1
foreach ($line in $pyResult) {
    Write-Host "  $line" -ForegroundColor DarkGray
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "  [FAIL] Merge failed" -ForegroundColor Red
    Copy-Item $prodBak $productsPath -Force
    exit 1
}
Write-Host "  [OK] products.json updated" -ForegroundColor Green

Write-Host ""

# --- Step 3: Patch main.py via Python (add ATLAS_MANUAL_FILES + ASSETS entries) ---
Write-Host "[3/4] Patching main.py..." -ForegroundColor Yellow

$mainPy = Join-Path $ApiPath "main.py"
$mainBak = $mainPy + ".bak-fix8"
Copy-Item $mainPy $mainBak -Force

# Python script that reads main.py, finds the right insertion points, and adds entries
# All string matching uses ASCII-only patterns
$pyPatch = @'
import sys
import re

path = sys.argv[1]

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

lines = content.split("\n")
changed = False

# --- 1. Add to ATLAS_MANUAL_FILES ---
# Find the ATLAS_MANUAL_FILES dict and add guide entries before closing }
guide_entries = [
    '    "guide-working-in-china-2026-08": "guides/guide-working-in-china-2026-08.md",',
    '    "guide-hiring-china-2026-08": "guides/guide-hiring-china-2026-08.md",',
    '    "guide-legal-rights-china-2026-08": "guides/guide-legal-rights-china-2026-08.md",',
    '    "guide-study-in-china-2026-08": "guides/guide-study-in-china-2026-08.md",',
    '    "guide-business-compliance-china-2026-08": "guides/guide-business-compliance-china-2026-08.md",',
]

if "guide-working-in-china-2026-08" in content:
    print("  Guides already in main.py, skipping patch")
else:
    # Find ATLAS_MANUAL_FILES dict
    manual_start = -1
    for i, line in enumerate(lines):
        if "ATLAS_MANUAL_FILES" in line and "{" in line:
            manual_start = i
            break

    if manual_start >= 0:
        # Find closing brace
        brace_count = 0
        manual_end = -1
        for i in range(manual_start, len(lines)):
            brace_count += lines[i].count("{") - lines[i].count("}")
            if brace_count <= 0 and i > manual_start:
                manual_end = i
                break

        if manual_end >= 0:
            # Insert before the closing brace line
            comment_line = "    # China Guides 2026-08"
            new_lines = lines[:manual_end] + [comment_line] + guide_entries + lines[manual_end:]
            lines = new_lines
            print(f"  Added 5 entries to ATLAS_MANUAL_FILES (around line {manual_end})")
            changed = True
        else:
            print("  WARN: Could not find end of ATLAS_MANUAL_FILES")
    else:
        print("  WARN: ATLAS_MANUAL_FILES not found")

    # --- 2. Add to ASSETS dict (price mapping) ---
    # Find lines with known price patterns like "svc-china-guide": <number>
    # or "brief-ai": <number> and add our guides after
    price_entries = [
        '    "guide-working-in-china-2026-08": 10000,',
        '    "guide-hiring-china-2026-08": 10000,',
        '    "guide-legal-rights-china-2026-08": 10000,',
        '    "guide-study-in-china-2026-08": 10000,',
        '    "guide-business-compliance-china-2026-08": 10000,',
    ]

    # Search for any known asset price line to use as anchor
    anchor_line = -1
    anchor_patterns = [
        r'"svc-china-guide"\s*:\s*\d+',
        r'"brief-ai"\s*:\s*\d+',
        r'"guide-144-hour-visa"\s*:\s*\d+',
        r'"guide-china-survival"\s*:\s*\d+',
        r'"guide-social-media-registration"\s*:\s*\d+',
        r'"api-web-fetch"\s*:\s*\d+',
    ]

    for i, line in enumerate(lines):
        for pat in anchor_patterns:
            if re.search(pat, line):
                anchor_line = i
                print(f"  Found price anchor at line {i+1}: {line.strip()[:80]}")
                break
        if anchor_line >= 0:
            break

    if anchor_line >= 0:
        # Insert after the anchor line
        new_lines = lines[:anchor_line+1] + price_entries + lines[anchor_line+1:]
        lines = new_lines
        print(f"  Added 5 price entries after line {anchor_line+1}")
        changed = True
    else:
        print("  WARN: Could not find price dict anchor")
        # Try to find any dict with asset_id: number pattern
        for i, line in enumerate(lines):
            if re.search(r'"[a-z].*"\s*:\s*\d{4,}', line) and "import" not in line:
                anchor_line = i
                print(f"  Found generic price pattern at line {i+1}: {line.strip()[:80]}")
                break
        if anchor_line >= 0:
            new_lines = lines[:anchor_line+1] + price_entries + lines[anchor_line+1:]
            lines = new_lines
            print(f"  Added 5 price entries after line {anchor_line+1}")
            changed = True

    if changed:
        new_content = "\n".join(lines)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new_content)
        print("  [OK] main.py patched successfully")
    else:
        print("  [WARN] No changes made to main.py")
'@

$pyTmp2 = Join-Path $env:TEMP "ab_fix8_patch.py"
[System.IO.File]::WriteAllText($pyTmp2, $pyPatch, [System.Text.UTF8Encoding]::new($false))

$pyResult2 = & python $pyTmp2 $mainPy 2>&1
foreach ($line in $pyResult2) {
    Write-Host "  $line" -ForegroundColor DarkGray
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "  [FAIL] Patch failed" -ForegroundColor Red
    Copy-Item $mainBak $mainPy -Force
    exit 1
}

# Verify syntax
$syntaxCheck = & python -c "import py_compile; py_compile.compile(r'$mainPy', doraise=True)" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [FAIL] Syntax error after patch:" -ForegroundColor Red
    Write-Host "  $syntaxCheck" -ForegroundColor DarkRed
    Copy-Item $mainBak $mainPy -Force
    Write-Host "  Restored from backup" -ForegroundColor DarkYellow
    exit 1
}

Write-Host "  [OK] Syntax verified" -ForegroundColor Green

Write-Host ""

# --- Step 4: Restart and verify ---
Write-Host "[4/4] Restarting service..." -ForegroundColor Yellow

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
        $r = Invoke-WebRequest -Uri "http://localhost:8000/openapi.json" -UseBasicParsing -TimeoutSec 10
        $spec = $r.Content | ConvertFrom-Json
        $ec = $spec.paths."/v1/assets/{asset_id}".get.parameters[0].schema.enum.Count
        Write-Host "  [OK] /openapi.json: $ec assets" -ForegroundColor Green
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
                Write-Host "  [OK] /v1/assets/$gid : 402 (payment wall = exists!)" -ForegroundColor Green
            } else {
                Write-Host "  [WARN] /v1/assets/$gid : $($_.Exception.Message)" -ForegroundColor DarkYellow
            }
        }
    }
} else {
    Write-Host "  [FAIL] Service not responding" -ForegroundColor Red
    Write-Host "  Try: cd $ApiPath; python main.py" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
