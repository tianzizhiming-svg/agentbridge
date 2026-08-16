param([string]$ApiPath = "F:\afie_proxy")

Write-Host "=== AgentBridge API Server Deploy ===" -ForegroundColor Cyan
Write-Host "API path: $ApiPath"
Write-Host ""

Write-Host "[1/4] Downloading updated files from GitHub..." -ForegroundColor Yellow

$baseUrl = "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files"
$tmpDir = "$env:TEMP\ab-deploy"

if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null

$files = @("llms.txt", "openapi.json", "catalog.json")
foreach ($f in $files) {
    $url = "$baseUrl/$f"
    $dest = Join-Path $tmpDir $f
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
        Write-Host "  [OK] Downloaded $f" -ForegroundColor Green
    } catch {
        $errMsg = $_.Exception.Message
        Write-Host "  [FAIL] Download $f - $errMsg" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "[2/4] Backing up existing files..." -ForegroundColor Yellow

$backupDir = Join-Path $ApiPath ("backup-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

foreach ($f in $files) {
    $src = Join-Path $ApiPath $f
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $backupDir $f)
        Write-Host "  [OK] Backed up $f" -ForegroundColor Green
    } else {
        Write-Host "  [SKIP] $f not found" -ForegroundColor DarkYellow
    }
}

Write-Host ""
Write-Host "[3/4] Replacing files..." -ForegroundColor Yellow

foreach ($f in $files) {
    $src = Join-Path $tmpDir $f
    $dest = Join-Path $ApiPath $f
    Copy-Item $src $dest -Force
    Write-Host "  [OK] Replaced $f" -ForegroundColor Green
}

Write-Host ""
Write-Host "[4/4] Adding 5 new asset IDs to main.py..." -ForegroundColor Yellow

$mainPy = Join-Path $ApiPath "main.py"
if (Test-Path $mainPy) {
    $content = Get-Content $mainPy -Raw
    $alreadyAdded = $content -match "guide-working-in-china-2026-08"
    
    if ($alreadyAdded) {
        Write-Host "  [OK] Assets already registered (skipping)" -ForegroundColor Green
    } else {
        Copy-Item $mainPy (Join-Path $backupDir "main.py")
        
        $newAssets = @(
            '    "guide-working-in-china-2026-08": 10000,',
            '    "guide-hiring-china-2026-08": 10000,',
            '    "guide-legal-rights-china-2026-08": 10000,',
            '    "guide-study-in-china-2026-08": 10000,',
            '    "guide-business-compliance-china-2026-08": 10000,'
        )
        
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
            Write-Host "  [OK] Added 5 new assets to main.py at line $insertLine" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] Could not find insertion point" -ForegroundColor DarkYellow
            Write-Host "  Add these lines manually to ASSETS dict:" -ForegroundColor Yellow
            foreach ($line in $newAssets) { Write-Host $line }
        }
    }
} else {
    Write-Host "  [FAIL] main.py not found" -ForegroundColor Red
}

Write-Host ""
Write-Host "Restarting AgentBridge-API service..." -ForegroundColor Yellow

try {
    nssm restart AgentBridge-API
    Write-Host "  [OK] Service restarted" -ForegroundColor Green
} catch {
    Write-Host "  [FAIL] Try manually: nssm restart AgentBridge-API" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== Verification ===" -ForegroundColor Cyan
Start-Sleep -Seconds 3

try {
    $health = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 10
    Write-Host "  [OK] Health check: $($health.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] Health check failed" -ForegroundColor DarkYellow
}

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
    $asset = Invoke-WebRequest -Uri "http://localhost:8000/v1/assets/guide-working-in-china-2026-08" -UseBasicParsing -TimeoutSec 10
    Write-Host "  [OK] New asset accessible: $($asset.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] New asset check failed" -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "=== Deploy Complete ===" -ForegroundColor Cyan
Write-Host "Backup: $backupDir"
