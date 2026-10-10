# Smoke suite (spec s.14 cat.10): health/ready/otp-login/openapi; gate <= 3 min
param([string]$BaseUrl = "http://localhost:8000")
 $ErrorActionPreference = "Stop"
 $Root = Split-Path -Parent $PSScriptRoot
 $script:fail = 0
function Check($name, $ok) {
    if ($ok) { Write-Host "OK   $name" -ForegroundColor Green }
    else { Write-Host "FAIL $name" -ForegroundColor Red; $script:fail++ }
}

 $h = Invoke-RestMethod "$BaseUrl/health" -TimeoutSec 5
Check "health" ($h.data.status -eq "ok")
 $r = Invoke-RestMethod "$BaseUrl/ready" -TimeoutSec 5
Check "ready(db+redis)" ($r.data.status -eq "ready")

    $phone = "0912999" + (Get-Random -Minimum 1000 -Maximum 9999)  # 11 digits total
 $req = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/auth/otp/request" -ContentType "application/json" -Body ('{"phone":"' + $phone + '"}') -TimeoutSec 5
Start-Sleep -Milliseconds 400
 $e164 = "+98" + $phone.TrimStart("0")
 $line = Get-Content (Join-Path $Root "backend\logs\dev-otp.log") | Where-Object { $_ -like "*$e164*" } | Select-Object -Last 1
 $code = ($line -split "`t")[-1].Trim()
 $v = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/auth/otp/verify" -ContentType "application/json" -Body (@{ challenge_id = $req.data.challenge_id; code = $code } | ConvertTo-Json) -TimeoutSec 5
Check "otp-login" ([string]$v.data.access_token -gt "")

 $resp = Invoke-WebRequest "$BaseUrl/openapi.json" -UseBasicParsing -TimeoutSec 5
Check "openapi" ($resp.StatusCode -eq 200)

if ($script:fail -gt 0) { Write-Host "SMOKE RED" -ForegroundColor Red; exit 1 }
Write-Host "SMOKE GREEN (<= 3 min gate)" -ForegroundColor Green
