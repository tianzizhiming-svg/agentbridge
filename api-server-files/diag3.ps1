param([string]$ApiPath = "F:\afie_proxy")

Write-Host "=== Diagnostic 3 ===" -ForegroundColor Cyan

# --- Check service names ---
Write-Host ""
Write-Host "--- NSSM Services ---" -ForegroundColor Yellow
$services = @()
try {
    $services = Get-Service | Where-Object { $_.Name -match 'agent|bridge|afie|cloud|tunnel|camp' } | Select-Object Name, Status, DisplayName
} catch {}

if ($services.Count -eq 0) {
    # Try sc.exe
    $scOutput = & sc.exe query type= service state= all 2>$null
    $serviceNames = $scOutput | Select-String "SERVICE_NAME"
    foreach ($s in $serviceNames) {
        $name = $s.ToString() -replace "SERVICE_NAME:\s*", ""
        if ($name -match 'agent|bridge|afie|cloud|tunnel|camp|uvicorn|python|gunicorn') {
            Write-Host "  $name"
        }
    }
} else {
    foreach ($s in $services) {
        Write-Host "  $($s.Name) - $($s.Status) - $($s.DisplayName)"
    }
}

Write-Host ""
Write-Host "--- All NSSM services ---" -ForegroundColor Yellow
$nssmServices = & sc.exe query type= service state= all 2>$null
$nssmServiceNames = $nssmServices | Select-String "SERVICE_NAME" | ForEach-Object {
    ($_.ToString() -replace "SERVICE_NAME:\s*", "").Trim()
}
foreach ($name in $nssmServiceNames) {
    if ($name -match 'agent|bridge|afie|cloud|tunnel|camp|uvicorn|python') {
        $status = (& sc.exe query $name 2>$null) | Select-String "STATE"
        Write-Host "  $name ($status)"
    }
}

# --- Read products.json structure ---
Write-Host ""
Write-Host "--- products.json structure ---" -ForegroundColor Yellow

$productsPath = Join-Path $ApiPath "data\products.json"
if (Test-Path $productsPath) {
    $products = Get-Content $productsPath -Raw | ConvertFrom-Json
    
    # Show first 3 items in detail
    Write-Host "  Total products: $($products.Count)"
    Write-Host ""
    Write-Host "  First 3 items (full structure):"
    for ($i = 0; $i -lt [Math]::Min(3, $products.Count); $i++) {
        Write-Host "  --- Item $i ---" -ForegroundColor DarkGray
        $json = $products[$i] | ConvertTo-Json -Depth 5
        Write-Host $json
    }
    
    # Show one guide item if exists
    $guide = $products | Where-Object { $_.id -eq "guide-144-hour-visa" }
    if ($guide) {
        Write-Host "  --- guide-144-hour-visa (full) ---" -ForegroundColor DarkGray
        $json = $guide | ConvertTo-Json -Depth 5
        Write-Host $json
    }
    
    # Show svc-china-guide
    $svc = $products | Where-Object { $_.id -eq "svc-china-guide" }
    if ($svc) {
        Write-Host "  --- svc-china-guide (full) ---" -ForegroundColor DarkGray
        $json = $svc | ConvertTo-Json -Depth 5
        Write-Host $json
    }
    
    # Show brief-ai
    $brief = $products | Where-Object { $_.id -eq "brief-ai" }
    if ($brief) {
        Write-Host "  --- brief-ai (full) ---" -ForegroundColor DarkGray
        $json = $brief | ConvertTo-Json -Depth 5
        Write-Host $json
    }
} else {
    Write-Host "  products.json not found"
}

# --- Check how prices are determined ---
Write-Host ""
Write-Host "--- Price logic in main.py ---" -ForegroundColor Yellow
$mainPy = Join-Path $ApiPath "main.py"
$lines = Get-Content $mainPy
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match 'ATLAS_STARTER_PRICE|ATLAS_PREMIUM_PRICE|price.*asset|asset.*price|amount.*asset|STARTER_REQ|PREMIUM_REQ') {
        $ln = $i + 1
        Write-Host "  line ${ln}: $($lines[$i].Trim())"
    }
}

# --- Check how assets endpoint works ---
Write-Host ""
Write-Host "--- /v1/assets/{asset_id} route ---" -ForegroundColor Yellow
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match 'v1/assets/\{asset_id\}' -or $lines[$i] -match 'assets.*asset_id') {
        $start = [Math]::Max(0, $i - 1)
        $end = [Math]::Min($lines.Count - 1, $i + 30)
        for ($j = $start; $j -le $end; $j++) {
            $ln = $j + 1
            Write-Host "  ${ln}: $($lines[$j])"
        }
        Write-Host "  ---"
        break
    }
}

# --- Check how asset price is resolved ---
Write-Host ""
Write-Host "--- Asset price resolution ---" -ForegroundColor Yellow
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match 'def.*asset_price|def.*get_price|def.*resolve_price|ATLAS_STARTER|ATLAS_PREMIUM|starter_price|premium_price') {
        $ln = $i + 1
        Write-Host "  line ${ln}: $($lines[$i].Trim())"
    }
}
