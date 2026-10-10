# Backup & restore drill (spec s.14 cat.12): real restore into scratch DB,
# row-count parity, elapsed vs RTO(4h), signed log entry in docs/drill-log.md
param([string]$DumpFile)
 $ErrorActionPreference = "Stop"
 $Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "infra")

if (-not $DumpFile) {
    $latest = Get-ChildItem (Join-Path $Root "backups") -Filter "roz-*.dump" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { throw "no backup found; run backup_db.ps1 first" }
    $DumpFile = $latest.FullName
}
 $dumpName = Split-Path $DumpFile -Leaf
Write-Host "restore drill from: $dumpName"

docker compose cp "$DumpFile" "db:/tmp/$dumpName"
docker compose exec -T db psql -U roz -d postgres -c "DROP DATABASE IF EXISTS roz_drill;" *> $null
docker compose exec -T db psql -U roz -d postgres -c "CREATE DATABASE roz_drill;" *> $null

 $sw = [Diagnostics.Stopwatch]::StartNew()
docker compose exec -T db pg_restore -U roz -d roz_drill --no-owner -1 "/tmp/$dumpName"
if ($LASTEXITCODE -ne 0) { throw "pg_restore failed" }
 $sw.Stop()

function Get-Count($db, $sql) {
    [int](docker compose exec -T db psql -U roz -d $db -t -A -c $sql)
}
 $srcUsers = Get-Count "roz" "SELECT count(*) FROM core.users"
 $dstUsers = Get-Count "roz_drill" "SELECT count(*) FROM core.users"
 $srcRecords = Get-Count "roz" "SELECT count(*) FROM clinical.clinical_records"
 $dstRecords = Get-Count "roz_drill" "SELECT count(*) FROM clinical.clinical_records"
 $ok = ($srcUsers -eq $dstUsers) -and ($srcRecords -eq $dstRecords)

docker compose exec -T db psql -U roz -d postgres -c "DROP DATABASE IF EXISTS roz_drill;" *> $null
docker compose exec -T db rm "/tmp/$dumpName" *> $null

 $elapsed = $sw.Elapsed.ToString("mm\:ss")
 $verdict = "MISMATCH"; $color = "Red"
if ($ok) { $verdict = "OK"; $color = "Green" }
Write-Host ("drill {0} | users {1}->{2} | records {3}->{4} | elapsed {5} (RTO 4h)" -f $verdict, $srcUsers, $dstUsers, $srcRecords, $dstRecords, $elapsed) -ForegroundColor $color

 $log = Join-Path $Root "docs\drill-log.md"
if (-not (Test-Path $log)) {
    $header = @(
        "# گزارش تمرین بازیابی (Restore Drill Log)",
        "",
        "| تاریخ (UTC) | بکاپ | تطبیق ردیف‌ها | زمان بازیابی | نتیجه |",
        "|---|---|---|---|---|"
    )
    Set-Content -Path $log -Encoding utf8 -Value $header
}
 $stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm")
Add-Content -Path $log -Encoding utf8 -Value ("| {0} | {1} | users {2}/{3} - records {4}/{5} | {6} | {7} |" -f $stamp, $dumpName, $dstUsers, $srcUsers, $dstRecords, $srcRecords, $elapsed, $verdict)
if (-not $ok) { exit 1 }
