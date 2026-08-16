param([string]$ApiPath = "F:\afie_proxy")

$mainPy = Join-Path $ApiPath "main.py"
$lines = Get-Content $mainPy

Write-Host "=== ASSETS dict structure (lines 120-160) ===" -ForegroundColor Cyan
for ($i = 119; $i -lt 160 -and $i -lt $lines.Count; $i++) {
    $ln = $i + 1
    Write-Host "  ${ln}: $($lines[$i])"
}

Write-Host ""
Write-Host "=== openapi route (lines 463-475) ===" -ForegroundColor Cyan
for ($i = 462; $i -lt 475 -and $i -lt $lines.Count; $i++) {
    $ln = $i + 1
    Write-Host "  ${ln}: $($lines[$i])"
}

Write-Host ""
Write-Host "=== llms.txt route (lines 723-745) ===" -ForegroundColor Cyan
for ($i = 722; $i -lt 745 -and $i -lt $lines.Count; $i++) {
    $ln = $i + 1
    Write-Host "  ${ln}: $($lines[$i])"
}

Write-Host ""
Write-Host "=== _load_atlas_json function ===" -ForegroundColor Cyan
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '_load_atlas_json') {
        $start = [Math]::Max(0, $i - 2)
        $end = [Math]::Min($lines.Count - 1, $i + 15)
        for ($j = $start; $j -le $end; $j++) {
            $ln = $j + 1
            Write-Host "  ${ln}: $($lines[$j])"
        }
        Write-Host "  ---"
    }
}

Write-Host ""
Write-Host "=== docs/ directory check ===" -ForegroundColor Cyan
$docsDir = Join-Path $ApiPath "docs"
if (Test-Path $docsDir) {
    Write-Host "docs/ exists"
    $docsItems = Get-ChildItem $docsDir -Filter "*.json" -ErrorAction SilentlyContinue
    foreach ($item in $docsItems) {
        Write-Host "  $($item.Name) - $($item.Length) bytes"
    }
    $docsLlms = Join-Path $docsDir "llms.txt"
    if (Test-Path $docsLlms) {
        $llmsLines = (Get-Content $docsLlms).Count
        Write-Host "  docs/llms.txt - $llmsLines lines"
    } else {
        Write-Host "  docs/llms.txt - NOT FOUND"
    }
} else {
    Write-Host "docs/ does NOT exist"
}

Write-Host ""
Write-Host "=== base_dir definition ===" -ForegroundColor Cyan
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match 'base_dir\s*=') {
        $ln = $i + 1
        Write-Host "  ${ln}: $($lines[$i])"
    }
}
