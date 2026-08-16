param([string]$ApiPath = "F:\afie_proxy")

Write-Host "=== AgentBridge Fix Script ===" -ForegroundColor Cyan
Write-Host ""

# --- Step 0: Find the real ASSETS price dict ---
Write-Host "[0/6] Locating real ASSETS price dictionary..." -ForegroundColor Yellow

$mainPy = Join-Path $ApiPath "main.py"
$lines = Get-Content $mainPy
$content = Get-Content $mainPy -Raw

# Search for lines containing price mappings like "svc-china-guide": 9990000 or "brief-ai":
$priceDictLines = @()
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '"(svc-china-guide|brief-ai|guide-144-hour-visa|api-web-fetch|api-policy)"\s*:\s*\d+') {
        $ln = $i + 1
        $priceDictLines += @{line=$ln; text=$lines[$i].Trim()}
    }
}

if ($priceDictLines.Count -gt 0) {
    Write-Host "  Found price mappings:" -ForegroundColor Green
    foreach ($p in $priceDictLines) {
        Write-Host "    line $($p.line): $($p.text)" -ForegroundColor DarkGray
    }
    $firstPriceLine = $priceDictLines[0].line
    $lastPriceLine = $priceDictLines[$priceDictLines.Count - 1].line
    Write-Host "  Price dict spans lines $firstPriceLine to $lastPriceLine" -ForegroundColor Green
} else {
    Write-Host "  [WARN] No price dict found with expected pattern" -ForegroundColor DarkYellow
    # Try broader search
    Write-Host "  Searching for amount patterns..."
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '"svc-china-guide"') {
            $ln = $i + 1
            $text = $lines[$i].Trim()
            Write-Host "    line ${ln}: $text" -ForegroundColor DarkGray
        }
        if ($lines[$i] -match '"brief-ai"') {
            $ln = $i + 1
            $text = $lines[$i].Trim()
            Write-Host "    line ${ln}: $text" -ForegroundColor DarkGray
        }
    }
}

Write-Host ""

# --- Step 1: Fix broken search_assets function ---
Write-Host "[1/6] Fixing broken search_assets function..." -ForegroundColor Yellow

# The 5 guide lines were wrongly inserted at lines 130-134 inside search_assets
# Remove them
$newLines = @()
$removed = 0
for ($i = 0; $i -lt $lines.Count; $i++) {
    $lineText = $lines[$i]
    if ($lineText -match '^\s*"guide-(working-in-china|hiring-china|legal-rights-china|study-in-china|business-compliance-china)-2026-08"\s*:\s*10000,?\s*$') {
        # Check if this is inside the search_assets function (lines 127-145 area)
        $ln = $i + 1
        if ($ln -ge 128 -and $ln -le 145) {
            Write-Host "  Removing wrongly inserted line $ln : $($lineText.Trim())" -ForegroundColor DarkGray
            $removed++
            continue
        }
    }
    $newLines += $lineText
}

if ($removed -gt 0) {
    $newLines | Set-Content $mainPy -Encoding UTF8
    Write-Host "  [OK] Removed $removed wrongly inserted lines from search_assets" -ForegroundColor Green
    # Reload
    $lines = Get-Content $mainPy
    $content = Get-Content $mainPy -Raw
} else {
    Write-Host "  [OK] No wrongly inserted lines found (already clean)" -ForegroundColor Green
}

Write-Host ""

# --- Step 2: Copy openapi.json to docs/ ---
Write-Host "[2/6] Copying openapi.json to docs/..." -ForegroundColor Yellow

$srcOpenapi = Join-Path $ApiPath "openapi.json"
$dstOpenapi = Join-Path $ApiPath "docs\openapi.json"
if (Test-Path $srcOpenapi) {
    Copy-Item $srcOpenapi $dstOpenapi -Force
    $sz = (Get-Item $dstOpenapi).Length
    Write-Host "  [OK] Copied openapi.json to docs/ ($sz bytes)" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] openapi.json not found at $srcOpenapi" -ForegroundColor DarkYellow
}

Write-Host ""

# --- Step 3: Copy catalog.json to data/ ---
Write-Host "[3/6] Copying catalog.json to data/..." -ForegroundColor Yellow

$srcCatalog = Join-Path $ApiPath "catalog.json"
$dstCatalog = Join-Path $ApiPath "data\catalog.json"
$dataDir = Join-Path $ApiPath "data"
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
}
if (Test-Path $srcCatalog) {
    Copy-Item $srcCatalog $dstCatalog -Force
    $sz = (Get-Item $dstCatalog).Length
    Write-Host "  [OK] Copied catalog.json to data/ ($sz bytes)" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] catalog.json not found at $srcCatalog" -ForegroundColor DarkYellow
}

Write-Host ""

# --- Step 4: Fix llms.txt route to read from disk ---
Write-Host "[4/6] Fixing llms.txt route to read from disk..." -ForegroundColor Yellow

# Current code (hardcoded):
#   txt = (
#       "# AgentBridge API\n"
#       ...
#   )
#   return PlainTextResponse(txt)
#
# Replace with disk read:
#   base_dir = os.path.dirname(os.path.abspath(__file__))
#   with open(os.path.join(base_dir, "llms.txt"), encoding="utf-8") as f:
#       return PlainTextResponse(f.read())

$content = Get-Content $mainPy -Raw
$llmsOldPattern = 'txt = \(\s*"# AgentBridge API\\n"\s*"Chinese web proxy for AI Agents\."'
$llmsHasDiskRead = $content -match 'open\(os\.path\.join\(base_dir.*llms\.txt'

if ($llmsHasDiskRead) {
    Write-Host "  [OK] llms.txt already reads from disk" -ForegroundColor Green
} else {
    # Find and replace the hardcoded llms.txt block
    $lines2 = Get-Content $mainPy
    $llmsStart = -1
    $llmsEnd = -1
    for ($i = 0; $i -lt $lines2.Count; $i++) {
        if ($lines2[$i] -match 'txt\s*=\s*\(\s*$' -and $i -gt 720 -and $i -lt 740) {
            $llmsStart = $i
            break
        }
    }
    
    if ($llmsStart -gt 0) {
        # Find the closing ) and return
        for ($i = $llmsStart; $i -lt $lines2.Count; $i++) {
            if ($lines2[$i] -match '^\s*\)\s*$' -and $i -gt $llmsStart) {
                $llmsEnd = $i
                break
            }
        }
        
        if ($llmsEnd -gt 0) {
            $replacement = @(
                '    base_dir = os.path.dirname(os.path.abspath(__file__))',
                '    with open(os.path.join(base_dir, "llms.txt"), encoding="utf-8") as f:',
                '        return PlainTextResponse(f.read())'
            )
            
            $newLines2 = $lines2[0..($llmsStart-1)] + $replacement + $lines2[($llmsEnd+1)..($lines2.Count-1)]
            $newLines2 | Set-Content $mainPy -Encoding UTF8
            Write-Host "  [OK] Replaced hardcoded llms.txt with disk read (lines $($llmsStart+1) to $($llmsEnd+1))" -ForegroundColor Green
            $lines = Get-Content $mainPy
            $content = Get-Content $mainPy -Raw
        } else {
            Write-Host "  [WARN] Could not find end of llms.txt block" -ForegroundColor DarkYellow
        }
    } else {
        Write-Host "  [WARN] Could not find llms.txt hardcoded block" -ForegroundColor DarkYellow
    }
}

Write-Host ""

# --- Step 5: Add 5 new assets to ATLAS_MANUAL_FILES ---
Write-Host "[5/6] Adding 5 new guides to ATLAS_MANUAL_FILES..." -ForegroundColor Yellow

$content = Get-Content $mainPy -Raw
$hasGuideInManual = $content -match 'guide-working-in-china-2026-08.*\.md'

if ($hasGuideInManual) {
    Write-Host "  [OK] Guides already in ATLAS_MANUAL_FILES" -ForegroundColor Green
} else {
    # Find ATLAS_MANUAL_FILES dict and add entries
    $lines3 = Get-Content $mainPy
    $manualStart = -1
    $manualEnd = -1
    for ($i = 0; $i -lt $lines3.Count; $i++) {
        if ($lines3[$i] -match 'ATLAS_MANUAL_FILES\s*=\s*\{') {
            $manualStart = $i
            break
        }
    }
    
    if ($manualStart -gt 0) {
        # Find closing }
        $braceCount = 0
        for ($i = $manualStart; $i -lt $lines3.Count; $i++) {
            if ($lines3[$i] -match '\{') { $braceCount += ($lines3[$i] -split '\{').Count - 1 }
            if ($lines3[$i] -match '\}') { $braceCount -= ($lines3[$i] -split '\}').Count - 1 }
            if ($braceCount -le 0 -and $i -gt $manualStart) {
                $manualEnd = $i
                break
            }
        }
        
        if ($manualEnd -gt 0) {
            # Insert before the closing brace
            $newEntries = @(
                '    # China Guides (Markdown)',
                '    "guide-working-in-china-2026-08": "guides/guide-working-in-china-2026-08.md",',
                '    "guide-hiring-china-2026-08": "guides/guide-hiring-china-2026-08.md",',
                '    "guide-legal-rights-china-2026-08": "guides/guide-legal-rights-china-2026-08.md",',
                '    "guide-study-in-china-2026-08": "guides/guide-study-in-china-2026-08.md",',
                '    "guide-business-compliance-china-2026-08": "guides/guide-business-compliance-china-2026-08.md",'
            )
            
            $newLines3 = $lines3[0..($manualEnd-1)] + $newEntries + $lines3[$manualEnd..($lines3.Count-1)]
            $newLines3 | Set-Content $mainPy -Encoding UTF8
            Write-Host "  [OK] Added 5 guide entries to ATLAS_MANUAL_FILES" -ForegroundColor Green
            $lines = Get-Content $mainPy
            $content = Get-Content $mainPy -Raw
        } else {
            Write-Host "  [WARN] Could not find end of ATLAS_MANUAL_FILES" -ForegroundColor DarkYellow
        }
    } else {
        Write-Host "  [WARN] ATLAS_MANUAL_FILES not found" -ForegroundColor DarkYellow
    }
}

Write-Host ""

# --- Step 5b: Add 5 new assets to real price dict ---
Write-Host "[5b/6] Adding 5 new assets to price dictionary..." -ForegroundColor Yellow

$content = Get-Content $mainPy -Raw
$hasGuidePrice = $content -match '"guide-working-in-china-2026-08"\s*:\s*\d+'

if ($hasGuidePrice) {
    Write-Host "  [OK] Guide prices already registered" -ForegroundColor Green
} else {
    # Search for the real price dict - look for "svc-china-guide" with a number value
    $lines4 = Get-Content $mainPy
    $priceLineNum = -1
    for ($i = 0; $i -lt $lines4.Count; $i++) {
        # Match patterns like: "svc-china-guide": 9990000,
        if ($lines4[$i] -match '"svc-china-guide"\s*:\s*\d+') {
            $priceLineNum = $i
            Write-Host "  Found svc-china-guide at line $($i+1): $($lines4[$i].Trim())" -ForegroundColor DarkGray
            break
        }
    }
    
    # If not found, try "brief-ai"
    if ($priceLineNum -eq -1) {
        for ($i = 0; $i -lt $lines4.Count; $i++) {
            if ($lines4[$i] -match '"brief-ai"\s*:\s*\d+') {
                $priceLineNum = $i
                Write-Host "  Found brief-ai at line $($i+1): $($lines4[$i].Trim())" -ForegroundColor DarkGray
                break
            }
        }
    }
    
    # If still not found, try "guide-144-hour-visa"
    if ($priceLineNum -eq -1) {
        for ($i = 0; $i -lt $lines4.Count; $i++) {
            if ($lines4[$i] -match '"guide-144-hour-visa"\s*:\s*\d+') {
                $priceLineNum = $i
                Write-Host "  Found guide-144-hour-visa at line $($i+1): $($lines4[$i].Trim())" -ForegroundColor DarkGray
                break
            }
        }
    }
    
    if ($priceLineNum -gt 0) {
        $newPriceEntries = @(
            '    "guide-working-in-china-2026-08": 10000,',
            '    "guide-hiring-china-2026-08": 10000,',
            '    "guide-legal-rights-china-2026-08": 10000,',
            '    "guide-study-in-china-2026-08": 10000,',
            '    "guide-business-compliance-china-2026-08": 10000,'
        )
        
        $newLines4 = $lines4[0..$priceLineNum] + $newPriceEntries + $lines4[($priceLineNum+1)..($lines4.Count-1)]
        $newLines4 | Set-Content $mainPy -Encoding UTF8
        Write-Host "  [OK] Added 5 guide prices after line $($priceLineNum+1)" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] Could not find price dict anchor" -ForegroundColor DarkYellow
        Write-Host "  Listing all lines with 10000 or 9990000 or 4990000..." -ForegroundColor DarkGray
        for ($i = 0; $i -lt $lines4.Count; $i++) {
            if ($lines4[$i] -match ':\s*(10000|9990000|4990000|90000000)\b') {
                $ln = $i + 1
                Write-Host "    line ${ln}: $($lines4[$i].Trim())" -ForegroundColor DarkGray
            }
        }
    }
}

Write-Host ""

# --- Step 5c: Check products.json ---
Write-Host "[5c/6] Checking products.json..." -ForegroundColor Yellow

$productsPath = Join-Path $ApiPath "data\products.json"
if (Test-Path $productsPath) {
    $productsContent = Get-Content $productsPath -Raw
    $hasGuides = $productsContent -match 'guide-working-in-china-2026-08'
    if ($hasGuides) {
        Write-Host "  [OK] Guides already in products.json" -ForegroundColor Green
    } else {
        Write-Host "  [INFO] products.json exists but guides not added yet" -ForegroundColor DarkYellow
        Write-Host "  Listing products.json asset IDs:" -ForegroundColor DarkGray
        $prodLines = Get-Content $productsPath
        for ($i = 0; $i -lt $prodLines.Count; $i++) {
            if ($prodLines[$i] -match '"id"\s*:') {
                Write-Host "    $($prodLines[$i].Trim())" -ForegroundColor DarkGray
            }
        }
    }
} else {
    Write-Host "  [INFO] products.json not found at $productsPath" -ForegroundColor DarkYellow
}

Write-Host ""

# --- Step 6: Restart ---
Write-Host "[6/6] Restarting service..." -ForegroundColor Yellow

try {
    nssm restart AgentBridge-API
    Write-Host "  [OK] Service restarted" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Try: nssm restart AgentBridge-API" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Verification ===" -ForegroundColor Cyan
Start-Sleep -Seconds 3

try {
    $llms = Invoke-WebRequest -Uri "http://localhost:8000/llms.txt" -UseBasicParsing -TimeoutSec 10
    $lineCount = ($llms.Content -split "`n").Count
    Write-Host "  [OK] llms.txt: $lineCount lines" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] llms.txt check failed" -ForegroundColor DarkYellow
}

try {
    $api = Invoke-WebRequest -Uri "http://localhost:8000/openapi.json" -UseBasicParsing -TimeoutSec 10
    $spec = $api.Content | ConvertFrom-Json
    $enumCount = $spec.paths."/v1/assets/{asset_id}".get.parameters[0].schema.enum.Count
    Write-Host "  [OK] openapi.json enum: $enumCount items" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] openapi.json check failed" -ForegroundColor DarkYellow
}

try {
    $cat = Invoke-WebRequest -Uri "http://localhost:8000/catalog.json" -UseBasicParsing -TimeoutSec 10
    $catJson = $cat.Content | ConvertFrom-Json
    Write-Host "  [OK] catalog.json: $($catJson.assets.Count) assets" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] catalog.json check failed" -ForegroundColor DarkYellow
}

try {
    $asset = Invoke-WebRequest -Uri "http://localhost:8000/v1/assets/guide-working-in-china-2026-08" -UseBasicParsing -TimeoutSec 10
    Write-Host "  [OK] New asset accessible: $($asset.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] New asset check: $($_.Exception.Message)" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
