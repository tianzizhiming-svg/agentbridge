# AgentBridge API Server Deploy Script
# Usage: powershell -ExecutionPolicy Bypass -File deploy-api.ps1
# Or download-and-run: 
#   irm "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files/deploy-api.ps1" -OutFile deploy-api.ps1; powershell -ExecutionPolicy Bypass -File deploy-api.ps1

param([string]$ApiPath = "F:\afie_proxy")

Write-Host "=== AgentBridge API Server Deploy ===" -ForegroundColor Cyan
Write-Host "API path: $ApiPath"
Write-Host ""

# --- Step 1: Download files from GitHub ---
Write-Host "[1/4] Downloading updated files from GitHub..." -ForegroundColor Yellow

$baseUrl = "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files"
$tmpDir = "$env:TEMP\agentbridge-deploy"

if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null

$files = @("llms.txt", "openapi.json", "catalog.json")
foreach ($f in $files) {
    $url = "$baseUrl/$f"
    $dest = "$tmpDir\$f"
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
        Write-Host "  Downloaded $f OK" -ForegroundColor Green
    } catch {
        $errMsg = $_.Exception.Message
        Write-Host "  Failed to download $f : $errMsg" -ForegroundColor Red
        exit 1
    }
}

# --- Step 2: Backup existing files ---
Write-Host ""
Write-Host "[2/4] Backing up existing files..." -ForegroundColor Yellow

$backupDir = "$ApiPath\backup-$(Get-Date -Format 'yyyy-MM-dd-HHmmss')"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

foreach ($f in $files) {
    $src = "$ApiPath\$f"
    if (Test-Path $src) {
        Copy-Item $src "$backupDir\$f"
        Write-Host "  Backed up $f OK" -ForegroundColor Green
    } else {
        Write-Host "  $f not found at $src (skipping backup)" -ForegroundColor DarkYellow
    }
}

# --- Step 3: Replace files ---
Write-Host ""
Write-Host "[3/4] Replacing files..." -ForegroundColor Yellow

foreach ($f in $files) {
    $src = "$tmpDir\$f"
    $dest = "$ApiPath\$f"
    Copy-Item $src $dest -Force
    Write-Host "  Replaced $f OK" -ForegroundColor Green
}

# --- Step 4: Add 5 new assets to main.py ---
Write-Host ""
Write-Host "[4/4] Adding 5 new asset IDs to main.py..." -ForegroundColor Yellow

$mainPy = "$ApiPath\main.py"
if (-not (Test-Path $mainPy)) {
    $found = Get-ChildItem -Path $ApiPath -Filter "main.py" -Recurse | Select-Object -First 1
    if ($found) {
        $mainPy = $found.FullName
        Write-Host "  Found main.py at: $mainPy" -ForegroundColor DarkYellow
    } else {
        Write-Host "  main.py not found in $ApiPath" -ForegroundColor Red
        Write-Host "  Please manually add these 5 lines to your ASSETS dictionary:" -ForegroundColor Yellow
        Write-Host ""
        Write-Host '    "guide-working-in-china-2026-08": 10000,' -ForegroundColor White
        Write-Host '    "guide-hiring-china-2026-08": 10000,' -ForegroundColor White
        Write-Host '    "guide-legal-rights-china-2026-08": 10000,' -ForegroundColor White
        Write-Host '    "guide-study-in-china-2026-08": 10000,' -ForegroundColor White
        Write-Host '    "guide-business-compliance-china-2026-08": 10000,' -ForegroundColor White
        Write-Host ""
    }
}

if (Test-Path $mainPy) {
    $content = Get-Content $mainPy -Raw
    $newAssets = @(
        '    "guide-working-in-china-2026-08": 10000,',
        '    "guide-hiring-china-2026-08": 10000,',
        '    "guide-legal-rights-china-2026-08": 10000,',
        '    "guide-study-in-china-2026-08": 10000,',
        '    "guide-business-compliance-china-2026-08": 10000,'
    )
    
    $alreadyAdded = $content -match "guide-working-in-china-2026-08"
    
    if ($alreadyAdded) {
        Write-Host "  Assets already registered in main.py (skipping)" -ForegroundColor Green
    } else {
        Copy-Item $mainPy "$backupDir\main.py"
        
        $lines = Get-Content $mainPy
        $insertLine = -1
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match '"svc-china-guide"') {
                $insertLine = $i + 1
                break
            }
        }
        
        if ($insertLine -eq -1) {
            for ($i = 0; $i -lt $lines.Count; $i++) {
                if ($lines[$i] -match '"topic-15th-five-year"') {
                    $insertLine = $i + 1
                    break
                }
            }
        }
        
        if ($insertLine -gt 0) {
            $newLines = $lines[0..($insertLine-1)] + $newAssets + $lines[$insertLine..($lines.Count-1)]
            $newLines | Set-Content $mainPy
            Write-Host "  Added 5 new assets to main.py at line $insertLine OK" -ForegroundColor Green
        } else {
            Write-Host "  Could not find insertion point in main.py" -ForegroundColor DarkYellow
            Write-Host "  Please manually add these 5 lines to your ASSETS dictionary:" -ForegroundColor Yellow
            Write-Host ""
            foreach ($line in $newAssets) {
                Write-Host $line -ForegroundColor White
            }
        }
    }
}

# --- Step 5: Restart service ---
Write-Host ""
Write-Host "Restarting AgentBridge-API service..." -ForegroundColor Yellow

try {
    nssm restart AgentBridge-API
    Write-Host "  Service restarted OK" -ForegroundColor Green
} catch {
    $errMsg2 = $_.Exception.Message
    Write-Host "  Failed to restart service: $errMsg2" -ForegroundColor Red
    Write-Host "  Try manually: nssm restart AgentBridge-API" -ForegroundColor Yellow
}

# --- Verify ---
Write-Host ""
Write-Host "=== Verification ===" -ForegroundColor Cyan
Start-Sleep -Seconds 3

try {
    $health = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 10
    Write-Host "  Health check: $($health.StatusCode) OK" -ForegroundColor Green
} catch {
    Write-Host "  Health check failed (service may still be starting)" -ForegroundColor DarkYellow
}

try {
    $llms = Invoke-WebRequest -Uri "http://localhost:8000/llms.txt" -UseBasicParsing -TimeoutSec 10
    $lineCount = ($llms.Content -split "`n").Count
    Write-Host "  llms.txt: $lineCount lines" -ForegroundColor Green
} catch {
    Write-Host "  llms.txt check failed" -ForegroundColor DarkYellow
}

try {
    $api = Invoke-WebRequest -Uri "http://localhost:8000/openapi.json" -UseBasicParsing -TimeoutSec 10
    $spec = $api.Content | ConvertFrom-Json
    $enumCount = $spec.paths."/v1/assets/{asset_id}".get.parameters[0].schema.enum.Count
    Write-Host "  openapi.json enum: $enumCount items" -ForegroundColor Green
} catch {
    Write-Host "  openapi.json check failed" -ForegroundColor DarkYellow
}

try {
    $asset = Invoke-WebRequest -Uri "http://localhost:8000/v1/assets/guide-working-in-china-2026-08" -UseBasicParsing -TimeoutSec 10
    Write-Host "  New asset guide-working-in-china-2026-08: $($asset.StatusCode) OK" -ForegroundColor Green
} catch {
    Write-Host "  New asset check failed (may need manual verification)" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "=== Deploy Complete ===" -ForegroundColor Cyan
Write-Host "Backup saved to: $backupDir"
Write-Host ""
Write-Host "If something went wrong, restore from backup:"
Write-Host "  Copy-Item '$backupDir\*' '$ApiPath\' -Recurse -Force"
Write-Host "  nssm restart AgentBridge-API"
