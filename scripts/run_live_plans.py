"""Run the LIVE Akamai LLM pipeline (concepts + param_plan) for the two demo
briefs and dump the chosen ParamPlans (+ their concepts) to scripts/_live_plans.json.

This is the LLM half of the pipeline only; the Magnific image stages are driven
separately via the authenticated Magnific MCP so we capture REAL output.

    py scripts/run_live_plans.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from backend.ledger import summarize  # noqa: E402
from backend.pipeline import concepts_stage, param_plan_stage  # noqa: E402

BRIEFS = {
    "coffee": "A specialty single-origin coffee bag, hand-roasted in small batches.",
    "shoe": "A lightweight trail running shoe with grippy all-terrain soles.",
}


async def run_one(name: str, brief: str) -> dict:
    print(f"\n===== {name}: {brief}", flush=True)
    stages = []
    concepts, recs = await concepts_stage(brief)
    stages.extend(recs)
    print(f"  concepts: {len(concepts)}", flush=True)
    for c in concepts:
        print(f"    [{c.channel}] {c.id}: {c.headline}", flush=True)

    plans, recs = await param_plan_stage(brief, concepts)
    stages.extend(recs)
    print(f"  plans chosen: {len(plans)}", flush=True)
    by_id = {c.id: c for c in concepts}
    out_creatives = []
    for p in plans:
        c = by_id[p.concept_id]
        print(f"    -> {p.concept_id} [{c.channel}] {p.aspect_ratio} "
              f"creativity={p.creativity:+d} upscale={p.upscale_factor}", flush=True)
        out_creatives.append({"concept": c.model_dump(), "plan": p.model_dump()})

    return {
        "run_id": f"demo_{name}",
        "brief": brief,
        "creatives": out_creatives,
        "llm_stages": [r.model_dump() for r in stages],
        "ledger": summarize(stages),
    }


async def main() -> None:
    result = {}
    for name, brief in BRIEFS.items():
        result[name] = await run_one(name, brief)
    out = ROOT / "scripts" / "_live_plans.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwrote {out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
