"""
backend/agents/portfolio/app.py
=================================
FastAPI sub-app exposing the Portfolio Intelligence LangGraph agent via A2A protocol.

Endpoints:
  GET  /.well-known/agent.json   → Agent Card
  POST /a2a/tasks/send           → Execute the agent and return typed output

Note: Portfolio agent receives the Credit Risk output in the A2A payload,
      which is why it runs last in the CrewAI orchestration sequence.
"""
from __future__ import annotations
import time
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="Portfolio Intelligence Agent", version="1.0.0")

AGENT_CARD = {
    "name": "portfolio_agent",
    "display_name": "Portfolio Intelligence Specialist",
    "description": (
        "LangGraph-powered specialist agent that computes Expected Loss impact, "
        "checks sector/geo concentration limits (35% threshold), queries similar historical cases, "
        "and generates a portfolio diversification recommendation via Gemini CoT."
    ),
    "version": "1.0.0",
    "input_schema": "PortfolioInput",
    "output_schema": "PortfolioOutput",
    "endpoints": {
        "agent_card": "/.well-known/agent.json",
        "task": "/a2a/tasks/send",
    },
}


class A2ATaskRequest(BaseModel):
    task_id: str
    application_id: str
    payload: dict = {}          # Should include credit_risk_output for EL calculation
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
    logger.info(f"[A2A][portfolio] task_id={req.task_id} app_id={req.application_id}")
    try:
        from agents.portfolio.agent import run_portfolio_graph
        # Credit Risk output passed via payload (A2A context injection from CrewAI)
        credit_risk_output = req.payload.get("credit_risk_output", {})
        output = run_portfolio_graph(req.application_id, credit_risk_output)
        return A2ATaskResponse(
            task_id=req.task_id,
            status="COMPLETED",
            output=output,
            processing_time_ms=round((time.time() - t0) * 1000, 1),
        )
    except Exception as e:
        logger.exception(f"[A2A][portfolio] task failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
