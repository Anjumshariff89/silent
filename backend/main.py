"""ASGI entrypoint: `uvicorn backend.main:app`. Contract: PROJECT_STATE.md."""
from backend.app.factory import create_app

app = create_app()
