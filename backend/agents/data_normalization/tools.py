from crewai.tools import tool
import json
import logging

logger = logging.getLogger(__name__)

@tool("normalize_extracted_data")
def normalize_extracted_data(ocr_json_str: str) -> str:
    """
    Takes the JSON output from the OCR & Extraction Agent, merges extracted data 
    from multiple documents, removes duplicates, and creates one unified applicant profile.
    """
    try:
        ocr_data = json.loads(ocr_json_str)
    except Exception as e:
        return json.dumps({"error": f"Invalid input JSON: {str(e)}"})
        
    application_id = ocr_data.get("application_id")
    extracted_docs = ocr_data.get("extracted_documents", [])
    
    # Unified profile
    unified_profile = {
        "application_id": application_id,
        "identity": {
            "name": None,
            "pan_number": None,
            "aadhaar_number": None,
        },
        "financials": {
            "avg_monthly_credit": 0.0,
            "avg_monthly_balance": 0.0,
            "min_eod_balance": 0.0,
            "emi_bounce_count": 0,
            "salary_regularity": 0.0,
            "gross_salary": 0.0,
            "net_pay": 0.0,
            "employer_name": None,
            "total_income_itr": 0.0,
            "tax_paid": 0.0,
        },
        "documents_processed": [],
        "confidence_scores": {}
    }
    
    # Track the highest confidence score for each field to handle duplicates
    field_confidence = {
        "name": 0.0,
        "pan_number": 0.0,
        "aadhaar_number": 0.0
    }
    
    for doc in extracted_docs:
        doc_type = doc.get("doc_type")
        conf = doc.get("confidence_score", 0.0)
        
        unified_profile["documents_processed"].append({
            "doc_id": doc.get("doc_id"),
            "doc_type": doc_type,
            "confidence_score": conf
        })
        
        # Merge Identity
        if doc_type in ["AADHAAR", "PAN"]:
            name = doc.get("name")
            if name and conf >= field_confidence["name"]:
                unified_profile["identity"]["name"] = name
                field_confidence["name"] = conf
                unified_profile["confidence_scores"]["name"] = conf
                
            if doc_type == "PAN" and doc.get("pan_number") and conf >= field_confidence["pan_number"]:
                unified_profile["identity"]["pan_number"] = doc.get("pan_number")
                field_confidence["pan_number"] = conf
                unified_profile["confidence_scores"]["pan_number"] = conf
                
            if doc_type == "AADHAAR" and doc.get("aadhaar_number") and conf >= field_confidence["aadhaar_number"]:
                unified_profile["identity"]["aadhaar_number"] = doc.get("aadhaar_number")
                field_confidence["aadhaar_number"] = conf
                unified_profile["confidence_scores"]["aadhaar_number"] = conf
                
        # Merge Financials
        elif doc_type == "BANK_STATEMENT":
            unified_profile["financials"]["avg_monthly_credit"] = doc.get("avg_monthly_credit", 0.0)
            unified_profile["financials"]["avg_monthly_balance"] = doc.get("avg_monthly_balance", 0.0)
            unified_profile["financials"]["min_eod_balance"] = doc.get("min_eod_balance", 0.0)
            unified_profile["financials"]["emi_bounce_count"] = doc.get("emi_bounce_count", 0)
            unified_profile["financials"]["salary_regularity"] = doc.get("salary_regularity", 0.0)
            unified_profile["confidence_scores"]["bank_statement"] = conf
            
        elif doc_type == "SALARY_SLIP":
            unified_profile["financials"]["gross_salary"] = doc.get("gross_salary", 0.0)
            unified_profile["financials"]["net_pay"] = doc.get("net_pay", 0.0)
            if not unified_profile["financials"]["employer_name"]:
                unified_profile["financials"]["employer_name"] = doc.get("employer_name")
            unified_profile["confidence_scores"]["salary_slip"] = conf
            
        elif doc_type == "ITR":
            unified_profile["financials"]["total_income_itr"] = doc.get("total_income", 0.0)
            unified_profile["financials"]["tax_paid"] = doc.get("tax_paid", 0.0)
            if not unified_profile["financials"]["employer_name"]:
                unified_profile["financials"]["employer_name"] = doc.get("employer_name")
            unified_profile["confidence_scores"]["itr"] = conf
            
    return json.dumps(unified_profile)
