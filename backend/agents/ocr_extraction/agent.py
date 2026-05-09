from crewai import Agent

def get_ocr_extraction_agent(llm=None):
    from .tools import extract_document_data
    
    if llm is None:
        from orchestration.crew import _build_llm
        llm = _build_llm()
        
    return Agent(
        role="OCR & Extraction Specialist",
        goal="Extract raw text from documents using OCR, clean noisy text, convert it to structured JSON using LLM, and assign confidence scores.",
        backstory="You are an expert OCR & Data Extraction Specialist. You receive document metadata from the Intake agent, run advanced OCR and Vision models on the files, and structure the data into highly accurate JSON formats with associated confidence scores.",
        verbose=True,
        allow_delegation=False,
        tools=[extract_document_data],
        llm=llm,
    )
