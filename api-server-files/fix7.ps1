# AgentBridge Fix7 - Repair main.py encoding (ASCII-only Python script)
# Usage:
#   irm "https://raw.githubusercontent.com/tianzizhiming-svg/agentbridge/master/api-server-files/fix7.ps1" -OutFile "$env:TEMP\fix7.ps1"
#   powershell -ExecutionPolicy Bypass -File "$env:TEMP\fix7.ps1"

param([string]$ApiPath = "F:\afie_proxy")

Write-Host "=== AgentBridge Fix7 (Encoding Repair v2) ===" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Kill stuck service ---
Write-Host "[1/4] Killing stuck service..." -ForegroundColor Yellow

Get-Process -Name "python" -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmd = (Get-WmiObject Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
        if ($cmd -match "main.py" -or $cmd -match "afie") {
            Write-Host "  Killing PID $($_.Id)" -ForegroundColor DarkGray
            Stop-Process -Id $_.Id -Force
        }
    } catch {}
}
& sc.exe stop AgentBridge 2>$null
Start-Sleep -Seconds 3
Write-Host "  [OK] Done" -ForegroundColor Green

Write-Host ""

# --- Step 2: Find all backups of main.py ---
Write-Host "[2/4] Looking for main.py backups..." -ForegroundColor Yellow

$mainPy = Join-Path $ApiPath "main.py"

# List all backup files
$allBackups = @()
$allBackups += Get-ChildItem $ApiPath -Filter "main.py*" | Where-Object { $_.Name -ne "main.py" }
$dataDir = Join-Path $ApiPath "data"
if (Test-Path $dataDir) {
    $allBackups += Get-ChildItem $dataDir -Filter "main.py*" -ErrorAction SilentlyContinue
}

Write-Host "  Found backups:" -ForegroundColor DarkGray
foreach ($b in $allBackups) {
    Write-Host "    $($b.FullName) ($($b.Length) bytes, $($b.LastWriteTime))" -ForegroundColor DarkGray
}

Write-Host ""

# --- Step 3: Try to fix encoding via Python ---
Write-Host "[3/4] Fixing main.py encoding..." -ForegroundColor Yellow

# Create a pure ASCII Python script
$pyCode = @'
import sys
import os

path = sys.argv[1]
backups_dir = sys.argv[2]

print(f"  Target: {path}")

# Read the corrupted file as bytes
with open(path, "rb") as f:
    raw = f.read()

# Remove BOM if present
if raw[:3] == b"\xef\xbb\xbf":
    raw = raw[3:]
    print("  BOM removed")

# Try to decode as UTF-8
try:
    text = raw.decode("utf-8")
    print("  Decoded as UTF-8 OK")
except:
    print("  WARNING: Not valid UTF-8, trying latin-1")
    text = raw.decode("latin-1")

# Strategy 1: Reverse GBK mojibake
# Corruption was: original UTF-8 bytes -> read as GBK -> written as UTF-8
# Reverse: encode current text as GBK -> decode as UTF-8
strategies = []

# Try GBK reversal
try:
    reversed_bytes = text.encode("gbk", errors="replace")
    reversed_text = reversed_bytes.decode("utf-8", errors="replace")
    # Count CJK characters
    cjk_original = sum(1 for c in text if 0x4e00 <= ord(c) <= 0x9fff)
    cjk_reversed = sum(1 for c in reversed_text if 0x4e00 <= ord(c) <= 0x9fff)
    strategies.append(("GBK", reversed_text, cjk_original, cjk_reversed))
    print(f"  Strategy GBK: CJK {cjk_original} -> {cjk_reversed}")
except Exception as e:
    print(f"  Strategy GBK failed: {e}")

# Try latin-1 reversal
try:
    reversed_bytes = text.encode("latin-1", errors="replace")
    reversed_text_l1 = reversed_bytes.decode("utf-8", errors="replace")
    cjk_reversed_l1 = sum(1 for c in reversed_text_l1 if 0x4e00 <= ord(c) <= 0x9fff)
    strategies.append(("latin-1", reversed_text_l1, cjk_original, cjk_reversed_l1))
    print(f"  Strategy latin-1: CJK {cjk_original} -> {cjk_reversed_l1}")
except Exception as e:
    print(f"  Strategy latin-1 failed: {e}")

# Try cp1252 reversal
try:
    reversed_bytes = text.encode("cp1252", errors="replace")
    reversed_text_c = reversed_bytes.decode("utf-8", errors="replace")
    cjk_reversed_c = sum(1 for c in reversed_text_c if 0x4e00 <= ord(c) <= 0x9fff)
    strategies.append(("cp1252", reversed_text_c, cjk_original, cjk_reversed_c))
    print(f"  Strategy cp1252: CJK {cjk_original} -> {cjk_reversed_c}")
except Exception as e:
    print(f"  Strategy cp1252 failed: {e}")

# Pick the best strategy (most CJK chars + valid Python)
best_text = None
best_name = None
best_cjk = 0

for name, candidate, cjk_orig, cjk_rev in strategies:
    if cjk_rev <= best_cjk:
        continue
    # Test if it's valid Python
    try:
        compile(candidate, path, "exec")
        best_text = candidate
        best_name = name
        best_cjk = cjk_rev
        print(f"  {name}: valid Python, {cjk_rev} CJK chars")
    except SyntaxError as e:
        print(f"  {name}: SyntaxError at line {e.lineno}: {e.msg}")
        # Even if syntax error, keep it if it has more CJK (partial fix)
        if cjk_rev > best_cjk:
            best_text = candidate
            best_name = name
            best_cjk = cjk_rev

if best_text and best_name:
    # Write the best candidate
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(best_text)
    print(f"  [OK] Wrote {best_name} reversed version ({best_cjk} CJK chars)")

    # Verify syntax
    try:
        compile(best_text, path, "exec")
        print("  [OK] Syntax verification passed!")
        sys.exit(0)
    except SyntaxError as e:
        print(f"  [WARN] Still has syntax error at line {e.lineno}: {e.msg}")
        print(f"  Line content: {e.text}")
        # Try to show the problematic line
        lines = best_text.split("\n")
        if e.lineno and e.lineno <= len(lines):
            print(f"  Line {e.lineno}: {lines[e.lineno-1][:200]}")
        sys.exit(1)
else:
    print("  [FAIL] No strategy produced better results")
    print("  The file may need manual repair or restoring from git")
    sys.exit(2)
'@

$pyTmp = Join-Path $env:TEMP "ab_fix7.py"
[System.IO.File]::WriteAllText($pyTmp, $pyCode, [System.Text.UTF8Encoding]::new($false))

# Backup current (corrupted) file
$corruptBak = $mainPy + ".corrupt-bak"
Copy-Item $mainPy $corruptBak -Force

$pyResult = & python $pyTmp $mainPy $ApiPath 2>&1
foreach ($line in $pyResult) {
    Write-Host "  $line" -ForegroundColor DarkGray
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Encoding fixed and verified" -ForegroundColor Green
} else {
    Write-Host "  [WARN] Auto-fix incomplete (exit $LASTEXITCODE)" -ForegroundColor DarkYellow
    Write-Host ""

    # Check if there's a git repo we can restore from
    $gitDir = Join-Path $ApiPath ".git"
    if (Test-Path $gitDir) {
        Write-Host "  Found .git in $ApiPath, trying git checkout..." -ForegroundColor DarkYellow
        Set-Location $ApiPath
        $gitResult = & git checkout -- main.py 2>&1
        Write-Host "  git: $gitResult" -ForegroundColor DarkGray
    } else {
        # Try to find a working backup by testing each one
        Write-Host "  Testing backup files..." -ForegroundColor DarkYellow
        foreach ($b in $allBackups) {
            $testResult = & python -c "import py_compile; py_compile.compile(r'$($b.FullName)', doraise=True)" 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  [OK] Working backup found: $($b.FullName)" -ForegroundColor Green
                Copy-Item $b.FullName $mainPy -Force
                Write-Host "  [OK] Restored from backup" -ForegroundColor Green
                break
            } else {
                Write-Host "  [FAIL] $($b.Name) - has syntax errors" -ForegroundColor DarkGray
            }
        }
    }
}

Write-Host ""

# --- Step 4: Start service ---
Write-Host "[4/4] Starting service..." -ForegroundColor Yellow

# Final syntax check
$syntaxCheck = & python -c "import py_compile; py_compile.compile(r'$mainPy', doraise=True)" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [FAIL] main.py still has syntax errors:" -ForegroundColor Red
    Write-Host "  $syntaxCheck" -ForegroundColor DarkRed
    Write-Host ""
    Write-Host "  Manual repair needed. Check line numbers in error above." -ForegroundColor Yellow
    exit 1
}

Write-Host "  [OK] Syntax OK" -ForegroundColor Green

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
        $r = Invoke-WebRequest -Uri "http://localhost:8000/llms.txt" -UseBasicParsing -TimeoutSec 10
        $lc = ($r.Content -split "`n").Count
        Write-Host "  [OK] /llms.txt: $lc lines" -ForegroundColor Green
    } catch { Write-Host "  [WARN] /llms.txt failed" -ForegroundColor DarkYellow }

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
                Write-Host "  [OK] /v1/assets/$gid : 402 (exists!)" -ForegroundColor Green
            } else {
                Write-Host "  [WARN] /v1/assets/$gid" -ForegroundColor DarkYellow
            }
        }
    }
} else {
    Write-Host "  [FAIL] Service not responding" -ForegroundColor Red
    Write-Host "  Try: cd $ApiPath; python main.py" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Cyan
