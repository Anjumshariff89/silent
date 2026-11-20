"""FastAPI entrypoint. Endpoints are implemented in Step 4+; see PROJECT_STATE.md for the contract."""
from fastapi import FastAPI

app = FastAPI(title="Logs the Attacker Can't Erase", version="0.1.0")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "phase": "step-1-scaffold"}
