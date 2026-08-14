param(
    [string]$TargetRoot = "D:\Projects\EnterpriseSQLCopilot",
    [string]$ModelRoot = "D:\AIModels",
    [switch]$CopyProject
)

$ErrorActionPreference = "Stop"
$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

$runtimeDirs = @(
    $TargetRoot,
    $ModelRoot,
    (Join-Path $TargetRoot ".runtime"),
    (Join-Path $TargetRoot ".runtime\cache"),
    (Join-Path $TargetRoot ".runtime\cache\faiss"),
    (Join-Path $TargetRoot ".runtime\cache\npm"),
    (Join-Path $TargetRoot ".runtime\cache\pip"),
    (Join-Path $TargetRoot ".runtime\logs"),
    (Join-Path $TargetRoot ".runtime\sqlite"),
    (Join-Path $TargetRoot ".runtime\tmp"),
    (Join-Path $ModelRoot "huggingface"),
    (Join-Path $ModelRoot "huggingface\transformers"),
    (Join-Path $ModelRoot "torch"),
    (Join-Path $ModelRoot "rl")
)

foreach ($dir in $runtimeDirs) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

$sourceRlModel = Join-Path $SourceRoot "rl\models\sql_ppo_agent.zip"
if (Test-Path -LiteralPath $sourceRlModel) {
    Copy-Item -LiteralPath $sourceRlModel -Destination (Join-Path $ModelRoot "rl\sql_ppo_agent.zip") -Force
}

if ($CopyProject) {
    $sourceFull = [System.IO.Path]::GetFullPath($SourceRoot).TrimEnd("\")
    $targetFull = [System.IO.Path]::GetFullPath($TargetRoot).TrimEnd("\")
    if ($sourceFull -ieq $targetFull) {
        Write-Host "Source and target are the same folder; skipping copy."
        exit 0
    }
    $excludeDirs = @(
        ".next",
        ".pytest_cache",
        ".runtime",
        "__pycache__",
        "node_modules",
        "frontend\node_modules",
        "frontend\.next",
        "frontend\playwright-report",
        "frontend\test-results",
        "logs",
        "playwright-report",
        "reports",
        "reports_test",
        "test-results"
    )
    $excludeFiles = @("*.db", "*.db-*", "*.sqlite", "*.sqlite-*", "*.sqlite3", "*.sqlite3-*", "*.log")
    robocopy $SourceRoot $TargetRoot /E /XD $excludeDirs /XF $excludeFiles
    if ($LASTEXITCODE -gt 7) {
        throw "Project copy failed with robocopy exit code $LASTEXITCODE"
    }
}

Write-Host "Prepared runtime folders under $TargetRoot and $ModelRoot."
if ($CopyProject) {
    Write-Host "Project files copied to $TargetRoot. Install dependencies from the copied folder."
} else {
    Write-Host "Run with -CopyProject to copy source files without generated caches."
}
