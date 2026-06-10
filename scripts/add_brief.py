"""Run the live Akamai LLM pipeline for ONE brief and merge it into
scripts/_live_plans.json (without disturbing existing entries).

    py scripts/add_brief.py <key> "<brief text>"
    py scripts/add_brief.py perfume "A luxury eau de parfum in a faceted glass bottle."
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

OUT = ROOT / "scripts" / "_live_plans.json"


async def main() -> None:
    key, brief = sys.argv[1], sys.argv[2]
    print(f"=== {key}: {brief}", flush=True)
    stages = []
    concepts, recs = await concepts_stage(brief)
    stages.extend(recs)
    for c in concepts:
        print(f"  [{c.channel}] {c.id}: {c.headline}", flush=True)
    plans, recs = await param_plan_stage(brief, concepts)
    stages.extend(recs)
    by_id = {c.id: c for c in concepts}
    creatives = []
    for p in plans:
        c = by_id[p.concept_id]
        print(f"  -> {p.concept_id} [{c.channel}] {p.aspect_ratio} "
              f"cre={p.creativity:+d} up={p.upscale_factor}", flush=True)
        creatives.append({"concept": c.model_dump(), "plan": p.model_dump()})

    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    data[key] = {
        "run_id": f"demo_{key}",
        "brief": brief,
        "creatives": creatives,
        "llm_stages": [r.model_dump() for r in stages],
        "ledger": summarize(stages),
    }
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"merged '{key}' into {OUT}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
