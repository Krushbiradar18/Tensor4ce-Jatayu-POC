"""
mock_api.py — Standalone compliance mock API server.
Delegates all routes to compliance_router.py (shared router).

Run standalone:  uvicorn mock_api:app --reload --port 8001
Or mounted via:  app.py at project root (port 8000)
"""
from fastapi import FastAPI
from compliance_router import router

app = FastAPI(title="Compliance Agent Mock APIs")
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mock_api:app", host="0.0.0.0", port=8001, reload=True)
