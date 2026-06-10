"""FastAPI app: submit a brief, run the pipeline in the background, poll state.

Run state lives in an in-memory dict (no DB). The frontend is a single static
HTML file served at /, polling GET /run/{id} for streamed progress.
"""
from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from pathlib import Path  # noqa: E402

from . import demo as demo_mod  # noqa: E402
from . import listing_factory  # noqa: E402
from .ledger import summarize  # noqa: E402
from .models import ListingRun, RunState  # noqa: E402
from .pipeline import run_pipeline  # noqa: E402

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
FRONTEND = BASE_DIR.parent / "frontend" / "index.html"

STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Ad-in-a-Box", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# In-memory run store: run_id -> RunState
RUNS: dict[str, RunState] = {}
LISTING_RUNS: dict[str, ListingRun] = {}


class RunRequest(BaseModel):
    brief: str


def _demo_enabled() -> bool:
    return os.getenv("DEMO_MODE", "0").strip() not in ("", "0", "false", "False")


@app.get("/")
async def index():
    if FRONTEND.exists():
        return FileResponse(str(FRONTEND))
    return JSONResponse({"detail": "frontend/index.html not found"}, status_code=404)


@app.get("/health")
async def health():
    return {
        "ok": True,
        "demo_mode": _demo_enabled(),
        "model_fast": os.getenv("MODEL_FAST", ""),
        "model_smart": os.getenv("MODEL_SMART", ""),
        "akamai_base": os.getenv("AKAMAI_BASE_URL", ""),
        "freepik_key_set": bool(os.getenv("FREEPIK_API_KEY", "").strip()),
    }


@app.post("/run")
async def create_run(req: RunRequest, background: BackgroundTasks):
    brief = (req.brief or "").strip()
    if not brief:
        raise HTTPException(status_code=400, detail="brief is required")

    run_id = uuid.uuid4().hex[:8]

    if _demo_enabled():
        cached = demo_mod.load_demo(brief)
        if cached is not None:
            cached.run_id = run_id
            cached.brief = brief
            RUNS[run_id] = cached
            return {"run_id": run_id, "demo_mode": True}
        # No cached demo available; fall through to a live run.

    state = RunState(run_id=run_id, brief=brief)
    RUNS[run_id] = state
    background.add_task(run_pipeline, state, STATIC_DIR)
    return {"run_id": run_id, "demo_mode": False}


@app.get("/run/{run_id}")
async def get_run(run_id: str):
    state = RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="run not found")
    all_stages = list(state.stages)
    for c in state.creatives:
        all_stages.extend(c.stages)
    payload = state.model_dump()
    payload["ledger_summary"] = summarize(all_stages)
    return payload


# --- E-commerce Listing Factory ------------------------------------------
@app.post("/listings")
async def create_listing_run():
    """Run the listing factory. In demo mode this replays the cached run with
    real captured Magnific output; live runs need a Magnific REST key + photos."""
    run_id = uuid.uuid4().hex[:8]
    if _demo_enabled():
        cached = listing_factory.load_demo()
        if cached is not None:
            cached.run_id = run_id
            LISTING_RUNS[run_id] = cached
            return {"run_id": run_id, "demo_mode": True}
    raise HTTPException(
        status_code=503,
        detail="No cached listing run and no live Magnific key. "
        "Run scripts/build_listing_demo.py, or set DEMO_MODE=1.",
    )


@app.get("/listings/{run_id}")
async def get_listing_run(run_id: str):
    state = LISTING_RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="listing run not found")
    all_stages = list(state.stages)
    for it in state.items:
        all_stages.extend(it.stages)
    payload = state.model_dump()
    payload["ledger_summary"] = summarize(all_stages)
    return payload
