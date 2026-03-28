"""
backend/agents/credit_risk/app.py
===================================
FastAPI sub-app exposing the Credit Risk LangGraph agent via the A2A protocol.

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

app = FastAPI(title="Credit Risk Agent", version="1.0.0")

AGENT_CARD = {
    "name": "credit_risk_agent",
    "display_name": "Credit Risk Specialist",
    "description": (
        "LangGraph-powered specialist agent that computes Probability of Default (PD), "
        "assigns a risk band, runs macro overlay, and generates officer/customer narratives."
    ),
    "version": "1.0.0",
    "input_schema": "CreditRiskInput",
    "output_schema": "CreditRiskOutput",
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
def run_task(req: A2ATaskRequest):
    t0 = time.time()
    logger.info(f"[A2A][credit_risk] task_id={req.task_id} app_id={req.application_id}")
    try:
        from agents.credit_risk.agent import run_credit_risk_graph
        output = run_credit_risk_graph(req.application_id)
        return A2ATaskResponse(
            task_id=req.task_id,
            status="COMPLETED",
            output=output,
            processing_time_ms=round((time.time() - t0) * 1000, 1),
        )
    except Exception as e:
        logger.exception(f"[A2A][credit_risk] task failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
