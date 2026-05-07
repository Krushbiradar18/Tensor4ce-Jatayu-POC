param(
    [switch]$WithDocs,
    [switch]$MissingDoc
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$BASE_URL = 'http://localhost:8000'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PDFDir = Resolve-Path (Join-Path $ScriptDir '..\pdf_data') | Select-Object -ExpandProperty Path

$AADHAAR_FILE = Join-Path $PDFDir 'iyer_aadhar.png'
$PAN_FILE     = Join-Path $PDFDir 'iyer_pan.png'
$BANK_FILE    = Join-Path $PDFDir 'bank_statement.png'
$SALARY_FILE  = Join-Path $PDFDir 'salary_slip_iyer.png'
$ITR_FILE     = Join-Path $PDFDir 'ITR_Iyer.png'

Write-Host "-------------------------------------------------"
Write-Host "ARIA Loan Application Test - Krishna Iyer"
if ($WithDocs) { Write-Host "Mode: WITH DOCUMENTS (Day 2 + Day 3)" }
elseif ($MissingDoc) { Write-Host "Mode: MISSING DOC - expects DATA_REQUIRED" }
else { Write-Host "Mode: FORM ONLY" }
Write-Host "-------------------------------------------------`n"

# Step 1: OCR document extraction
$DOCUMENT_DATA = '{}'

function Ensure-FilesExist {
    param([string[]]$Files)
    $missing = $false
    foreach ($f in $Files) {
        if (-not (Test-Path $f)) {
            Write-Host "  MISSING: $f"
            $missing = $true
        }
    }
    if ($missing) { throw "ERROR: Place the above files in $PDFDir first." }
}

if ($WithDocs) {
    Ensure-FilesExist -Files @($AADHAAR_FILE, $PAN_FILE, $BANK_FILE, $SALARY_FILE, $ITR_FILE)
    Write-Host "`n> Step 1: Uploading all 5 documents for OCR / vision extraction..."
    Write-Host "  Aadhaar : $AADHAAR_FILE"
    Write-Host "  PAN     : $PAN_FILE"
    Write-Host "  Bank    : $BANK_FILE"
    Write-Host "  Salary  : $SALARY_FILE"
    Write-Host "  ITR     : $ITR_FILE`n"

    $curlArgs = @(
        '-s', '-X', 'POST', "$BASE_URL/api/extract-documents",
        '-F', "aadhaar=@$AADHAAR_FILE;type=image/png",
        '-F', "pan=@$PAN_FILE;type=image/png",
        '-F', "bank_statement=@$BANK_FILE;type=image/png",
        '-F', "salary_slip=@$SALARY_FILE;type=image/png",
        '-F', "itr=@$ITR_FILE;type=image/png"
    )
    try {
        $OCR_RESPONSE = & curl.exe @curlArgs 2>$null
    } catch {
        throw "Failed to run curl.exe. Ensure curl is available in PATH or use Invoke-RestMethod multipart upload."
    }
    Write-Host "`n  OCR Response:`n$OCR_RESPONSE`n"
    $DOCUMENT_DATA = $OCR_RESPONSE

} elseif ($MissingDoc) {
    Ensure-FilesExist -Files @($AADHAAR_FILE, $PAN_FILE)
    Write-Host "`n> Step 1: Uploading aadhaar + PAN only (no bank/salary/ITR) -> triggers DATA_REQUIRED"
    Write-Host "  Aadhaar : $AADHAAR_FILE"
    Write-Host "  PAN     : $PAN_FILE`n"

    $curlArgs = @(
        '-s', '-X', 'POST', "$BASE_URL/api/extract-documents",
        '-F', "aadhaar=@$AADHAAR_FILE;type=image/png",
        '-F', "pan=@$PAN_FILE;type=image/png"
    )
    try {
        $OCR_RESPONSE = & curl.exe @curlArgs 2>$null
    } catch {
        throw "Failed to run curl.exe. Ensure curl is available in PATH or use Invoke-RestMethod multipart upload."
    }
    Write-Host "`n  OCR Response (identity only):`n$OCR_RESPONSE`n"
    $DOCUMENT_DATA = $OCR_RESPONSE

} else {
    Write-Host "`n> Step 1: Skipping OCR (using hardcoded values from cards)"
    $DOCUMENT_DATA = '{"name":"Krishna Iyer","pan_number":"HNORU5381L","aadhaar_number":"756455143468"}'
}

# Step 2: Submit loan application
Write-Host "`n> Step 2: Submitting loan application..."

$ANNUAL_INCOME = 840000
if ($MissingDoc) { $ANNUAL_INCOME = 0 }

# Try to parse document JSON if possible
$DocumentDataObject = $null
try {
    $DocumentDataObject = $DOCUMENT_DATA | ConvertFrom-Json -ErrorAction Stop
} catch {
    # keep as raw string if not JSON
    $DocumentDataObject = $DOCUMENT_DATA
}

$payload = @{
    form_data = @{
        applicant_name = 'Krishna Iyer'
        pan_number = 'HNORU5381L'
        aadhaar_last4 = '3468'
        date_of_birth = '1982-05-12'
        gender = 'MALE'
        employment_type = 'SALARIED'
        employer_name = 'Genesys Technologies Pvt Ltd'
        annual_income = $ANNUAL_INCOME
        employment_tenure_years = 5
        loan_amount_requested = 500000
        loan_tenure_months = 36
        loan_purpose = 'PERSONAL'
        purpose_description = 'Home renovation'
        existing_emi_monthly = 5000
        residential_assets_value = 2000000
        mobile_number = '+91 9876543210'
        email = 'krishna.iyer@example.com'
        address = @{ line1 = 'H.No. 401, Mantri Residency, Bannerghatta Road'; city = 'Bengaluru'; state = 'Karnataka'; pincode = '560076' }
    }
    ip_metadata = @{ ip_address = '103.21.1.1'; form_fill_seconds = 120; device_fingerprint = 'test-device-001'; user_agent = 'curl/test' }
    document_data = $DocumentDataObject
}

$jsonBody = $payload | ConvertTo-Json -Depth 10

try {
    $APPLY_RESPONSE = Invoke-RestMethod -Uri "$BASE_URL/api/apply" -Method Post -Body $jsonBody -ContentType 'application/json'
} catch {
    throw "Apply request failed: $_"
}

Write-Host "`n  Apply Response:`n"
try { $APPLY_RESPONSE | ConvertTo-Json -Depth 5 | Write-Host } catch { Write-Host $APPLY_RESPONSE }

# Step 3: Poll until terminal status
$APP_ID = $null
try { $APP_ID = $APPLY_RESPONSE.application_id } catch { $APP_ID = $null }
if (-not $APP_ID) { throw 'ERROR: Could not extract application_id from response.' }

Write-Host "`n> Step 3: Polling status for $APP_ID (up to 120s)..."

$TERMINAL_STATUSES = @('DECIDED_PENDING_OFFICER','DATA_REQUIRED','REJECTED','OFFICER_APPROVED','OFFICER_REJECTED','ERROR','VERIFICATION_FAILED')
$FINAL_STATUS = ''
$MAX_POLLS = 24

for ($i = 1; $i -le $MAX_POLLS; $i++) {
    Start-Sleep -Seconds 5
    try {
        $STATUS_JSON = Invoke-RestMethod -Uri "$BASE_URL/api/status/$APP_ID" -Method Get -ErrorAction SilentlyContinue
    } catch {
        $STATUS_JSON = $null
    }
    $CURRENT = if ($STATUS_JSON -and $STATUS_JSON.status) { $STATUS_JSON.status } else { '' }
    Write-Host "  [$i x 5s] Status: $CURRENT"
    if ($TERMINAL_STATUSES -contains $CURRENT) { $FINAL_STATUS = $CURRENT; break }
}

Write-Host "`n-------------------------------------------------"
Write-Host "Application ID : $APP_ID"
Write-Host "Final Status   : ${FINAL_STATUS:-STILL_PROCESSING}"
Write-Host "Track at       : http://localhost:8081/track?id=$APP_ID"
Write-Host "-------------------------------------------------`n"

# Step 4: Print decision summary if available
try {
    $FULL_STATUS = Invoke-RestMethod -Uri "$BASE_URL/api/status/$APP_ID" -Method Get -ErrorAction SilentlyContinue
} catch {
    $FULL_STATUS = $null
}

Write-Host "> Step 4: Final decision payload:"
if ($FULL_STATUS -and $FULL_STATUS.decision) {
    $dec = $FULL_STATUS.decision
    Write-Host "  AI Recommendation : $($dec.ai_recommendation -or 'N/A')"
    $cibil = $dec.credit_risk.cibil_score -or $dec.credit_score -or 'N/A'
    Write-Host "  CIBIL Score       : $cibil"
    if ($dec.data_completeness) { Write-Host "  Data Score        : $($dec.data_completeness.data_completeness_score -or 'N/A')" }
    if ($dec.required_documents) { Write-Host "  Required Docs     : $($dec.required_documents | ForEach-Object { $_.doc })" }
} else {
    Write-Host '  (no structured decision yet)'
}

if ($MissingDoc -and $FINAL_STATUS -eq 'DATA_REQUIRED') {
    Write-Host "`n-------------------------------------------------"
    Write-Host "DATA_REQUIRED confirmed. No re-upload will be performed in missing-doc mode."
    Write-Host "-------------------------------------------------`n"
}
