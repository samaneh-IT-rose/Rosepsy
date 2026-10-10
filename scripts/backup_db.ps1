# Daily logical backup (spec s.11): pg_dump custom format, 30-day retention
param([string]$OutDir = "D:\projects\rose-clinic\backups")
 $ErrorActionPreference = "Stop"
 $Root = Split-Path -Parent $PSScriptRoot
 $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
Set-Location (Join-Path $Root "infra")

 $name = "roz-$stamp.dump"
docker compose exec -T db pg_dump -U roz -d roz -F c -f "/tmp/$name"
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed" }
docker compose cp "db:/tmp/$name" (Join-Path $OutDir $name)
docker compose exec -T db rm "/tmp/$name"

Get-ChildItem $OutDir -Filter "roz-*.dump" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force

 $item = Get-Item (Join-Path $OutDir $name)
Write-Host ("backup OK: {0} ({1:N0} KB)" -f $item.Name, ($item.Length / 1KB)) -ForegroundColor Green
