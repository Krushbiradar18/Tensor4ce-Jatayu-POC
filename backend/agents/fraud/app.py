"""
backend/agents/fraud/app.py
============================
FastAPI sub-app exposing the Fraud Detection LangGraph agent via A2A protocol.

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

app = FastAPI(title="Fraud Risk Agent", version="1.0.0")

AGENT_CARD = {
    "name": "fraud_agent",
    "display_name": "Fraud Detection Specialist",
    "description": (
        "LangGraph-powered specialist agent that evaluates fraud signals using hard rules, "
        "soft behavioural indicators, and IP risk analysis. Calls Gemini for SUSPICIOUS cases."
    ),
    "version": "1.0.0",
    "input_schema": "FraudInput",
    "output_schema": "FraudOutput",
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
    logger.info(f"[A2A][fraud] task_id={req.task_id} app_id={req.application_id}")
    try:
        from agents.fraud.agent import run_fraud_graph
        output = run_fraud_graph(req.application_id)
        return A2ATaskResponse(
            task_id=req.task_id,
            status="COMPLETED",
            output=output,
            processing_time_ms=round((time.time() - t0) * 1000, 1),
        )
    except Exception as e:
        logger.exception(f"[A2A][fraud] task failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
