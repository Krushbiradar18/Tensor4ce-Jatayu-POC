"""
backend/agents/compliance/app.py
==================================
FastAPI sub-app exposing the Compliance LangGraph agent via A2A protocol.

Endpoints:
  GET  /.well-known/agent.json   → Agent Card
  POST /a2a/tasks/send           → Execute the agent and return typed output
"""
from __future__ import annotations
import time
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="Compliance Agent", version="1.0.0")

AGENT_CARD = {
    "name": "compliance_agent",
    "display_name": "Compliance Specialist",
    "description": (
        "LangGraph-powered specialist agent that evaluates all 12 RBI compliance rules deterministically. "
        "Uses Gemini CoT for WARNING-severity flags. Checks fraud_blacklist for C007."
    ),
    "version": "1.0.0",
    "input_schema": "ComplianceInput",
    "output_schema": "ComplianceOutput",
    "endpoints": {
        "agent_card": "/.well-known/agent.json",
        "task": "/a2a/tasks/send",
    },
}


class A2ATaskRequest(BaseModel):
    task_id: str
    application_id: str
    payload: dict = {}
    timeout_seconds: int = 120


class A2ATaskResponse(BaseModel):
    task_id: str
    status: str
    output: dict
    processing_time_ms: float


@app.get("/.well-known/agent.json")
async def agent_card():
    return AGENT_CARD


@app.post("/a2a/tasks/send", response_model=A2ATaskResponse)
async def run_task(req: A2ATaskRequest):
    t0 = time.time()
    logger.info(f"[A2A][compliance] task_id={req.task_id} app_id={req.application_id}")
    try:
        from agents.compliance.agent import run_compliance_graph
        output = run_compliance_graph(req.application_id)
        return A2ATaskResponse(
            task_id=req.task_id,
            status="COMPLETED",
            output=output,
            processing_time_ms=round((time.time() - t0) * 1000, 1),
        )
    except Exception as e:
        logger.exception(f"[A2A][compliance] task failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
