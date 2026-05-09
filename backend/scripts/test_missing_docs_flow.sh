#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# test_missing_docs_flow.sh
# 
# Demonstrates the full missing documents orchestration flow:
# 1. User uploads incomplete documents (Aadhaar & PAN only).
# 2. Pipeline evaluates requirements, halts, and returns DATA_REQUIRED.
# 3. User resubmits missing documents (Bank Statement, Salary Slip, ITR).
# 4. Pipeline resumes processing and generates a final decision.
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

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ⏳ STARTING MISSING DOCUMENTS FLOW TEST"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Step 1: Upload Incomplete Documents ─────────────────────────────────────
echo ""
echo "▶ STEP 1: Uploading incomplete documents (Aadhaar + PAN only)"
echo "  This simulates a user forgetting to upload financial documents."
echo "  [INFO] Running local AI vision extraction (PaddleOCR)..."
echo "  [INFO] This usually takes 30-60 seconds on CPU. Please wait and do NOT press Ctrl+C!"

OCR_RESPONSE=$(curl -s -X POST "$BASE_URL/api/extract-documents" \
  -F "aadhaar=@$AADHAAR_FILE;type=image/png" \
  -F "pan=@$PAN_FILE;type=image/png")

echo "  OCR Extraction Complete."

# ── Step 2: Submit Loan Application ─────────────────────────────────────────
echo ""
echo "▶ STEP 2: Submitting Loan Application (₹5,00,000 Salaried Loan)"

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
      \"annual_income\": 0,
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
    \"document_data\": $OCR_RESPONSE
  }")

APP_ID=$(echo "$APPLY_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('application_id',''))" 2>/dev/null)
echo "  Application Created: $APP_ID"

# ── Step 3: Poll until DATA_REQUIRED ─────────────────────────────────────────
echo ""
echo "▶ STEP 3: Polling pipeline status... Waiting for Orchestrator to pause."

FINAL_STATUS=""
for i in $(seq 1 20); do
  sleep 4
  STATUS_JSON=$(curl -s "$BASE_URL/api/status/$APP_ID" 2>/dev/null || echo '{}')
  CURRENT=$(echo "$STATUS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
  echo "  [Poll $i] Status: $CURRENT"
  
  if [[ "$CURRENT" == "DATA_REQUIRED" || "$CURRENT" == "DECIDED_PENDING_OFFICER" || "$CURRENT" == "REJECTED" || "$CURRENT" == "ERROR" ]]; then
    FINAL_STATUS="$CURRENT"
    break
  fi
done

if [[ "$FINAL_STATUS" != "DATA_REQUIRED" ]]; then
  echo "❌ FAILED: Pipeline did not halt at DATA_REQUIRED. Status: $FINAL_STATUS"
  exit 1
fi

echo ""
echo "✅ PIPELINE PAUSED: DATA_REQUIRED confirmed."

# Extract what documents are missing
MISSING_DOCS=$(curl -s "$BASE_URL/api/status/$APP_ID" | python3 -c "
import sys, json
d = json.load(sys.stdin)
req_docs = d.get('decision', {}).get('required_documents', [])
print(', '.join([r.get('doc') for r in req_docs]))
" 2>/dev/null)
echo "   Orchestrator requested: $MISSING_DOCS"

# ── Step 4: Resubmit Missing Documents ───────────────────────────────────────
echo ""
echo "▶ STEP 4: User uploads the required documents..."
echo "  Uploading Bank Statement, Salary Slip, and ITR..."

RESUBMIT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/resubmit/$APP_ID" \
  -F "annual_income=840000" \
  -F "bank_statement=@$BANK_FILE;type=image/png" \
  -F "salary_slip=@$SALARY_FILE;type=image/png" \
  -F "itr=@$ITR_FILE;type=image/png")

echo "  Documents received. Pipeline restarted!"

# ── Step 5: Poll until Final Decision ────────────────────────────────────────
echo ""
echo "▶ STEP 5: Polling resumed pipeline..."

FINAL_STATUS=""
for i in $(seq 1 24); do
  sleep 5
  STATUS_JSON=$(curl -s "$BASE_URL/api/status/$APP_ID" 2>/dev/null || echo '{}')
  CURRENT=$(echo "$STATUS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
  echo "  [Poll $i] Status: $CURRENT"
  
  if [[ "$CURRENT" == "DECIDED_PENDING_OFFICER" || "$CURRENT" == "REJECTED" || "$CURRENT" == "OFFICER_REJECTED" || "$CURRENT" == "ERROR" ]]; then
    FINAL_STATUS="$CURRENT"
    break
  fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " 🎉 FLOW COMPLETE!"
echo " Final Application Status : $FINAL_STATUS"
echo " View Application at      : http://localhost:8000/track?id=$APP_ID"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
