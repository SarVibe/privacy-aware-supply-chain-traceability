[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("YES")]
    [string]$ConfirmReset,

    [switch]$SkipBackup,
    [switch]$StartApp
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$AnvilExecutable = Join-Path $ProjectRoot ".tools\foundry\anvil.exe"
$PythonExecutable = Join-Path $ProjectRoot "backend\venv313\Scripts\python.exe"
$StatePath = Join-Path $ProjectRoot "backend\data\anvil-state.json"
$DeploymentPath = Join-Path $ProjectRoot "backend\data\pharmachain-deployment.json"
$ChainId = 131277322940537
$Mnemonic = "test test test test test test test test test test test junk"

if (-not (Test-Path $AnvilExecutable)) {
    throw "Anvil executable not found at $AnvilExecutable"
}

Write-Warning "This permanently deletes all on-chain transactions, blocks, product records, roles, and deployed contracts in the local Anvil state."
Write-Warning "A normal application restart does not use reset. Continue only if you intentionally want a fresh experiment."

New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot "backend\data") | Out-Null

if (-not $SkipBackup) {
    $BackupName = "anvil-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss")
    $BackupDirectory = Join-Path $ProjectRoot ("backend\backups\" + $BackupName)
    New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null

    foreach ($PathToBackUp in @($StatePath, $DeploymentPath)) {
        if (Test-Path $PathToBackUp) {
            Copy-Item -LiteralPath $PathToBackUp -Destination $BackupDirectory -Force
        }
    }
    Write-Host "Backup saved to $BackupDirectory"
}

$PortsToStop = @(5173, 8546)
$ProcessIds = foreach ($Port in $PortsToStop) {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
}

foreach ($ProcessId in ($ProcessIds | Sort-Object -Unique)) {
    Stop-Process -Id $ProcessId -Force
}

if (Test-Path $StatePath) {
    Remove-Item -LiteralPath $StatePath -Force
}
if (Test-Path $DeploymentPath) {
    Remove-Item -LiteralPath $DeploymentPath -Force
}

$AnvilArgumentList = "--chain-id $ChainId --accounts 10 --balance 10000 " +
    "--mnemonic `"$Mnemonic`" --host 127.0.0.1 --port 8546 " +
    "--dump-state `"$StatePath`""

$AnvilProcess = Start-Process -FilePath $AnvilExecutable `
    -ArgumentList $AnvilArgumentList `
    -WorkingDirectory $ProjectRoot `
    -PassThru

$Deadline = (Get-Date).AddSeconds(30)
do {
    Start-Sleep -Milliseconds 100
    $Listening = Get-NetTCPConnection -LocalPort 8546 -State Listen -ErrorAction SilentlyContinue
} while (-not $Listening -and (Get-Date) -lt $Deadline)

if (-not $Listening) {
    throw "Anvil did not start successfully after reset."
}

Write-Host "Fresh Anvil blockchain started on http://127.0.0.1:8546"
Write-Host "Chain ID: $ChainId"
Write-Host "The next application start will deploy fresh contracts."

if ($StartApp) {
    if (-not (Test-Path $PythonExecutable)) {
        throw "Python executable not found at $PythonExecutable"
    }
    Start-Process -FilePath $PythonExecutable `
        -ArgumentList "backend\scripts\start_local_chain.py" `
        -WorkingDirectory $ProjectRoot
    Write-Host "Starting the PharmaChain application..."
} else {
    Write-Host "Run: .\backend\venv313\Scripts\python.exe backend\scripts\start_local_chain.py"
}
