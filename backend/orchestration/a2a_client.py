"""
backend/orchestration/a2a_client.py
=====================================
A2A Protocol client — sends typed HTTP task requests to LangGraph agent sub-apps.

Usage (called from crew.py):
    from orchestration.a2a_client import call_agent

Each agent is a FastAPI sub-app mounted on the main app. Since they share
the same process, we call them via HTTP to maintain A2A protocol compliance.
The base URL defaults to localhost:8000 and can be overridden via A2A_BASE_URL env var.
"""
from __future__ import annotations
import os
import uuid
import time
import logging
import httpx

logger = logging.getLogger(__name__)

# Base URL for A2A calls — defaults to same-process local server
A2A_BASE_URL = os.environ.get("A2A_BASE_URL", "http://127.0.0.1:8000")

AGENT_PATHS = {
    "credit_risk": "/agents/credit-risk",
    "fraud":       "/agents/fraud",
    "compliance":  "/agents/compliance",
    "portfolio":   "/agents/portfolio",
}


def _resolve_timeout(agent_name: str, timeout: int | None) -> int:
    if timeout is not None:
        return int(timeout)
    agent_key = f"A2A_TIMEOUT_{agent_name.upper()}"
    # Fraud can be slower due to optional LLM explanation path.
    default_map = {
        "fraud": 180,
    }
    default_timeout = default_map.get(agent_name, 120)
    return int(os.environ.get(agent_key, os.environ.get("A2A_DEFAULT_TIMEOUT_SECONDS", str(default_timeout))))


def _resolve_retries() -> int:
    # Total attempts = 1 + retries. Defaults to 1 retry.
    return max(0, int(os.environ.get("A2A_RETRY_COUNT", "1")))


def call_agent(
    agent_name: str,
    application_id: str,
    payload: dict | None = None,
    timeout: int | None = None,
) -> dict:
    """
    Send an A2A task request to a specialist LangGraph agent.

    Args:
        agent_name:     One of credit_risk, fraud, compliance, portfolio
        application_id: The loan application ID
        payload:        Optional additional context (e.g., credit_risk_output for portfolio)
        timeout:        Request timeout in seconds

    Returns:
        The agent output dict from the A2A response
    """
    base_path = AGENT_PATHS.get(agent_name)
    if not base_path:
        raise ValueError(f"Unknown agent: {agent_name}. Must be one of {list(AGENT_PATHS.keys())}")

    task_id  = f"TASK-{uuid.uuid4().hex[:10].upper()}"
    endpoint = f"{A2A_BASE_URL}{base_path}/a2a/tasks/send"

    resolved_timeout = _resolve_timeout(agent_name, timeout)
    body = {
        "task_id":          task_id,
        "application_id":   application_id,
        "payload":          payload or {},
        "timeout_seconds":  resolved_timeout,
    }

    retries = _resolve_retries()
    attempts = 1 + retries
    logger.info(
        f"[A2A] → {agent_name} | task={task_id} | app={application_id} | timeout={resolved_timeout}s | attempts={attempts}"
    )

    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req_timeout = httpx.Timeout(
                connect=min(10, resolved_timeout),
                read=resolved_timeout,
                write=30,
                pool=10,
            )
            with httpx.Client(timeout=req_timeout) as client:
                resp = client.post(endpoint, json=body)
                resp.raise_for_status()
                data = resp.json()
                logger.info(
                    f"[A2A] ← {agent_name} | status={data.get('status')} | {data.get('processing_time_ms', 0):.0f}ms"
                )
                return data.get("output", {})
        except httpx.HTTPStatusError as e:
            logger.error(f"[A2A] {agent_name} HTTP error: {e.response.status_code} — {e.response.text[:200]}")
            raise
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException, httpx.NetworkError) as e:
            last_exc = e
            if attempt >= attempts:
                logger.error(f"[A2A] {agent_name} timeout/network error after {attempt} attempts: {e}")
                raise
            backoff = min(2 ** (attempt - 1), 5)
            logger.warning(
                f"[A2A] {agent_name} transient timeout/network error (attempt {attempt}/{attempts}): {e}; retrying in {backoff}s"
            )
            time.sleep(backoff)
        except Exception as e:
            logger.error(f"[A2A] {agent_name} connection error: {e}")
            raise

    if last_exc:
        raise last_exc
    raise RuntimeError(f"[A2A] Unexpected empty result for agent {agent_name}")


def get_agent_card(agent_name: str) -> dict:
    """Retrieve the Agent Card for a specialist agent."""
    base_path = AGENT_PATHS.get(agent_name, "")
    endpoint = f"{A2A_BASE_URL}{base_path}/.well-known/agent.json"
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(endpoint)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning(f"[A2A] Could not fetch agent card for {agent_name}: {e}")
        return {}
