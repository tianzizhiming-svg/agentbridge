param([string]$ApiPath = "F:\afie_proxy")

Write-Host "=== Diagnostic ===" -ForegroundColor Cyan

# Check disk files
Write-Host ""
Write-Host "--- Disk Files ---"
$llmsPath = Join-Path $ApiPath "llms.txt"
if (Test-Path $llmsPath) {
    $lines = (Get-Content $llmsPath).Count
    Write-Host "llms.txt on disk: $lines lines"
    Get-Content $llmsPath | Select-Object -First 3
} else {
    Write-Host "llms.txt NOT on disk at $llmsPath"
}

$openapiPath = Join-Path $ApiPath "openapi.json"
if (Test-Path $openapiPath) {
    $content = Get-Content $openapiPath -Raw
    $enumCount = ([regex]::Matches($content, '"api-policy"')).Count
    Write-Host "openapi.json on disk: exists, size=$($content.Length) chars"
} else {
    Write-Host "openapi.json NOT on disk at $openapiPath"
}

$catalogPath = Join-Path $ApiPath "catalog.json"
if (Test-Path $catalogPath) {
    $content = Get-Content $catalogPath -Raw
    Write-Host "catalog.json on disk: exists, size=$($content.Length) chars"
} else {
    Write-Host "catalog.json NOT on disk at $catalogPath"
}

# Search main.py for how these are served
Write-Host ""
Write-Host "--- main.py Analysis ---"
$mainPy = Join-Path $ApiPath "main.py"
if (Test-Path $mainPy) {
    $lines = Get-Content $mainPy
    Write-Host "main.py: $($lines.Count) lines"
    Write-Host ""
    
    # Find llms.txt references
    Write-Host "llms.txt references in main.py:"
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match 'llms\.txt' -or $lines[$i] -match 'llms_text' -or $lines[$i] -match 'LLMS') {
            $ln = $i + 1
            $text = $lines[$i].Trim()
            Write-Host "  line ${ln}: $text"
        }
    }
    
    Write-Host ""
    # Find openapi references
    Write-Host "openapi references in main.py:"
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match 'openapi' -or $lines[$i] -match 'OpenAPI' -or $lines[$i] -match 'swagger') {
            $ln = $i + 1
            $text = $lines[$i].Trim()
            Write-Host "  line ${ln}: $text"
        }
    }
    
    Write-Host ""
    # Find catalog references
    Write-Host "catalog references in main.py:"
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match 'catalog' -or $lines[$i] -match 'CATALOG') {
            $ln = $i + 1
            $text = $lines[$i].Trim()
            Write-Host "  line ${ln}: $text"
        }
    }
    
    Write-Host ""
    # Find ASSETS dict
    Write-Host "ASSETS dict in main.py:"
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match 'ASSETS\s*=' -or $lines[$i] -match 'ASSETS\s*:') {
            $ln = $i + 1
            $text = $lines[$i].Trim()
            Write-Host "  line ${ln}: $text"
            # Show next 5 lines
            for ($j = 1; $j -le 5 -and ($i+$j) -lt $lines.Count; $j++) {
                $ln2 = $i + $j + 1
                $text2 = $lines[$i+$j].Trim()
                Write-Host "  line ${ln2}: $text2"
            }
            break
        }
    }
    
    Write-Host ""
    # Find enum definition
    Write-Host "enum definition in main.py:"
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match 'enum' -and $lines[$i] -match 'api-policy') {
            $ln = $i + 1
            $text = $lines[$i].Trim()
            Write-Host "  line ${ln}: $text"
        }
        if ($lines[$i] -match 'enum' -and ($lines[$i] -match 'brief-' -or $lines[$i] -match 'guide-')) {
            $ln = $i + 1
            $text = $lines[$i].Trim()
            Write-Host "  line ${ln}: $text"
        }
    }
    
    Write-Host ""
    # Find guide-working to check if assets were added
    Write-Host "guide-working-in-china in main.py:"
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match 'guide-working-in-china') {
            $ln = $i + 1
            $text = $lines[$i].Trim()
            Write-Host "  line ${ln}: $text"
            $found = $true
        }
    }
    if (-not $found) {
        Write-Host "  NOT FOUND - assets were not added to main.py"
    }
    
} else {
    Write-Host "main.py not found at $mainPy"
}
