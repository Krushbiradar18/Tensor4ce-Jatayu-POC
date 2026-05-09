from crewai import Agent
import os

def get_document_intake_agent(llm=None):
    from .tools import intake_documents
    
    if llm is None:
        # Default LLM resolution logic from orchestration/crew.py
        from orchestration.crew import _build_llm
        llm = _build_llm()
        
    return Agent(
        role="Document Intake Specialist",
        goal="Accept uploaded files for a loan application, identify their document type, assign document IDs, and store the metadata.",
        backstory="You are a meticulous Document Intake Specialist. When a user uploads loan application documents, your job is to scan the storage directory, identify which files are Aadhaar, PAN, Bank Statements, Salary Slips, or ITRs, and formally register them into the system by assigning a doc_id to each.",
        verbose=True,
        allow_delegation=False,
        tools=[intake_documents],
        llm=llm,
    )
