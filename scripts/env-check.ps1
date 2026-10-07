# بررسی و ترمیم محیط توسعه — هر بار قبل از کار اجرا کنید
docker info *> $null
if (-not $?) {
    Write-Host "X Docker Desktop اجرا نیست. آن را باز کنید، تا سبز شدن آیکون صبر کنید و دوباره اجرا کنید." -ForegroundColor Red
    exit 1
}
Write-Host "OK: Docker active" -ForegroundColor Green
Set-Location (Join-Path $PSScriptRoot "..\infra")
docker compose up -d db redis
docker compose ps
Set-Location (Join-Path $PSScriptRoot "..\backend")
& .\.venv\Scripts\python.exe -m pytest
