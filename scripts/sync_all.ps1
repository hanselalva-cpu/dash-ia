# Sincroniza costos de OpenAI, ElevenLabs y Deepgram hacia Supabase.
# Re-descarga los últimos N días: los proveedores ajustan cifras del día anterior y el upsert no duplica.
# Uso manual:  powershell -ExecutionPolicy Bypass -File scripts\sync_all.ps1 [-Days 3]
param([int]$Days = 3)

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("sync_{0:yyyy-MM-dd}.log" -f (Get-Date))
$env:PYTHONIOENCODING = "utf-8"
Set-Location $root

$failed = @()
foreach ($module in "openai_sync", "elevenlabs_sync", "deepgram_sync") {
    "[{0:yyyy-MM-dd HH:mm:ss}] ===== $module --days $Days" -f (Get-Date) | Out-File -Append -Encoding utf8 $log
    & $python -m "integrations.$module" --days $Days 2>&1 | ForEach-Object { "$_" } | Out-File -Append -Encoding utf8 $log
    if ($LASTEXITCODE -ne 0) { $failed += $module }
}

$status = if ($failed) { "ERROR en: $($failed -join ', ')" } else { "OK" }
"[{0:yyyy-MM-dd HH:mm:ss}] ===== fin: $status" -f (Get-Date) | Out-File -Append -Encoding utf8 $log

# Conservar 60 días de logs.
Get-ChildItem $logDir -Filter "sync_*.log" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-60) } | Remove-Item -Force

if ($failed) { exit 1 }
