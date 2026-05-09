from crewai import Agent

def get_data_normalization_agent(llm=None):
    from .tools import normalize_extracted_data
    
    if llm is None:
        from orchestration.crew import _build_llm
        llm = _build_llm()
        
    return Agent(
        role="Data Normalization Specialist",
        goal="Merge structured JSON data extracted from multiple documents, remove duplicates, resolve conflicting information, and generate a single unified applicant profile.",
        backstory="You are a Data Normalization Specialist. Your task is to receive multiple JSON payloads from the OCR agent (representing different documents like Aadhaar, PAN, Bank Statements), intelligently merge them, keep the data with the highest confidence scores, and output a pristine, unified Applicant Profile JSON.",
        verbose=True,
        allow_delegation=False,
        tools=[normalize_extracted_data],
        llm=llm,
    )
