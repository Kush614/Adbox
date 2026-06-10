"""Per-run cost / latency tracking.

The ledger is the Akamai pitch made visible: it proves the cheap "fast" tier
handled most of the tokens while the expensive "smart" tier ran exactly once,
and it shows every deliberate Magnific credit spend.
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Iterator

from .models import StageRecord


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def llm_cost_usd(tier: str, tokens_in: int, tokens_out: int) -> float:
    """Rough $ estimate using per-model $/Mtok constants from env."""
    if tier == "smart":
        per_mtok = _env_float("COST_SMART_PER_MTOK", 1.00)
    else:
        per_mtok = _env_float("COST_FAST_PER_MTOK", 0.10)
    return round((tokens_in + tokens_out) / 1_000_000 * per_mtok, 6)


@contextmanager
def stage_timer(stage: str, engine: str) -> Iterator[StageRecord]:
    """Time a stage and hand back a StageRecord the caller can enrich.

    Latency is always recorded, even if the body raises (the record's `ok`
    is left for the caller to flip to False on failure).
    """
    rec = StageRecord(stage=stage, model_or_engine=engine)
    start = time.perf_counter()
    try:
        yield rec
    finally:
        rec.latency_ms = int((time.perf_counter() - start) * 1000)


def summarize(stages: list[StageRecord]) -> dict:
    """Aggregate stats for the UI headline ("fast tier did X% of tokens")."""
    llm_stages = [s for s in stages if s.tokens_in or s.tokens_out]
    total_tokens = sum(s.tokens_in + s.tokens_out for s in llm_stages)
    fast_tokens = sum(
        s.tokens_in + s.tokens_out
        for s in llm_stages
        if "smart" not in s.model_or_engine.lower() and s.stage in ("concepts", "json_repair")
    )
    # Anything tagged as the concepts/repair stage is the fast tier; param_plan
    # and listing_copy are the smart tier's single planned calls.
    smart_calls = sum(1 for s in llm_stages if s.stage in ("param_plan", "listing_copy"))
    return {
        "total_tokens": total_tokens,
        "fast_token_pct": round(100 * fast_tokens / total_tokens, 1) if total_tokens else 0.0,
        "smart_calls": smart_calls,
        "total_llm_cost_usd": round(sum(s.est_cost_usd for s in stages), 6),
        "total_credits": sum(s.credits for s in stages),
        "total_latency_ms": sum(s.latency_ms for s in stages),
    }
