from crewai import Crew, Task, Process
import json
import logging
import os

logger = logging.getLogger(__name__)

def run_document_processing_crew(application_id: str, llm=None):
    """
    Runs the Document Intake -> OCR -> Normalization sequence using CrewAI.
    Returns the unified applicant profile JSON.
    """
    try:
        from agents.document_intake.agent import get_document_intake_agent
        from agents.ocr_extraction.agent import get_ocr_extraction_agent
        from agents.data_normalization.agent import get_data_normalization_agent

        intake_agent = get_document_intake_agent(llm)
        ocr_agent = get_ocr_extraction_agent(llm)
        normalization_agent = get_data_normalization_agent(llm)

        intake_task = Task(
            description=f"Process uploaded documents for application {application_id} using the intake_documents tool. Return the JSON output exactly as provided by the tool.",
            expected_output="JSON string containing the application_id and identified documents.",
            agent=intake_agent,
        )

        ocr_task = Task(
            description="Take the JSON output from the intake task and pass it to the extract_document_data tool. Return the JSON output exactly as provided by the tool.",
            expected_output="JSON string containing the application_id and extracted document data.",
            agent=ocr_agent,
            context=[intake_task]
        )

        normalization_task = Task(
            description="Take the JSON output from the OCR task and pass it to the normalize_extracted_data tool. Return the final unified applicant profile JSON exactly as provided by the tool.",
            expected_output="Unified applicant profile JSON string containing identity, financials, and confidence scores.",
            agent=normalization_agent,
            context=[ocr_task]
        )

        crew = Crew(
            agents=[intake_agent, ocr_agent, normalization_agent],
            tasks=[intake_task, ocr_task, normalization_task],
            process=Process.sequential,
            verbose=True
        )
        result = crew.kickoff()
        # Extract JSON from the final result (CrewAI might wrap it in markdown)
        result_str = str(result)
        if "```json" in result_str:
            result_str = result_str.split("```json")[1].split("```")[0].strip()
        elif "```" in result_str:
            result_str = result_str.split("```")[1].strip()
            
        profile = json.loads(result_str)
        return profile
    except Exception as e:
        logger.warning(f"CrewAI initialization failed: {e}. Falling back to direct tool execution.")
        try:
            from agents.document_intake.tools import intake_documents
            from agents.ocr_extraction.tools import extract_document_data
            from agents.data_normalization.tools import normalize_extracted_data
            
            intake_res = intake_documents.func(application_id)
            ocr_res = extract_document_data.func(intake_res)
            profile_res = normalize_extracted_data.func(ocr_res)
            return json.loads(profile_res)
        except Exception as fallback_e:
            import traceback
            err_msg = f"PIPELINE CRASH (Fallback also failed): {str(fallback_e)}\n{traceback.format_exc()}"
            logger.error(err_msg)
            with open("pipeline_error.log", "a") as f:
                f.write(f"\n\n--- Error at {application_id} ---\n{err_msg}\n")
            from db import update_status
            update_status(application_id, "ERROR")
            return {"application_id": application_id, "error": str(fallback_e)}

def evaluate_requirements(profile: dict, loan_amount: float, employment_type: str) -> dict:
    """
    Evaluates the unified profile against downstream agent requirement cards.
    Returns {"action": "PROCEED" | "DATA_REQUIRED" | "LOW_CONFIDENCE_RETRY", "missing": [...], "low_confidence": [...]}
    """
    from agents_base import REQUIREMENT_CARDS
    
    missing_docs = set()
    low_confidence_fields = []
    
    # Check identity documents
    docs_processed = [d.get("doc_type") for d in profile.get("documents_processed", [])]
    confidence_scores = profile.get("confidence_scores", {})
    
    # Hardcoded business rules mappings to Requirement Cards
    reqs = REQUIREMENT_CARDS.get("credit_risk", {})
    
    if "AADHAAR" not in docs_processed:
        missing_docs.add("AADHAAR")
    elif confidence_scores.get("aadhaar_number", 1.0) < REQUIREMENT_CARDS["fraud"]["min_confidence"]:
        low_confidence_fields.append("aadhaar_number")
        
    if "PAN" not in docs_processed:
        missing_docs.add("PAN")
    elif confidence_scores.get("pan_number", 1.0) < REQUIREMENT_CARDS["fraud"]["min_confidence"]:
        low_confidence_fields.append("pan_number")
        
    if loan_amount > 300000:
        if "BANK_STATEMENT" not in docs_processed:
            missing_docs.add("BANK_STATEMENT")
            
        if employment_type == "SALARIED" and "SALARY_SLIP" not in docs_processed:
            missing_docs.add("SALARY_SLIP")
            
        if employment_type == "SELF_EMPLOYED" and "ITR" not in docs_processed:
            missing_docs.add("ITR")
            
    if missing_docs:
        return {
            "action": "DATA_REQUIRED",
            "missing": list(missing_docs),
            "low_confidence": low_confidence_fields
        }
        
    if low_confidence_fields:
        return {
            "action": "LOW_CONFIDENCE_RETRY",
            "missing": [],
            "low_confidence": low_confidence_fields
        }
        
    return {
        "action": "PROCEED",
        "missing": [],
        "low_confidence": []
    }
