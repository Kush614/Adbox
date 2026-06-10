"""E-commerce Listing Factory: messy seller photos -> clean storefront listings.

Pipeline per batch:
  1. (smart tier LLM) For every ingested photo label, write an SEO title +
     description + tags + category + suggested price, AND decide the Magnific
     enhancement params (background removal? relight direction? upscale factor?).
  2. (Magnific) background removal -> relight -> upscale into a storefront-ready
     image.
  3. Aggregate into a listings table the seller can paste into a marketplace.

Mirrors backend/pipeline.py: live image stages need a Magnific REST key; at the
venue the demo replays a pre-baked cache (backend/demo/listings.json) whose
images are real Magnific output captured via the MCP. See scripts/build_listing_demo.py.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from pydantic import ValidationError

from . import magnific
from .llm import LLMError, chat_json
from .magnific import BudgetExceeded, MagnificBudget, MagnificError
from .models import ListingItem, ListingRun, StageRecord

DEMO_DIR = Path(__file__).parent / "demo"
MAX_IN_FLIGHT = 3

# --------------------------------------------------------------------------
# Stage 1 (smart tier): SEO copy + per-image enhancement decision
# --------------------------------------------------------------------------
_LISTING_SYSTEM = """You are an e-commerce merchandising expert and product
photographer. For each messy seller photo (described by a short label), you:
1. Write marketplace-ready SEO copy.
2. Decide how Magnific should clean the photo into a storefront-ready shot.

You understand Magnific's controls:
- remove_background: true to cut the product out of its messy scene onto a clean
  studio backdrop (almost always true for marketplace listings).
- relight_prompt: phrase studio lighting as direction + quality + color temp,
  e.g. "soft neutral studio key from upper-left, gentle fill, crisp specular
  highlight". Tailor to the material (matte vs glossy vs metal vs leather).
- upscale_factor: "2x" | "4x". Use "4x" for hero/detail products, "2x" otherwise.

Return STRICT JSON only, shape:
{"listings": [
  {"id": "p1", "title": "...", "description": "...", "tags": ["..."],
   "category": "...", "suggested_price": "$49", "remove_background": true,
   "relight_prompt": "...", "upscale_factor": "2x",
   "rationale": "one sentence: why this copy + these enhancement params"}
]}

Rules:
- title <= 12 words, keyword-rich. description 2-3 sentences, persuasive + factual.
- 4-7 lowercase tags. category is a marketplace category.
- suggested_price is a believable retail price string.
- One listing object per input, ids must match the input ids. No prose outside JSON."""


def _listing_user(items: list[dict]) -> str:
    lines = ["Messy seller photos to turn into listings:"]
    for it in items:
        lines.append(f"- {it['id']}: {it['label']}")
    lines.append("\nWrite the listings + enhancement plans now.")
    return "\n".join(lines)


async def listing_copy_stage(items: list[dict]) -> tuple[list[dict], list]:
    """items: [{id, label}]. Returns (per-id listing dicts, stage records)."""
    raw, records = await chat_json(
        "smart", _LISTING_SYSTEM, _listing_user(items), stage="listing_copy", temperature=0.5
    )
    parsed = raw.get("listings", raw) if isinstance(raw, dict) else raw
    by_id = {str(p.get("id")): p for p in (parsed or []) if isinstance(p, dict)}
    out: list[dict] = []
    for it in items:
        p = by_id.get(it["id"], {})
        out.append({
            "id": it["id"],
            "title": str(p.get("title") or it["label"].title()),
            "description": str(p.get("description") or ""),
            "tags": [str(t) for t in (p.get("tags") or [])][:7],
            "category": str(p.get("category") or "General"),
            "suggested_price": str(p.get("suggested_price") or ""),
            "remove_background": bool(p.get("remove_background", True)),
            "relight_prompt": str(p.get("relight_prompt")
                                   or "soft neutral studio key from upper-left, gentle fill"),
            "upscale_factor": p.get("upscale_factor") if p.get("upscale_factor") in ("2x", "4x") else "2x",
            "rationale": str(p.get("rationale") or ""),
        })
    return out, records


# --------------------------------------------------------------------------
# Stage 2 (Magnific): clean each photo
# --------------------------------------------------------------------------
async def clean_item(
    item: ListingItem,
    source_path: Path,
    run_dir: Path,
    budget: MagnificBudget,
    sem: asyncio.Semaphore,
) -> None:
    """remove background -> relight -> upscale. Degrade gracefully on failure."""
    async with sem:
        cur = str(source_path)
        item.status = "cleaning"
        # background removal
        if item.remove_background:
            try:
                budget.charge(1)
                url, rec = await magnific.remove_background(cur)
                item.stages.append(rec)
                saved = await magnific.download(url, run_dir / f"{item.id}_nobg.png")
                cur = str(saved)
            except (MagnificError, BudgetExceeded, OSError) as e:
                _note(item, "remove_bg", e)
        # relight
        try:
            budget.charge(1)
            url, rec = await magnific.relight(cur, item.relight_prompt)
            item.stages.append(rec)
            saved = await magnific.download(url, run_dir / f"{item.id}_relit.jpg")
            cur = str(saved)
        except (MagnificError, BudgetExceeded, OSError) as e:
            _note(item, "relight", e)
        # upscale
        try:
            budget.charge(1)
            url, rec = await magnific.upscale(cur, item.upscale_factor, 0, item.title)
            item.stages.append(rec)
            saved = await magnific.download(url, run_dir / f"{item.id}_clean.jpg")
            item.clean_url = f"/static/listings/{run_dir.name}/{saved.name}"
            item.status = "done"
        except (MagnificError, BudgetExceeded, OSError) as e:
            _note(item, "upscale", e)
            item.status = "degraded"


def _note(item: ListingItem, stage: str, e: Exception) -> None:
    item.stages.append(
        StageRecord(stage=stage, model_or_engine="magnific", ok=False, note=str(e)[:200])
    )


# --------------------------------------------------------------------------
# Orchestration + demo cache
# --------------------------------------------------------------------------
async def run_listing_pipeline(
    state: ListingRun, sources: list[Path], labels: list[str], static_dir: Path
) -> None:
    try:
        state.status = "running"
        state.stage = "listing_copy"
        items_in = [{"id": f"p{i+1}", "label": lb} for i, lb in enumerate(labels)]
        copy, recs = await listing_copy_stage(items_in)
        state.stages.extend(recs)
        state.items = [ListingItem(**c) for c in copy]

        state.stage = "cleaning"
        run_dir = static_dir / "listings" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        budget = MagnificBudget(limit=int(os.getenv("MAX_MAGNIFIC_CALLS_PER_RUN", "9")) * 3)
        sem = asyncio.Semaphore(MAX_IN_FLIGHT)
        for it, src in zip(state.items, sources):
            it.source_url = f"/static/listings/{run_dir.name}/{src.name}"
        await asyncio.gather(
            *(clean_item(it, src, run_dir, budget, sem) for it, src in zip(state.items, sources))
        )
        degraded = any(it.status == "degraded" for it in state.items)
        state.status = "degraded" if degraded else "done"
        state.stage = "done"
    except (LLMError, Exception) as e:  # noqa: BLE001
        state.status = "error"
        state.error = str(e)
        state.stage = "error"


def load_demo() -> ListingRun | None:
    path = DEMO_DIR / "listings.json"
    if not path.exists():
        return None
    try:
        run = ListingRun(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    run.demo_mode = True
    return run
