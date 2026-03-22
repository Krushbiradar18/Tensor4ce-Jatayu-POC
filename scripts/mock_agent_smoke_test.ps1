param(
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [int]$PollIntervalSeconds = 2,
  [int]$MaxPollAttempts = 45
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-ApplyPayload {
  param(
    [hashtable]$FormData,
    [hashtable]$IpMeta
  )

  return @{
    form_data = $FormData
    ip_metadata = $IpMeta
  }
}

function Submit-Application {
  param([hashtable]$Payload)

  $json = $Payload | ConvertTo-Json -Depth 10
  return Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/apply" -ContentType "application/json" -Body $json
}

function Get-Status {
  param([string]$AppId)
  return Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/status/$AppId"
}

function Wait-UntilDecided {
  param([string]$AppId)

  for ($i = 1; $i -le $MaxPollAttempts; $i++) {
    $statusRes = Get-Status -AppId $AppId
    $status = $statusRes.status

    if ($status -eq "ERROR" -or $status -eq "DECIDED_PENDING_OFFICER" -or $status.StartsWith("OFFICER_")) {
      return $statusRes
    }

    Start-Sleep -Seconds $PollIntervalSeconds
  }

  return [pscustomobject]@{
    application_id = $AppId
    status = "TIMEOUT"
    message = "Status did not reach terminal state in time"
  }
}

function Get-FinalDecision {
  param([string]$AppId)

  try {
    return Invoke-RestMethod -Method Get -Uri "$BaseUrl/api/officer/decision/$AppId"
  }
  catch {
    return $null
  }
}

$scenarios = @(
  [pscustomobject]@{
    Name = "CleanApproval"
    Expected = "APPROVE|CONDITIONAL"
    FormData = @{
      applicant_name = "Rahul Sharma"
      pan_number = "ABCDE1234F"
      aadhaar_last4 = "9012"
      date_of_birth = "1988-05-12"
      gender = "MALE"
      employment_type = "SALARIED"
      employer_name = "Infosys Limited"
      annual_income = 1800000
      employment_tenure_years = 6
      loan_amount_requested = 4500000
      loan_tenure_months = 240
      loan_purpose = "HOME"
      existing_emi_monthly = 15000
      residential_assets_value = 8000000
      mobile_number = "9876543210"
      email = "rahul@example.com"
      address = @{
        line1 = "12 MG Road"
        city = "Pune"
        state = "Maharashtra"
        pincode = "411001"
      }
    }
    IpMeta = @{
      ip_address = "103.21.1.1"
      form_fill_seconds = 280
      device_fingerprint = "dev-clean-001"
      user_agent = "Mozilla/5.0"
    }
  },
  [pscustomobject]@{
    Name = "FraudTrigger"
    Expected = "REJECT|ESCALATE"
    FormData = @{
      applicant_name = "Test Fraud"
      pan_number = "FRAUD1234F"
      aadhaar_last4 = "1234"
      date_of_birth = "1993-04-17"
      gender = "MALE"
      employment_type = "SELF_EMPLOYED"
      employer_name = "Self Business"
      annual_income = 600000
      employment_tenure_years = 2
      loan_amount_requested = 2500000
      loan_tenure_months = 120
      loan_purpose = "PERSONAL"
      existing_emi_monthly = 18000
      residential_assets_value = 0
      mobile_number = "9999999999"
      email = "fraud@test.com"
      address = @{
        line1 = "Unknown"
        city = "Mumbai"
        state = "Maharashtra"
        pincode = "400001"
      }
    }
    IpMeta = @{
      ip_address = "10.0.1.1"
      form_fill_seconds = 12
      device_fingerprint = "dev-fraud-001"
      user_agent = "Mozilla/5.0"
    }
  },
  [pscustomobject]@{
    Name = "AffordabilityStress"
    Expected = "CONDITIONAL|ESCALATE|REJECT"
    FormData = @{
      applicant_name = "High Risk Case"
      pan_number = "QWERT1234Z"
      aadhaar_last4 = "7777"
      date_of_birth = "1999-01-01"
      gender = "FEMALE"
      employment_type = "SALARIED"
      employer_name = "Small Startup"
      annual_income = 360000
      employment_tenure_years = 1
      loan_amount_requested = 3000000
      loan_tenure_months = 60
      loan_purpose = "AUTO"
      existing_emi_monthly = 22000
      residential_assets_value = 100000
      mobile_number = "8888888888"
      email = "risk@test.com"
      address = @{
        line1 = "Lane 4"
        city = "Bengaluru"
        state = "Karnataka"
        pincode = "560001"
      }
    }
    IpMeta = @{
      ip_address = "45.120.10.55"
      form_fill_seconds = 25
      device_fingerprint = "dev-risk-001"
      user_agent = "Mozilla/5.0"
    }
  }
)

$results = @()

foreach ($scenario in $scenarios) {
  Write-Host "`n=== Running scenario: $($scenario.Name) ===" -ForegroundColor Cyan

  $payload = New-ApplyPayload -FormData $scenario.FormData -IpMeta $scenario.IpMeta
  $submitRes = Submit-Application -Payload $payload
  $appId = $submitRes.application_id

  Write-Host "Submitted: $appId" -ForegroundColor Gray

  $statusRes = Wait-UntilDecided -AppId $appId
  $final = Get-FinalDecision -AppId $appId

  $aiDecision = $null
  if ($null -ne $final -and $null -ne $final.decision) {
    $aiDecision = $final.decision.ai_recommendation
  }

  $status = $statusRes.status
  $matched = $false
  if ($aiDecision) {
    $allowed = $scenario.Expected -split "\|"
    $matched = $allowed -contains $aiDecision
  }

  $results += [pscustomobject]@{
    Scenario = $scenario.Name
    AppId = $appId
    Status = $status
    Expected = $scenario.Expected
    AIDecision = $(if ($aiDecision) { $aiDecision } else { "N/A" })
    Match = $(if ($matched) { "YES" } else { "NO" })
  }
}

Write-Host "`n=== Smoke Test Summary ===" -ForegroundColor Green
$results | Format-Table -AutoSize

# Emit machine-readable object at the end too
$results
