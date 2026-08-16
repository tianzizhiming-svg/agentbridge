# AgentBridge Fix2 - Add 5 guides to products.json + find correct service
# Usage:
#   irm "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files/fix2.ps1?v=$(Get-Random)" -OutFile "$env:TEMP\fix2.ps1"
#   powershell -ExecutionPolicy Bypass -File "$env:TEMP\fix2.ps1"

param([string]$ApiPath = "F:\afie_proxy")

Write-Host "=== AgentBridge Fix2 ===" -ForegroundColor Cyan
Write-Host "API path: $ApiPath"
Write-Host ""

# --- Step 1: Add 5 guides to products.json ---
Write-Host "[1/3] Adding 5 guides to products.json..." -ForegroundColor Yellow

$productsPath = Join-Path $ApiPath "data\products.json"
if (-not (Test-Path $productsPath)) {
    # Try alternative location
    $altPath = Join-Path $ApiPath "data\products-verified.json"
    if (Test-Path $altPath) {
        $productsPath = $altPath
        Write-Host "  Using products-verified.json instead" -ForegroundColor DarkYellow
    } else {
        Write-Host "  [FAIL] Neither products.json nor products-verified.json found in data\" -ForegroundColor Red
        Write-Host "  Searched: $productsPath" -ForegroundColor DarkGray
        Write-Host "  Searched: $altPath" -ForegroundColor DarkGray
        # List what IS in data\
        $dataDir = Join-Path $ApiPath "data"
        if (Test-Path $dataDir) {
            Write-Host "  Files in data\:" -ForegroundColor DarkGray
            Get-ChildItem $dataDir -Filter "*.json" | ForEach-Object { Write-Host "    $($_.Name)" }
        }
        exit 1
    }
}

Write-Host "  Reading: $productsPath" -ForegroundColor DarkGray

# Backup first
$backupPath = $productsPath + ".bak-" + (Get-Date -Format 'yyyyMMdd-HHmmss')
Copy-Item $productsPath $backupPath -Force
Write-Host "  [OK] Backup: $backupPath" -ForegroundColor Green

# Read and parse JSON
$rawJson = Get-Content $productsPath -Raw -Encoding UTF8
$json = $rawJson | ConvertFrom-Json

# Check if guides already exist
$existing = $json.products | Where-Object { $_.id -eq "guide-working-in-china-2026-08" }
if ($existing) {
    Write-Host "  [OK] Guides already in products.json (skipping)" -ForegroundColor Green
} else {
    # Build 5 new product entries matching the existing format
    $guide1 = [PSCustomObject]@{
        id = "guide-working-in-china-2026-08"
        name = "外国人在华工作完全指南（2026年版）"
        name_en = "Working in China Guide for Foreigners (2026-08 Edition)"
        type = "guide"
        type_label = "🧭 指南/教程"
        type_label_en = "🧭 Guides / Tutorials"
        domain = @("employment", "china-data", "legal")
        domain_labels = @("💼 就业", "🇨🇳 中国数据", "⚖️ 法律")
        domain_labels_en = @("💼 Employment", "🇨🇳 China Data", "⚖️ Legal")
        description = "外国人在华工作全流程操作手册：Z签证→工作许可→居留许可→就业权利→五险一金→个税→离职争议→数据隐私合规。引用2024年公司法、PIPL/DSL/CSL三法、2025年司法解释二等最新法规。"
        description_en = "Complete 2026 operational manual for foreigners working in China: Z-visa, work permit, residence permit, employment rights, social insurance, IIT, contract termination, dispute resolution, and data privacy compliance."
        price = 0.01
        currency = "USDC"
        format = @("Markdown")
        endpoint = "/v1/assets/guide-working-in-china-2026-08"
        status = "available"
        published = "2026-08-16"
        source_file = "guides/guide-working-in-china-2026-08.md"
        province = $null
        sample_url = $null
        tags = @("来华工作", "就业", "签证", "工作许可", "居留许可", "法律指南")
        tags_en = @("working", "employment", "visa", "work-permit", "residence-permit", "legal-guide")
        shelf = "human"
        listed_at = "2026-08-16"
        payment_method = @("x402")
        sample = "preview"
        preview = "30pct"
        preview_files = @("guides/guide-working-in-china-2026-08-preview.md")
        delivery = "auto"
        missions = @("work")
    }

    $guide2 = [PSCustomObject]@{
        id = "guide-hiring-china-2026-08"
        name = "在华招聘与管理团队完全指南（2026年版）"
        name_en = "Hiring Employees and Managing Teams in China (2026-08 Edition)"
        type = "guide"
        type_label = "🧭 指南/教程"
        type_label_en = "🧭 Guides / Tutorials"
        domain = @("employment", "china-data", "legal")
        domain_labels = @("💼 就业", "🇨🇳 中国数据", "⚖️ 法律")
        domain_labels_en = @("💼 Employment", "🇨🇳 China Data", "⚖️ Legal")
        description = "在华招聘与管理团队合规与策略指南：招聘法律→合同必备条款→试用期→社保公积金→个税代扣→竞业限制（2025司法解释二）→解雇→遣散费（2N）→劳动仲裁全流程。"
        description_en = "Complete 2026 compliance and strategy guide for hiring and managing teams in China: recruitment law, mandatory contract terms, probation, social insurance, non-compete (2025 SPC Interpretation II), termination, severance (2N), labor arbitration."
        price = 0.01
        currency = "USDC"
        format = @("Markdown")
        endpoint = "/v1/assets/guide-hiring-china-2026-08"
        status = "available"
        published = "2026-08-16"
        source_file = "guides/guide-hiring-china-2026-08.md"
        province = $null
        sample_url = $null
        tags = @("招聘", "人力资源管理", "劳动法", "竞业限制", "遣散费", "劳动仲裁")
        tags_en = @("hiring", "hr", "employment-law", "non-compete", "severance", "labor-arbitration")
        shelf = "human"
        listed_at = "2026-08-16"
        payment_method = @("x402")
        sample = "preview"
        preview = "30pct"
        preview_files = @("guides/guide-hiring-china-2026-08-preview.md")
        delivery = "auto"
        missions = @("work", "invest")
    }

    $guide3 = [PSCustomObject]@{
        id = "guide-legal-rights-china-2026-08"
        name = "在华法律权利与消费者保护指南（2026年版）"
        name_en = "China Legal Rights & Consumer Protection Guide for Foreigners (2026-08 Edition)"
        type = "guide"
        type_label = "🧭 指南/教程"
        type_label_en = "🧭 Guides / Tutorials"
        domain = @("legal", "china-data")
        domain_labels = @("⚖️ 法律", "🇨🇳 中国数据")
        domain_labels_en = @("⚖️ Legal", "🇨🇳 China Data")
        description = "在华法律权利与消费者保护完全指南：消费者九大权利→12315投诉系统→租房纠纷→合同争议→电商维权→民事诉讼程序→证据清单→英中术语对照表。含2026年真实案例。"
        description_en = "Complete 2026 guide to legal rights and consumer protection in China: 9 consumer rights, 12315 complaint system, rental disputes, contract disputes, e-commerce rights, civil litigation procedure, and evidence checklist."
        price = 0.01
        currency = "USDC"
        format = @("Markdown")
        endpoint = "/v1/assets/guide-legal-rights-china-2026-08"
        status = "available"
        published = "2026-08-16"
        source_file = "guides/guide-legal-rights-china-2026-08.md"
        province = $null
        sample_url = $null
        tags = @("法律权利", "消费者保护", "12315", "租房纠纷", "合同", "诉讼")
        tags_en = @("legal-rights", "consumer-protection", "12315", "rental-dispute", "contract", "litigation")
        shelf = "human"
        listed_at = "2026-08-16"
        payment_method = @("x402")
        sample = "preview"
        preview = "30pct"
        preview_files = @("guides/guide-legal-rights-china-2026-08-preview.md")
        delivery = "auto"
        missions = @("visit", "work")
    }

    $guide4 = [PSCustomObject]@{
        id = "guide-study-in-china-2026-08"
        name = "国际学生在华学习指南（2026年版）"
        name_en = "Study in China Guide for International Students (2026-08 Edition)"
        type = "guide"
        type_label = "🧭 指南/教程"
        type_label_en = "🧭 Guides / Tutorials"
        domain = @("education", "china-data")
        domain_labels = @("📚 教育", "🇨🇳 中国数据")
        domain_labels_en = @("📚 Education", "🇨🇳 China Data")
        description = "国际学生在华学习完全指南：X1/X2签证→JW201/JW202表格→学习类居留许可→大学注册→奖学金类型（CSC/ISCC/省级）→实习政策→兼职规定→5个常见陷阱。"
        description_en = "Complete 2026 guide for international students in China: X1/X2 visa, JW201/JW202 forms, residence permit for study, university registration, scholarship types, internship policies, and common pitfalls."
        price = 0.01
        currency = "USDC"
        format = @("Markdown")
        endpoint = "/v1/assets/guide-study-in-china-2026-08"
        status = "available"
        published = "2026-08-16"
        source_file = "guides/guide-study-in-china-2026-08.md"
        province = $null
        sample_url = $null
        tags = @("留学", "国际学生", "X1签证", "JW201", "奖学金", "居留许可")
        tags_en = @("study", "international-students", "x1-visa", "jw201", "scholarship", "residence-permit")
        shelf = "human"
        listed_at = "2026-08-16"
        payment_method = @("x402")
        sample = "preview"
        preview = "30pct"
        preview_files = @("guides/guide-study-in-china-2026-08-preview.md")
        delivery = "auto"
        missions = @("visit", "study")
    }

    $guide5 = [PSCustomObject]@{
        id = "guide-business-compliance-china-2026-08"
        name = "外资企业在华合规指南（2026年版）"
        name_en = "China Business Compliance Guide for Foreign Companies (2026-08 Edition)"
        type = "guide"
        type_label = "🧭 指南/教程"
        type_label_en = "🧭 Guides / Tutorials"
        domain = @("legal", "china-data")
        domain_labels = @("⚖️ 法律", "🇨🇳 中国数据")
        domain_labels_en = @("⚖️ Legal", "🇨🇳 China Data")
        description = "外资企业WFOE在华合规操作手册：2024年公司法（5年实缴）→公司治理→CIT/VAT/预提税→PIPL/DSL数据合规→反不正当竞争→出口管制→年报公示→审计要求。含11个实操表格。"
        description_en = "Complete 2026 operational manual for WFOE compliance in China: 2024 Company Law (5-year paid-in capital), corporate governance, CIT/VAT/withholding tax, PIPL/DSL data compliance, anti-unfair competition, export control, and audit requirements."
        price = 0.01
        currency = "USDC"
        format = @("Markdown")
        endpoint = "/v1/assets/guide-business-compliance-china-2026-08"
        status = "available"
        published = "2026-08-16"
        source_file = "guides/guide-business-compliance-china-2026-08.md"
        province = $null
        sample_url = $null
        tags = @("企业合规", "WFOE", "公司法", "税务", "数据合规", "审计")
        tags_en = @("business-compliance", "wfoe", "company-law", "tax", "data-compliance", "audit")
        shelf = "human"
        listed_at = "2026-08-16"
        payment_method = @("x402")
        sample = "preview"
        preview = "30pct"
        preview_files = @("guides/guide-business-compliance-china-2026-08-preview.md")
        delivery = "auto"
        missions = @("invest")
    }

    # Add to products array
    $json.products += $guide1
    $json.products += $guide2
    $json.products += $guide3
    $json.products += $guide4
    $json.products += $guide5

    # Update total_products
    if ($json.total_products) {
        $json.total_products = $json.products.Count
        Write-Host "  Updated total_products to $($json.total_products)" -ForegroundColor DarkGray
    }

    # Write back with UTF8 encoding, preserve formatting
    $output = $json | ConvertTo-Json -Depth 10
    # PowerShell adds BOM with UTF8, use UTF8NoBOM if available
    try {
        [System.IO.File]::WriteAllText($productsPath, $output, [System.Text.UTF8Encoding]::new($false))
    } catch {
        $output | Out-File -FilePath $productsPath -Encoding UTF8 -Force
    }

    Write-Host "  [OK] Added 5 guides to products.json" -ForegroundColor Green
    Write-Host "  Total products now: $($json.products.Count)" -ForegroundColor DarkGray
}

Write-Host ""

# --- Step 2: Find and restart correct service ---
Write-Host "[2/3] Finding correct service name..." -ForegroundColor Yellow

$serviceFound = $false
$serviceName = ""

# Method 1: Try nssm list
Write-Host "  Trying nssm list..." -ForegroundColor DarkGray
try {
    $nssmOutput = & nssm list 2>$null
    foreach ($line in $nssmOutput) {
        $line = $line.ToString().Trim()
        if ($line -and $line -notmatch '^$' -and $line -ne "SUCCESS") {
            Write-Host "    Found: $line" -ForegroundColor DarkGray
            if ($line -match 'agent|bridge|afie|api|proxy|uvicorn|fastapi') {
                $serviceName = $line
            }
        }
    }
} catch {
    Write-Host "    nssm list not available" -ForegroundColor DarkGray
}

# Method 2: sc.exe query
if (-not $serviceName) {
    Write-Host "  Trying sc.exe query..." -ForegroundColor DarkGray
    $scOutput = & sc.exe query type= service state= all 2>$null
    $inService = $false
    $currentName = ""
    foreach ($line in $scOutput) {
        $line = $line.ToString().Trim()
        if ($line -match "SERVICE_NAME:\s*(.+)") {
            $currentName = $Matches[1].Trim()
            if ($currentName -match 'agent|bridge|afie|api|proxy|uvicorn|fastapi|python') {
                Write-Host "    Candidate: $currentName" -ForegroundColor DarkGray
                $serviceName = $currentName
            }
        }
    }
}

# Method 3: Get-Service
if (-not $serviceName) {
    Write-Host "  Trying Get-Service..." -ForegroundColor DarkGray
    $allServices = Get-Service | Where-Object { $_.Name -match 'agent|bridge|afie|api|proxy|uvicorn|fastapi|python' -or $_.DisplayName -match 'agent|bridge|afie|api|proxy|uvicorn|fastapi|python' }
    foreach ($svc in $allServices) {
        Write-Host "    Found service: $($svc.Name) - $($svc.Status) - $($svc.DisplayName)" -ForegroundColor DarkGray
        $serviceName = $svc.Name
    }
}

# Method 4: Check common names
if (-not $serviceName) {
    Write-Host "  Trying common service names..." -ForegroundColor DarkGray
    $commonNames = @("afie_proxy", "afie-proxy", "afie", "AgentBridge", "agentbridge", "AgentBridgeAPI", "AgentBridge-API", "agentbridge-api", "api-server", "apiserver", "uvicorn", "fastapi")
    foreach ($name in $commonNames) {
        try {
            $test = & sc.exe query $name 2>$null
            if ($test -and ($test -match "SERVICE_NAME" -or $test -match "STATE")) {
                Write-Host "    Found: $name" -ForegroundColor DarkGray
                $serviceName = $name
                break
            }
        } catch {}
    }
}

if ($serviceName) {
    Write-Host "  [OK] Service found: $serviceName" -ForegroundColor Green
    Write-Host "  Restarting..." -ForegroundColor Yellow
    try {
        & nssm restart $serviceName 2>$null
        Write-Host "  [OK] Service restarted via nssm" -ForegroundColor Green
        $serviceFound = $true
    } catch {
        Write-Host "  nssm restart failed, trying sc.exe..." -ForegroundColor DarkGray
        try {
            & sc.exe stop $serviceName 2>$null
            Start-Sleep -Seconds 2
            & sc.exe start $serviceName 2>$null
            Write-Host "  [OK] Service restarted via sc.exe" -ForegroundColor Green
            $serviceFound = $true
        } catch {
            Write-Host "  [FAIL] Could not restart service" -ForegroundColor Red
            Write-Host "  Try manually: nssm restart $serviceName" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "  [WARN] Could not auto-detect service name" -ForegroundColor DarkYellow
    Write-Host "  Listing ALL services for manual inspection:" -ForegroundColor DarkGray
    $allSvc = & sc.exe query type= service state= all 2>$null
    foreach ($line in $allSvc) {
        $line = $line.ToString().Trim()
        if ($line -match "SERVICE_NAME:\s*(.+)") {
            $sname = $Matches[1].Trim()
            Write-Host "    $sname" -ForegroundColor DarkGray
        }
    }
    Write-Host ""
    Write-Host "  Try: nssm restart <service-name>" -ForegroundColor Yellow
}

Write-Host ""

# --- Step 3: Verify ---
Write-Host "[3/3] Verifying..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

# Check products.json
try {
    $prodFile = Get-Content $productsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $guideCount = ($prodFile.products | Where-Object { $_.id -match "^guide-" }).Count
    $total = $prodFile.products.Count
    Write-Host "  [OK] products.json: $total products ($guideCount guides)" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] products.json parse error: $($_.Exception.Message)" -ForegroundColor DarkYellow
}

# Check API endpoints
$baseUrl = "http://localhost:8000"

try {
    $resp = Invoke-WebRequest -Uri "$baseUrl/health" -UseBasicParsing -TimeoutSec 10
    Write-Host "  [OK] /health: $($resp.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] /health check failed: $($_.Exception.Message)" -ForegroundColor DarkYellow
}

try {
    $resp = Invoke-WebRequest -Uri "$baseUrl/llms.txt" -UseBasicParsing -TimeoutSec 10
    $lines = ($resp.Content -split "`n").Count
    Write-Host "  [OK] /llms.txt: $lines lines" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] /llms.txt check failed" -ForegroundColor DarkYellow
}

try {
    $resp = Invoke-WebRequest -Uri "$baseUrl/openapi.json" -UseBasicParsing -TimeoutSec 10
    $spec = $resp.Content | ConvertFrom-Json
    $enumCount = $spec.paths."/v1/assets/{asset_id}".get.parameters[0].schema.enum.Count
    Write-Host "  [OK] /openapi.json: $enumCount assets in enum" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] /openapi.json check failed" -ForegroundColor DarkYellow
}

try {
    $resp = Invoke-WebRequest -Uri "$baseUrl/catalog.json" -UseBasicParsing -TimeoutSec 10
    $cat = $resp.Content | ConvertFrom-Json
    Write-Host "  [OK] /catalog.json: $($cat.assets.Count) assets" -ForegroundColor Green
} catch {
    Write-Host "  [WARN] /catalog.json check failed" -ForegroundColor DarkYellow
}

# Check each new guide asset
$guideIds = @(
    "guide-working-in-china-2026-08",
    "guide-hiring-china-2026-08",
    "guide-legal-rights-china-2026-08",
    "guide-study-in-china-2026-08",
    "guide-business-compliance-china-2026-08"
)

foreach ($gid in $guideIds) {
    try {
        $resp = Invoke-WebRequest -Uri "$baseUrl/v1/assets/$gid" -UseBasicParsing -TimeoutSec 10
        Write-Host "  [OK] /v1/assets/$gid : $($resp.StatusCode)" -ForegroundColor Green
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if ($statusCode -eq 402) {
            Write-Host "  [OK] /v1/assets/$gid : 402 (payment required - asset exists!)" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] /v1/assets/$gid : $($_.Exception.Message)" -ForegroundColor DarkYellow
        }
    }
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "If service was not found, try these commands:" -ForegroundColor Yellow
Write-Host "  sc.exe query type= service state= all | findstr /i agent" -ForegroundColor DarkGray
Write-Host "  sc.exe query type= service state= all | findstr /i afie" -ForegroundColor DarkGray
Write-Host "  sc.exe query type= service state= all | findstr /i bridge" -ForegroundColor DarkGray
Write-Host "  sc.exe query type= service state= all | findstr /i python" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Then: nssm restart <service-name>" -ForegroundColor Yellow
