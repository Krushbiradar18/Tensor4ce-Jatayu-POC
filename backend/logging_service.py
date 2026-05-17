"""
logging_service.py — Centralized Structured Logging for ARIA AI
================================================================
Provides:
  - AgentLogger   : per-agent logger with context propagation
  - log_llm_call  : hook for LLM client instrumentation
  - log_exception : standardized exception capture
  - @log_agent_execution : decorator for agent entry-points
  - @log_tool_execution  : decorator for tool functions

Usage (in any agent):
    from logging_service import AgentLogger
    logger = AgentLogger("credit_risk", application_id="APP-123")
    logger.info("Starting credit risk analysis")
    logger.llm("gemini-1.5-flash", prompt="...", response="...", exec_ms=423.0)
    logger.error("Bureau lookup failed", exc=e)
"""
from __future__ import annotations

import functools
import json
import logging
import queue
import threading
import time
import traceback
from typing import Any, Callable

import db
from data_masking import redact_pii

_py_logger = logging.getLogger(__name__)

# ── DB Logging Handler ─────────────────────────────────────────────────────────

# Map Python log levels → our log_level column values
_PY_LEVEL_MAP = {
    logging.DEBUG:    "DEBUG",
    logging.INFO:     "INFO",
    logging.WARNING:  "WARN",
    logging.ERROR:    "ERROR",
    logging.CRITICAL: "ERROR",
}

# Loggers to skip — avoid recursive loops and third-party noise
_SKIP_LOGGERS = {
    "httpcore", "httpx", "urllib3", "asyncio", "multipart",
    "uvicorn.access", "uvicorn.error", "matplotlib", "PIL",
    "paddleocr", "ppocr", "litellm", "LiteLLM", "crewai.telemetry",
    __name__,  # skip logging_service itself
}

# Module name → friendly agent_name stored in DB
# Keys are checked as startswith() prefixes, in order.
_AGENT_NAME_MAP: list[tuple[str, str]] = [
    ("agents.credit_risk",          "credit_risk"),
    ("agents.fraud",                "fraud"),
    ("agents.compliance",           "compliance"),
    ("agents.portfolio",            "portfolio"),
    ("agents.ocr_extraction",       "ocr_extraction"),
    ("agents.data_normalization",   "data_normalization"),
    ("orchestration.crew",          "orchestrator"),
    ("orchestration.a2a_client",    "orchestrator"),
    ("orchestration.document_pipeline", "orchestrator"),
    ("orchestration.mcp_tools",     "orchestrator"),
    ("orchestration",               "orchestrator"),
    ("orchestrator",                "orchestrator"),
    ("crew_runner",                 "orchestrator"),
    ("autonomous_decision",         "orchestrator"),
    ("graphs",                      "langgraph"),
    ("agent_adapters",              "agent_adapters"),
    ("dil",                         "dil"),
    ("document_extractor",          "document_extractor"),
    ("verification",                "verification"),
    ("tools",                       "tools"),
    ("services.rag",                "rag"),
    ("services.llm_extractor",      "llm_extractor"),
    ("llm_client",                  "llm_client"),
    ("llm_config",                  "llm_config"),
    ("mock_apis",                   "mock_apis"),
    ("auth",                        "auth"),
    ("db",                          "db"),
    ("main",                        "system"),
    ("agents_base",                 "system"),
    ("dataset_loader",              "system"),
]

# Regex to extract application_id (e.g. APP-07EF069F) from log messages
import re as _re
_APP_ID_RE = _re.compile(r'\bAPP-[A-F0-9]{6,10}\b', _re.IGNORECASE)


def _agent_name_from_logger(name: str) -> str:
    """Map a Python logger name to a specific agent name."""
    lower = name.lower()
    for prefix, agent in _AGENT_NAME_MAP:
        if lower == prefix or lower.startswith(prefix + "."):
            return agent
    # Fall back to first segment, capped at 30 chars
    return name.split(".")[0][:30] if name else "system"


def _category_from_agent(agent_name: str) -> str:
    if agent_name in ("credit_risk", "fraud", "compliance", "portfolio",
                      "orchestrator", "agent_adapters", "langgraph"):
        return "agent"
    if agent_name in ("llm_client", "llm_config", "llm_extractor"):
        return "llm"
    if agent_name in ("tools", "ocr_extraction", "data_normalization", "dil",
                      "document_extractor", "verification", "mock_apis"):
        return "tool"
    if agent_name in ("rag", "services"):
        return "integration"
    return "system"


def _extract_app_id(message: str) -> str | None:
    """Extract an application_id like APP-07EF069F from a log message."""
    m = _APP_ID_RE.search(message)
    return m.group(0).upper() if m else None



class DBLoggingHandler(logging.Handler):
    """
    A Python logging.Handler that writes log records to the PostgreSQL `logs`
    table via db.log_structured().

    Uses a background daemon thread + queue so that DB writes never block
    the main request thread. If the queue fills up or the DB write fails,
    the record is silently dropped — logging must never crash the app.
    """

    def __init__(self, max_queue: int = 2000):
        super().__init__()
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="db-log-writer")
        self._thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        # Skip loggers that would cause recursion or noise
        if record.name in _SKIP_LOGGERS:
            return
        for skip in _SKIP_LOGGERS:
            if record.name.startswith(skip):
                return
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            pass  # Drop silently — never crash the app

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                record = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                self._write(record)
            except Exception:
                pass  # Absolutely never crash the worker thread
            finally:
                self._queue.task_done()

    def _write(self, record: logging.LogRecord) -> None:
        level = _PY_LEVEL_MAP.get(record.levelno, "INFO")

        # Precise agent name from module path
        agent_name = _agent_name_from_logger(record.name)
        category   = _category_from_agent(agent_name)

        # Grab exc_info if present
        error_type: str | None = None
        stack_trace: str | None = None
        if record.exc_info and record.exc_info[0] is not None:
            error_type  = record.exc_info[0].__name__
            stack_trace = "".join(traceback.format_exception(*record.exc_info))

        # Format the message safely
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()

        # Trim extremely long messages
        if len(message) > 4000:
            message = message[:4000] + "… [truncated]"

        # Try to pull application_id out of the message text
        application_id = _extract_app_id(message)

        db.log_structured(
            agent_name=agent_name,
            log_level=level,
            log_category=category,
            message=message,
            application_id=application_id,
            error_type=error_type,
            stack_trace=stack_trace,
        )


    def stop(self) -> None:
        """Gracefully stop the background writer thread."""
        self._stop_event.set()
        self._thread.join(timeout=3)


# Singleton handler instance — installed once at startup
_db_handler: DBLoggingHandler | None = None


def install_db_logging_handler(level: int = logging.DEBUG) -> DBLoggingHandler:
    """
    Install the DBLoggingHandler on the root logger.
    Safe to call multiple times — only installs once.
    """
    global _db_handler
    if _db_handler is not None:
        return _db_handler

    _db_handler = DBLoggingHandler()
    _db_handler.setLevel(level)
    _db_handler.setFormatter(logging.Formatter("%(name)s | %(message)s"))

    root = logging.getLogger()
    root.addHandler(_db_handler)
    _py_logger.info("DBLoggingHandler installed — all logs now persisted to DB.")
    return _db_handler


def remove_db_logging_handler() -> None:
    """Remove and stop the DB handler (called at shutdown)."""
    global _db_handler
    if _db_handler is None:
        return
    logging.getLogger().removeHandler(_db_handler)
    _db_handler.stop()
    _db_handler = None



def _safe_json(value: Any) -> str | None:
    """Serialize value to JSON string, gracefully truncate if too large."""
    if value is None:
        return None
    try:
        # Redact PII from the value before serialization to avoid storing raw PII
        try:
            safe_value = redact_pii(value)
        except Exception:
            safe_value = value
        s = json.dumps(safe_value, default=str)
        # Cap at 8 KB to avoid bloating the DB
        return s[:8192] if len(s) > 8192 else s
    except Exception:
        return str(value)[:8192]


def log_llm_call(
    agent_name: str,
    model_name: str,
    prompt: str,
    response: str,
    exec_ms: float,
    *,
    application_id: str | None = None,
    error: Exception | None = None,
    metadata: dict | None = None,
) -> None:
    """
    Hook called by llm_client.get_llm_response() after every LLM invocation.
    Writes a structured log entry to the `logs` table.
    """
    level = "ERROR" if error else "INFO"
    message = (
        f"LLM call to {model_name} completed in {exec_ms:.0f}ms"
        if not error
        else f"LLM call to {model_name} FAILED after {exec_ms:.0f}ms: {error}"
    )
    try:
        db.log_structured(
            agent_name=agent_name,
            log_level=level,
            log_category="llm",
            message=message,
            application_id=application_id,
            llm_model_name=model_name,
            input_data=_safe_json({"prompt": prompt[:2000]}),  # truncate prompt for storage
            output_data=_safe_json({"response": response[:2000] if response else None}),
            execution_time_ms=exec_ms,
            error_type=type(error).__name__ if error else None,
            stack_trace=traceback.format_exc() if error else None,
            metadata=metadata,
        )
    except Exception as exc:
        _py_logger.warning("logging_service: failed to write LLM log: %s", exc)


def log_exception(
    agent_name: str,
    exc: Exception,
    message: str = "",
    *,
    application_id: str | None = None,
    log_category: str = "agent",
    context: dict | None = None,
) -> None:
    """Write a structured ERROR log for an exception."""
    try:
        db.log_structured(
            agent_name=agent_name,
            log_level="ERROR",
            log_category=log_category,
            message=message or str(exc),
            application_id=application_id,
            error_type=type(exc).__name__,
            stack_trace=traceback.format_exc(),
            metadata=context,
        )
    except Exception as inner:
        _py_logger.warning("logging_service: failed to write exception log: %s", inner)


# ── Decorators ─────────────────────────────────────────────────────────────────


def log_agent_execution(agent_name: str, category: str = "agent"):
    """
    Decorator that auto-logs agent function start, success, and errors.

    Usage:
        @log_agent_execution("credit_risk")
        def run(state: dict) -> dict:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            app_id = kwargs.get("application_id") or (
                args[0].get("application_id") if args and isinstance(args[0], dict) else None
            )
            start = time.perf_counter()
            try:
                db.log_structured(
                    agent_name=agent_name,
                    log_level="INFO",
                    log_category=category,
                    message=f"{agent_name} execution started",
                    application_id=app_id,
                )
            except Exception:
                pass

            try:
                result = func(*args, **kwargs)
                exec_ms = (time.perf_counter() - start) * 1000
                try:
                    db.log_structured(
                        agent_name=agent_name,
                        log_level="INFO",
                        log_category=category,
                        message=f"{agent_name} execution completed in {exec_ms:.0f}ms",
                        application_id=app_id,
                        execution_time_ms=exec_ms,
                    )
                except Exception:
                    pass
                return result
            except Exception as exc:
                exec_ms = (time.perf_counter() - start) * 1000
                log_exception(
                    agent_name, exc,
                    message=f"{agent_name} execution FAILED: {exc}",
                    application_id=app_id,
                    log_category=category,
                    context={"exec_ms": exec_ms},
                )
                raise

        return wrapper
    return decorator


def log_tool_execution(tool_name: str, agent_name: str = "system"):
    """
    Decorator that auto-logs tool function calls with input args, output, and timing.

    Usage:
        @log_tool_execution("bureau_check_tool", agent_name="credit_risk")
        def bureau_check(pan: str) -> dict:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            input_summary = _safe_json({"args": str(args)[:500], "kwargs": str(kwargs)[:500]})
            try:
                result = func(*args, **kwargs)
                exec_ms = (time.perf_counter() - start) * 1000
                try:
                    db.log_structured(
                        agent_name=agent_name,
                        log_level="INFO",
                        log_category="tool",
                        message=f"Tool '{tool_name}' completed in {exec_ms:.0f}ms",
                        tool_name=tool_name,
                        input_data=input_summary,
                        output_data=_safe_json(result)[:2000] if result else None,
                        execution_time_ms=exec_ms,
                    )
                except Exception:
                    pass
                return result
            except Exception as exc:
                exec_ms = (time.perf_counter() - start) * 1000
                try:
                    db.log_structured(
                        agent_name=agent_name,
                        log_level="ERROR",
                        log_category="tool",
                        message=f"Tool '{tool_name}' FAILED: {exc}",
                        tool_name=tool_name,
                        input_data=input_summary,
                        execution_time_ms=exec_ms,
                        error_type=type(exc).__name__,
                        stack_trace=traceback.format_exc(),
                    )
                except Exception:
                    pass
                raise

        return wrapper
    return decorator


# ── AgentLogger class ──────────────────────────────────────────────────────────


class AgentLogger:
    """
    Per-agent context-aware logger.

    Usage:
        logger = AgentLogger("fraud", application_id="APP-XYZ")
        logger.info("Starting fraud checks")
        logger.warn("Soft signal: form fill too fast")
        logger.error("Hard rule fired: PAN blacklisted", exc=e)
        logger.llm("gemini-1.5-flash", prompt="...", response="...", exec_ms=320)
        logger.tool("ip_lookup_tool", input={"ip": "1.2.3.4"}, output={"score": 0.8}, exec_ms=45)
    """

    def __init__(
        self,
        agent_name: str,
        *,
        application_id: str | None = None,
        category: str = "agent",
    ):
        self.agent_name = agent_name
        self.application_id = application_id
        self.category = category

    def _write(
        self,
        level: str,
        message: str,
        category: str | None = None,
        **kwargs,
    ) -> None:
        try:
            db.log_structured(
                agent_name=self.agent_name,
                log_level=level,
                log_category=category or self.category,
                message=message,
                application_id=self.application_id,
                **kwargs,
            )
        except Exception as exc:
            _py_logger.warning("AgentLogger._write failed: %s", exc)

    def debug(self, message: str, **kwargs) -> None:
        self._write("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        self._write("INFO", message, **kwargs)

    def warn(self, message: str, **kwargs) -> None:
        self._write("WARN", message, **kwargs)

    def error(self, message: str, exc: Exception | None = None, **kwargs) -> None:
        extra: dict = {}
        if exc:
            extra["error_type"] = type(exc).__name__
            extra["stack_trace"] = traceback.format_exc()
        self._write("ERROR", message, **{**extra, **kwargs})

    def llm(
        self,
        model_name: str,
        *,
        prompt: str = "",
        response: str = "",
        exec_ms: float = 0.0,
        error: Exception | None = None,
        metadata: dict | None = None,
    ) -> None:
        log_llm_call(
            agent_name=self.agent_name,
            model_name=model_name,
            prompt=prompt,
            response=response,
            exec_ms=exec_ms,
            application_id=self.application_id,
            error=error,
            metadata=metadata,
        )

    def tool(
        self,
        tool_name: str,
        *,
        input: Any = None,
        output: Any = None,
        exec_ms: float = 0.0,
        error: Exception | None = None,
    ) -> None:
        level = "ERROR" if error else "INFO"
        extra: dict = {}
        if error:
            extra["error_type"] = type(error).__name__
            extra["stack_trace"] = traceback.format_exc()
        self._write(
            level,
            f"Tool '{tool_name}' {'FAILED: ' + str(error) if error else f'completed in {exec_ms:.0f}ms'}",
            category="tool",
            tool_name=tool_name,
            input_data=_safe_json(input),
            output_data=_safe_json(output),
            execution_time_ms=exec_ms,
            **extra,
        )
