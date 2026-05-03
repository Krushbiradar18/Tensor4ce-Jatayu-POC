#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# test_apply.sh — End-to-end loan application test using Krishna Iyer docs
#
# Usage:
#   ./scripts/test_apply.sh                  # direct apply (no OCR upload)
#   ./scripts/test_apply.sh --with-docs      # OCR upload first (all 5 docs), then apply
#   ./scripts/test_apply.sh --missing-doc    # submit with zero income + no financial docs
#                                            # → triggers DATA_REQUIRED gate
#
# Expected files for --with-docs (all in backend/pdf_data/):
#   iyer_aadhar.png, iyer_pan.png, bank_statement.png, salary_slip_iyer.png, ITR_Iyer.png
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BASE_URL="http://localhost:8000"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PDF_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/pdf_data"

AADHAAR_FILE="$PDF_DIR/iyer_aadhar.png"
PAN_FILE="$PDF_DIR/iyer_pan.png"
BANK_FILE="$PDF_DIR/bank_statement.png"
SALARY_FILE="$PDF_DIR/salary_slip_iyer.png"
ITR_FILE="$PDF_DIR/ITR_Iyer.png"

WITH_DOCS=false
MISSING_DOC=false
[[ "${1:-}" == "--with-docs" ]]   && WITH_DOCS=true
[[ "${1:-}" == "--missing-doc" ]] && MISSING_DOC=true

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ARIA Loan Application Test — Krishna Iyer"
if   $WITH_DOCS;   then echo " Mode: WITH DOCUMENTS (Day 2 + Day 3)"
elif $MISSING_DOC; then echo " Mode: MISSING DOC — expects DATA_REQUIRED"
else                    echo " Mode: FORM ONLY"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Step 1: OCR document extraction ──────────────────────────────────────────
DOCUMENT_DATA='{}'

if $WITH_DOCS; then
  # Check required files exist
  FILE_MISSING=false
  for F in "$AADHAAR_FILE" "$PAN_FILE" "$BANK_FILE" "$SALARY_FILE" "$ITR_FILE"; do
    if [[ ! -f "$F" ]]; then
      echo "  MISSING: $F"
      FILE_MISSING=true
    fi
  done
  if $FILE_MISSING; then
    echo "ERROR: Place the above files in $PDF_DIR first."
    exit 1
  fi

  echo ""
  echo "▶ Step 1: Uploading all 5 documents for OCR / vision extraction..."
  echo "  Aadhaar : $AADHAAR_FILE"
  echo "  PAN     : $PAN_FILE"
  echo "  Bank    : $BANK_FILE"
  echo "  Salary  : $SALARY_FILE"
  echo "  ITR     : $ITR_FILE"

  OCR_RESPONSE=$(curl -s -X POST "$BASE_URL/api/extract-documents" \
    -F "aadhaar=@$AADHAAR_FILE;type=image/png" \
    -F "pan=@$PAN_FILE;type=image/png" \
    -F "bank_statement=@$BANK_FILE;type=image/png" \
    -F "salary_slip=@$SALARY_FILE;type=image/png" \
    -F "itr=@$ITR_FILE;type=image/png")

  echo ""
  echo "  OCR Response:"
  echo "$OCR_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$OCR_RESPONSE"
  DOCUMENT_DATA="$OCR_RESPONSE"

elif $MISSING_DOC; then
  # Only upload aadhaar + PAN; skip all financial docs to trigger DATA_REQUIRED
  for F in "$AADHAAR_FILE" "$PAN_FILE"; do
    if [[ ! -f "$F" ]]; then
      echo "  MISSING: $F"
      exit 1
    fi
  done

  echo ""
  echo "▶ Step 1: Uploading aadhaar + PAN only (no bank/salary/ITR) → triggers DATA_REQUIRED"
  echo "  Aadhaar : $AADHAAR_FILE"
  echo "  PAN     : $PAN_FILE"

  OCR_RESPONSE=$(curl -s -X POST "$BASE_URL/api/extract-documents" \
    -F "aadhaar=@$AADHAAR_FILE;type=image/png" \
    -F "pan=@$PAN_FILE;type=image/png")

  echo ""
  echo "  OCR Response (identity only):"
  echo "$OCR_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$OCR_RESPONSE"
  DOCUMENT_DATA="$OCR_RESPONSE"

else
  echo ""
  echo "▶ Step 1: Skipping OCR (using hardcoded values from cards)"
  DOCUMENT_DATA='{"name":"Krishna Iyer","pan_number":"HNORU5381L","aadhaar_number":"756455143468"}'
fi

# ── Step 2: Submit loan application ──────────────────────────────────────────
echo ""
echo "▶ Step 2: Submitting loan application..."

# In missing-doc mode: zero income so INCOME_PROOF becomes a blocking gap
ANNUAL_INCOME=840000
$MISSING_DOC && ANNUAL_INCOME=0

APPLY_RESPONSE=$(curl -s -X POST "$BASE_URL/api/apply" \
  -H "Content-Type: application/json" \
  -d "{
    \"form_data\": {
      \"applicant_name\": \"Krishna Iyer\",
      \"pan_number\": \"HNORU5381L\",
      \"aadhaar_last4\": \"3468\",
      \"date_of_birth\": \"1982-05-12\",
      \"gender\": \"MALE\",
      \"employment_type\": \"SALARIED\",
      \"employer_name\": \"Genesys Technologies Pvt Ltd\",
      \"annual_income\": $ANNUAL_INCOME,
      \"employment_tenure_years\": 5,
      \"loan_amount_requested\": 500000,
      \"loan_tenure_months\": 36,
      \"loan_purpose\": \"PERSONAL\",
      \"purpose_description\": \"Home renovation\",
      \"existing_emi_monthly\": 5000,
      \"residential_assets_value\": 2000000,
      \"mobile_number\": \"+91 9876543210\",
      \"email\": \"krishna.iyer@example.com\",
      \"address\": {
        \"line1\": \"H.No. 401, Mantri Residency, Bannerghatta Road\",
        \"city\": \"Bengaluru\",
        \"state\": \"Karnataka\",
        \"pincode\": \"560076\"
      }
    },
    \"ip_metadata\": {
      \"ip_address\": \"103.21.1.1\",
      \"form_fill_seconds\": 120,
      \"device_fingerprint\": \"test-device-001\",
      \"user_agent\": \"curl/test\"
    },
    \"document_data\": $DOCUMENT_DATA
  }")

echo ""
echo "  Apply Response:"
echo "$APPLY_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$APPLY_RESPONSE"

# ── Step 3: Poll until terminal status ────────────────────────────────────────
APP_ID=$(echo "$APPLY_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('application_id',''))" 2>/dev/null || echo "")

if [[ -z "$APP_ID" ]]; then
  echo "ERROR: Could not extract application_id from response."
  exit 1
fi

echo ""
echo "▶ Step 3: Polling status for $APP_ID (up to 120s)..."

TERMINAL_STATUSES=("DECIDED_PENDING_OFFICER" "DATA_REQUIRED" "REJECTED" "OFFICER_APPROVED" "OFFICER_REJECTED" "ERROR" "VERIFICATION_FAILED")
FINAL_STATUS=""
MAX_POLLS=24  # 24 × 5s = 120s

for i in $(seq 1 $MAX_POLLS); do
  sleep 5
  STATUS_JSON=$(curl -s "$BASE_URL/api/status/$APP_ID" 2>/dev/null || echo '{}')
  CURRENT=$(echo "$STATUS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
  echo "  [${i}×5s] Status: $CURRENT"

  for TS in "${TERMINAL_STATUSES[@]}"; do
    if [[ "$CURRENT" == "$TS" ]]; then
      FINAL_STATUS="$CURRENT"
      break 2
    fi
  done
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Application ID : $APP_ID"
echo " Final Status   : ${FINAL_STATUS:-STILL_PROCESSING}"
echo " Track at       : http://localhost:8081/track?id=$APP_ID"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Step 4: Print decision summary if available ───────────────────────────────
FULL_STATUS=$(curl -s "$BASE_URL/api/status/$APP_ID" 2>/dev/null || echo '{}')
echo ""
echo "▶ Step 4: Final decision payload:"
echo "$FULL_STATUS" | python3 -c "
import sys, json
d = json.load(sys.stdin)
dec = d.get('decision') or {}
print(f\"  AI Recommendation : {dec.get('ai_recommendation', 'N/A')}\")
print(f\"  CIBIL Score       : {dec.get('credit_risk', {}).get('cibil_score', dec.get('credit_score', 'N/A'))}\")
comp = dec.get('data_completeness') or {}
if comp:
    print(f\"  Data Score        : {comp.get('data_completeness_score', 'N/A')}\")
req_docs = dec.get('required_documents') or []
if req_docs:
    print(f\"  Required Docs     : {[r.get('doc') for r in req_docs]}\")
" 2>/dev/null || echo "  (no structured decision yet)"
echo ""

# ── Step 5: Re-submit missing docs (only in --missing-doc mode) ──────────────
if $MISSING_DOC && [[ "${FINAL_STATUS:-}" == "DATA_REQUIRED" ]]; then
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo " DATA_REQUIRED confirmed. Now re-submitting with all docs + income..."
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "▶ Step 5: Uploading missing docs via /api/resubmit/$APP_ID ..."

  RESUBMIT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/resubmit/$APP_ID" \
    -F "annual_income=840000" \
    -F "bank_statement=@$BANK_FILE;type=image/png" \
    -F "salary_slip=@$SALARY_FILE;type=image/png" \
    -F "itr=@$ITR_FILE;type=image/png")

  echo "  Resubmit Response:"
  echo "$RESUBMIT_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESUBMIT_RESPONSE"

  echo ""
  echo "▶ Step 6: Polling again after resubmit (up to 120s)..."
  FINAL_STATUS=""
  for i in $(seq 1 $MAX_POLLS); do
    sleep 5
    STATUS_JSON=$(curl -s "$BASE_URL/api/status/$APP_ID" 2>/dev/null || echo '{}')
    CURRENT=$(echo "$STATUS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
    echo "  [${i}×5s] Status: $CURRENT"
    for TS in "${TERMINAL_STATUSES[@]}"; do
      if [[ "$CURRENT" == "$TS" ]]; then
        FINAL_STATUS="$CURRENT"
        break 2
      fi
    done
  done

  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo " After resubmit — Final Status: ${FINAL_STATUS:-STILL_PROCESSING}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
fi

