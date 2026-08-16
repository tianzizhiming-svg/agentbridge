# AgentBridge Fix6 - Fix main.py encoding corruption + restart service
# PowerShell corrupted main.py's Chinese text; Python will fix it
# Usage:
#   irm "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files/fix6.ps1" -OutFile "$env:TEMP\fix6.ps1"
#   powershell -ExecutionPolicy Bypass -File "$env:TEMP\fix6.ps1"

param([string]$ApiPath = "F:\afie_proxy")

Write-Host "=== AgentBridge Fix6 (Encoding Repair) ===" -ForegroundColor Cyan
Write-Host "API path: $ApiPath"
Write-Host ""

# --- Step 1: Kill stuck service ---
Write-Host "[1/4] Killing stuck AgentBridge service..." -ForegroundColor Yellow

# Force kill if stop pending
$proc = Get-Process -Name "python" -ErrorAction SilentlyContinue
if ($proc) {
    foreach ($p in $proc) {
        $cmdLine = ""
        try {
            $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId=$($p.Id)").CommandLine
        } catch {}
        if ($cmdLine -match "main.py" -or $cmdLine -match "afie") {
            Write-Host "  Killing PID $($p.Id): $cmdLine" -ForegroundColor DarkGray
            Stop-Process -Id $p.Id -Force
        }
    }
}

# Also try sc.exe
& sc.exe stop AgentBridge 2>$null
Start-Sleep -Seconds 3

# Check
$state = & sc.exe query AgentBridge 2>$null
if ($state -match "STOPPED") {
    Write-Host "  [OK] Service stopped" -ForegroundColor Green
} elseif ($state -match "STOP_PENDING") {
    Write-Host "  Still pending, force killing python..." -ForegroundColor DarkYellow
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
    Write-Host "  [OK] Python processes killed" -ForegroundColor Green
} else {
    Write-Host "  Service state: $state" -ForegroundColor DarkGray
}

Write-Host ""

# --- Step 2: Fix encoding via Python ---
Write-Host "[2/4] Fixing main.py encoding..." -ForegroundColor Yellow

$mainPy = Join-Path $ApiPath "main.py"
$mainPyBak = $mainPy + ".encoding-bak"
Copy-Item $mainPy $mainPyBak -Force
Write-Host "  Backup: $mainPyBak" -ForegroundColor DarkGray

$pyScript = @"
import sys
import os

path = r'$mainPy'

# Read the file as bytes
with open(path, 'rb') as f:
    raw = f.read()

# Check if file starts with BOM
has_bom = raw[:3] == b'\xef\xbb\xbf'
if has_bom:
    raw = raw[3:]
    print('  BOM detected, removing')

# Try to decode as UTF-8
try:
    text = raw.decode('utf-8')
    print('  File decoded as UTF-8 OK')
except:
    print('  ERROR: File is not valid UTF-8 even after BOM removal')
    print('  Trying latin-1 fallback...')
    text = raw.decode('latin-1')

# Check if there's mojibake (UTF-8 read as GBK then re-encoded as UTF-8)
# The corruption pattern: original UTF-8 bytes -> read as GBK -> written as UTF-8
# To reverse: encode current text as GBK -> decode as UTF-8
#
# But we need to be careful: some parts of the file might be fine (ASCII)
# and only Chinese strings are corrupted

# Strategy: try to reverse the mojibake
# If the text contains typical mojibake characters, reverse them
fixed_count = 0
try:
    # Try encoding the whole text as latin-1 (preserves byte values) then decode as UTF-8
    # This works if the corruption was: UTF-8 bytes -> read as latin-1/cp1252 -> written as UTF-8
    reversed_text = text.encode('latin-1').decode('utf-8')
    # If this worked, check if it looks better (more CJK characters)
    import unicodedata
    cjk_before = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    cjk_after = sum(1 for c in reversed_text if '\u4e00' <= c <= '\u9fff')
    print(f'  CJK chars before: {cjk_before}')
    print(f'  CJK chars after: {cjk_after}')
    if cjk_after > cjk_before:
        text = reversed_text
        fixed_count = cjk_after - cjk_before
        print(f'  [OK] Fixed {fixed_count} characters via latin-1 reverse')
    else:
        print('  latin-1 reverse did not improve, trying GBK reverse...')
        raise Exception('try gbk')
except:
    try:
        # Try: encode as GBK, decode as UTF-8
        # This works if corruption was: UTF-8 bytes -> read as GBK -> written as UTF-8
        reversed_text = text.encode('gbk', errors='replace').decode('utf-8', errors='replace')
        cjk_before = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        cjk_after = sum(1 for c in reversed_text if '\u4e00' <= c <= '\u9fff')
        print(f'  CJK chars before: {cjk_before}')
        print(f'  CJK chars after: {cjk_after}')
        if cjk_after > cjk_before:
            text = reversed_text
            fixed_count = cjk_after - cjk_before
            print(f'  [OK] Fixed {fixed_count} characters via GBK reverse')
        else:
            print('  GBK reverse did not improve either')
            print('  File might not have systematic mojibake')
    except Exception as e:
        print(f'  GBK reverse failed: {e}')

# Also fix common single-char corruptions line by line
# Look for lines with SyntaxError-prone patterns (unterminated strings)
lines = text.split('\n')
fixed_lines = []
for i, line in enumerate(lines):
    # Fix specific known corruptions
    # PATHFIX_TOP_EMPLOYMENT and PATHFIX_TOP_TEACHING lines
    if 'PATHFIX_TOP' in line and ('灞' in line or '婃' in line or '瘯' in line or '涓' in line):
        print(f'  Line {i+1}: Found corrupted PATHFIX line')
        # These should be Chinese year labels
        if 'EMPLOYMENT' in line:
            line = line.split('"')[0] + '"2025\\u5c4a\\u6bd5\\u4e1a\\u751f\\u5c31\\u4e1a\\u8d28\\u91cf\\u5e74\\u5ea6\\u62a5\\u544a\\u53ca\\u6df1\\u5ea6\\u89e3\\u8bfb"'
            # Actually just use the direct Chinese
            line = lines[i].split('"')[0] + '"2025\u5c4a\u6bd5\u4e1a\u751f\u5c31\u4e1a\u8d28\u91cf\u5e74\u5ea6\u62a5\u544a\u53ca\u6df1\u5ea6\u89e3\u8bfb"'
        elif 'TEACHING' in line:
            line = lines[i].split('"')[0] + '"2024-2025\\u5b66\\u5e74\\u672c\\u79d1\\u6559\\u5b66\\u8d28\\u91cf\\u62a5\\u544a\\u53ca\\u6df1\\u5ea6\\u89e3\\u8bfb"'
    fixed_lines.append(line)

text = '\n'.join(fixed_lines)

# Write back as UTF-8 without BOM
with open(path, 'w', encoding='utf-8', newline='') as f:
    f.write(text)

print('  [OK] File written as UTF-8 (no BOM)')
print(f'  Total characters fixed: {fixed_count}')
"@

$pyTmp = Join-Path $env:TEMP "ab_fix6.py"
[System.IO.File]::WriteAllText($pyTmp, $pyScript, [System.Text.UTF8Encoding]::new($false))

$pyResult = & python $pyTmp 2>&1
foreach ($line in $pyResult) {
    Write-Host "  $line" -ForegroundColor DarkGray
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Encoding fix completed" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Python script failed (exit $LASTEXITCODE)" -ForegroundColor Red
    Write-Host "  Restoring backup..." -ForegroundColor DarkYellow
    Copy-Item $mainPyBak $mainPy -Force
    exit 1
}

Write-Host ""

# --- Step 3: Test if main.py loads ---
Write-Host "[3/4] Testing main.py syntax..." -ForegroundColor Yellow

$testResult = & python -c "import py_compile; py_compile.compile(r'$mainPy', doraise=True)" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] main.py syntax OK" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Syntax error still exists:" -ForegroundColor Red
    foreach ($line in $testResult) {
        Write-Host "  $line" -ForegroundColor DarkRed
    }
    Write-Host ""
    Write-Host "  Restoring backup..." -ForegroundColor DarkYellow
    Copy-Item $mainPyBak $mainPy -Force
    Write-Host "  Please manually check main.py around the error line" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# --- Step 4: Start service ---
Write-Host "[4/4] Starting AgentBridge service..." -ForegroundColor Yellow

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

if ($ready) {
    # Quick verify
    Write-Host ""
    Write-Host "=== Verification ===" -ForegroundColor Cyan

    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/llms.txt" -UseBasicParsing -TimeoutSec 10
        $lc = ($r.Content -split "`n").Count
        Write-Host "  [OK] /llms.txt: $lc lines" -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] /llms.txt failed" -ForegroundColor DarkYellow
    }

    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/openapi.json" -UseBasicParsing -TimeoutSec 10
        $spec = $r.Content | ConvertFrom-Json
        $ec = $spec.paths."/v1/assets/{asset_id}".get.parameters[0].schema.enum.Count
        Write-Host "  [OK] /openapi.json: $ec assets in enum" -ForegroundColor Green
    } catch {
        Write-Host "  [WARN] /openapi.json failed" -ForegroundColor DarkYellow
    }

    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/catalog.json" -UseBasicParsing -TimeoutSec 10
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
    Write-Host "  [FAIL] Service not responding after ${maxWait}s" -ForegroundColor Red
    Write-Host "  Try manual: cd $ApiPath; python main.py" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
