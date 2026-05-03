"""
backend/llm_client.py — Single LLM abstraction for all agents.
================================================================
Swap between direct Gemini API and Vertex AI via LiteLLM
using the LLM_BACKEND environment variable.

Usage:
  from llm_client import get_llm_response
  text = get_llm_response("Your prompt here")

Config (.env):
  LLM_BACKEND=gemini      # (default) direct google.genai SDK
  LLM_BACKEND=vertex      # Vertex AI via LiteLLM
  LLM_MODEL=gemini-2.0-flash     # model name (default)
"""
import os
import logging
import threading
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import litellm
    from litellm.caching import Cache
    litellm.cache = Cache() # Local in-memory cache
except ImportError:
    litellm = None

logger = logging.getLogger(__name__)

LLM_BACKEND: str = os.getenv("LLM_BACKEND", "gemini")
LLM_MODEL: str = os.getenv("GEMINI_MODEL") or os.getenv("LLM_MODEL", "gemini-1.5-flash")

# Global semaphore to strictly serialize LLM calls across all agents/threads
# This is the most robust way to prevent 429s on restricted free-tier quotas.
_LLM_SEMAPHORE = threading.Semaphore(1)


def get_llm_response(prompt: str, max_tokens: int = 1000) -> str:
    """
    Single entry point for all LLM calls across all agents.
    Uses a global semaphore to ensure only one call is active at a time.
    """
    with _LLM_SEMAPHORE:
        # Add a tiny buffer between calls to respect burst limits
        time.sleep(0.5)

        if LLM_BACKEND == "groq":
            return _call_groq(prompt, max_tokens)
        elif LLM_BACKEND == "vertex":
            return _call_vertex(prompt, max_tokens)
        else:
            return _call_gemini(prompt, max_tokens)


def _call_groq(prompt: str, max_tokens: int) -> str:
    """Call Groq API using the groq SDK."""
    from groq import Groq
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set in environment.")
    model = os.getenv("GROQ_MODEL_NARRATIVE", "llama-3.1-8b-instant")
    # Strip groq/ prefix if present (Groq SDK doesn't need it)
    if model.startswith("groq/"):
        model = model[5:]
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.1,
    )
    return response.choices[0].message.content.strip()


def _call_gemini(prompt: str, max_tokens: int) -> str:
    """
    Call Gemini via the new google.genai SDK (google-genai package).
    Falls back to deprecated google.generativeai if new SDK not available.
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY not set in environment. "
            "Add GEMINI_API_KEY=<your-key> to .env"
        )

    # Try new google.genai SDK (google-genai package)
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=prompt,
        )
        return response.text.strip()
    except ImportError:
        pass

    # Fallback: deprecated google.generativeai (google-generativeai package)
    try:
        import google.generativeai as genai_legacy  # type: ignore[import]
        genai_legacy.configure(api_key=api_key)
        model = genai_legacy.GenerativeModel(LLM_MODEL)
        response = model.generate_content(
            prompt,
            generation_config={"max_output_tokens": max_tokens},
        )
        return response.text.strip()
    except ImportError:
        raise ImportError(
            "Neither google-genai nor google-generativeai is installed. "
            "Run: pip install google-genai"
        )


def _call_vertex(prompt: str, max_tokens: int) -> str:
    """
    Call Gemini via Vertex AI using LiteLLM.
    Requires: pip install litellm
    Requires: gcloud auth application-default login
    Requires: VERTEX_PROJECT (or GOOGLE_CLOUD_PROJECT) set in .env
    """
    if litellm is None:
        raise ImportError(
            "litellm not installed. Run: pip install litellm"
        )

    # Set required Vertex env vars from project .env conventions
    gcp_project = (
        os.getenv("VERTEX_PROJECT")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("VERTEXAI_PROJECT")
    )
    if gcp_project:
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", gcp_project)
        os.environ.setdefault("VERTEXAI_PROJECT", gcp_project)

    vertex_location = (
        os.getenv("VERTEX_LOCATION")
        or os.getenv("VERTEXAI_LOCATION", "us-central1")
    )
    os.environ.setdefault("VERTEXAI_LOCATION", vertex_location)

    vertex_model = f"vertex_ai/{LLM_MODEL}"
    logger.debug(f"Calling Vertex AI: model={vertex_model}, project={gcp_project}")

    response = litellm.completion(
        model=vertex_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        num_retries=5,
    )
    return response.choices[0].message.content.strip()
