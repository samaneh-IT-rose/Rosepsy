# env-check v2 — ترمیم خودکار محیط؛ همیشه قبل از کار اجرا کنید
 $Root = Split-Path -Parent $PSScriptRoot

docker info *> $null
if (-not $?) {
    Write-Host "Docker خاموش است — اجرای Docker Desktop..." -ForegroundColor Yellow
    $dd = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path $dd)) { Write-Host "Docker Desktop یافت نشد" -ForegroundColor Red; exit 1 }
    Start-Process $dd
    $deadline = (Get-Date).AddSeconds(150)
    while ((Get-Date) -lt $deadline) {
        docker info *> $null
        if ($?) { break }
        Start-Sleep -Seconds 5
    }
    docker info *> $null
    if (-not $?) { Write-Host "Docker بعد از 150 ثانیه بالا نیامد — دستی اجرا کنید" -ForegroundColor Red; exit 1 }
}
Write-Host "OK: Docker engine" -ForegroundColor Green

Set-Location (Join-Path $Root "infra")
docker compose up -d db redis

 $deadline = (Get-Date).AddSeconds(90)
while ((Get-Date) -lt $deadline) {
    docker compose exec -T db pg_isready -U roz -d roz *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 3
}
docker compose ps

Set-Location (Join-Path $Root "backend")
& .\.venv\Scripts\python.exe -m pytest
