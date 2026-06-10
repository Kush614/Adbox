"""DEMO_MODE support: load pre-baked successful runs from backend/demo/*.json.

Insurance against venue Wi-Fi / API hiccups during judging. A demo run is a
serialized RunState whose image URLs point at committed files under
backend/static/runs/<run_id>/. Loading one is instant and offline.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import RunState

DEMO_DIR = Path(__file__).parent / "demo"


def list_demos() -> list[Path]:
    if not DEMO_DIR.exists():
        return []
    return sorted(DEMO_DIR.glob("*.json"))


def load_demo(brief: str | None = None) -> RunState | None:
    """Return a cached RunState. If brief is given, prefer the closest match by
    shared keywords; otherwise return the first demo."""
    demos = list_demos()
    if not demos:
        return None

    best: Path = demos[0]
    if brief:
        brief_words = {w for w in brief.lower().split() if len(w) > 3}
        best_score = -1
        for p in demos:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            cand = str(data.get("brief", "")).lower()
            score = sum(1 for w in brief_words if w in cand)
            if score > best_score:
                best_score, best = score, p

    try:
        state = RunState(**json.loads(best.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    state.demo_mode = True
    return state
