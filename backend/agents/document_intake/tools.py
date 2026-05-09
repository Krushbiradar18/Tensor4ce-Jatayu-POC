from crewai.tools import tool
import os
import tempfile
import uuid
import json

@tool("intake_documents")
def intake_documents(application_id: str) -> str:
    """
    Accepts uploaded files for a given application_id, identifies the document type,
    assigns doc_ids, and stores metadata.
    Returns a JSON string of the identified documents.
    """
    # Match the storage path used in main.py
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    base_dir = os.path.join(backend_dir, "data", "uploads", application_id)
    
    if not os.path.exists(base_dir):
        return json.dumps({"application_id": application_id, "documents": []})
        
    identified_docs = []
    
    # We map common file name patterns to document types since the frontend 
    # saves them with standard names like "aadhaar.png", "bank_statement.pdf"
    for filename in os.listdir(base_dir):
        file_path = os.path.join(base_dir, filename)
        if not os.path.isfile(file_path):
            continue
            
        doc_type = "UNKNOWN"
        name_lower = filename.lower()
        if "aadhaar" in name_lower:
            doc_type = "AADHAAR"
        elif "pan" in name_lower:
            doc_type = "PAN"
        elif "bank_statement" in name_lower:
            doc_type = "BANK_STATEMENT"
        elif "salary_slip" in name_lower:
            doc_type = "SALARY_SLIP"
        elif "itr" in name_lower:
            doc_type = "ITR"
            
        doc_id = f"DOC-{uuid.uuid4().hex[:8].upper()}"
        
        identified_docs.append({
            "doc_id": doc_id,
            "application_id": application_id,
            "filename": filename,
            "file_path": file_path,
            "doc_type": doc_type,
            "status": "INTAKED"
        })
        
    return json.dumps({
        "application_id": application_id,
        "documents": identified_docs
    })
