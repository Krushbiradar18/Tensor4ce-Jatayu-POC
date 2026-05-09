#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# test_interactive_missing_docs.sh
# 
# This script starts a loan application with ONLY identity documents.
# It waits for the system to pause at DATA_REQUIRED, then waits for YOU
# to upload the remaining documents via the Frontend UI.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BASE_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:8081"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PDF_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/pdf_data"

AADHAAR_FILE="$PDF_DIR/iyer_aadhar.png"
PAN_FILE="$PDF_DIR/iyer_pan.png"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " 🛠️  INTERACTIVE MISSING DOCUMENTS TEST"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Step 1: Upload Aadhaar + PAN ─────────────────────────────────────────────
echo "▶ STEP 1: Uploading Aadhaar and PAN (Automatic)..."
OCR_RESPONSE=$(curl -s -X POST "$BASE_URL/api/extract-documents" \
  -F "aadhaar=@$AADHAAR_FILE;type=image/png" \
  -F "pan=@$PAN_FILE;type=image/png")

# ── Step 2: Submit Application ───────────────────────────────────────────────
echo "▶ STEP 2: Submitting Loan Application..."
APPLY_RESPONSE=$(curl -s -X POST "$BASE_URL/api/apply" \
  -H "Content-Type: application/json" \
  -d "{
    \"form_data\": {
      \"applicant_name\": \"Krishna Iyer\",
      \"pan_number\": \"HNORU5381L\",
      \"aadhaar_last4\": \"3468\",
      \"date_of_birth\": \"1982-05-12\",
      \"employment_type\": \"SALARIED\",
      \"employer_name\": \"Genesys Technologies\",
      \"annual_income\": 840000,
      \"loan_amount_requested\": 500000,
      \"loan_tenure_months\": 36,
      \"loan_purpose\": \"PERSONAL\"
    },
    \"document_data\": $OCR_RESPONSE
  }")

APP_ID=$(echo "$APPLY_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('application_id',''))" 2>/dev/null)
echo "   ✅ Application Created: $APP_ID"

# ── Step 3: Wait for DATA_REQUIRED ───────────────────────────────────────────
echo ""
echo "▶ STEP 3: Waiting for Orchestrator to detect missing documents..."
while true; do
  STATUS_JSON=$(curl -s "$BASE_URL/api/status/$APP_ID" 2>/dev/null || echo '{}')
  CURRENT=$(echo "$STATUS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
  echo "   [Current Status]: $CURRENT"
  
  if [[ "$CURRENT" == "DATA_REQUIRED" ]]; then break; fi
  if [[ "$CURRENT" == "ERROR" || "$CURRENT" == "REJECTED" ]]; then
    echo "   ❌ Something went wrong. Final Status: $CURRENT"
    exit 1
  fi
  sleep 4
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ⏸️  PIPELINE PAUSED"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Application ID: $APP_ID"
echo " Required Docs : BANK_STATEMENT, SALARY_SLIP"
echo ""
echo " 👉 ACTION REQUIRED:"
echo " 1. Open: $FRONTEND_URL/track?id=$APP_ID"
echo " 2. Upload the missing Salary Slip and Bank Statement in the UI."
echo " 3. Once you see 'Application received. Pipeline restarted' in the browser..."
echo ""
read -p " ⌨️  Press [ENTER] here to resume tracking the pipeline to the final decision..."

# ── Step 4: Poll until final decision ────────────────────────────────────────
echo ""
echo "▶ STEP 4: Tracking final processing..."
while true; do
  STATUS_JSON=$(curl -s "$BASE_URL/api/status/$APP_ID" 2>/dev/null || echo '{}')
  CURRENT=$(echo "$STATUS_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
  echo "   [Current Status]: $CURRENT"
  
  if [[ "$CURRENT" == "DECIDED_PENDING_OFFICER" || "$CURRENT" == "REJECTED" || "$CURRENT" == "OFFICER_REJECTED" ]]; then
    break
  fi
  sleep 5
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " 🎉 SUCCESS! Final Status: $CURRENT"
echo " View your results on the dashboard."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
