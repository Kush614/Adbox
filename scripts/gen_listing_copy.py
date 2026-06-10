"""Generate REAL Akamai LLM listing copy for the factory demo, when the tunnel
is up. Writes scripts/_listing_copy.json which build_listing_demo.py then uses.

    py scripts/gen_listing_copy.py
    py scripts/build_listing_demo.py   # picks up the real copy
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

from backend.listing_factory import listing_copy_stage  # noqa: E402

# Labels describe each messy seller photo (what the LLM 'sees').
LABELS = {
    "p1": "a pair of well-worn red canvas high-top sneakers on a gray wooden floor",
    "p2": "a modern round-face smartwatch with a blank screen on a plain surface",
    "p3": "a mustard-yellow leather shoulder handbag draped on a chair indoors",
}


async def main() -> None:
    items = [{"id": k, "label": v} for k, v in LABELS.items()]
    copy, recs = await listing_copy_stage(items)
    out = {c["id"]: c for c in copy}
    out["_stage"] = recs[0].model_dump() if recs else None
    (ROOT / "scripts" / "_listing_copy.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8")
    for c in copy:
        print(f"{c['id']}: {c['title']}  ({c['suggested_price']})")
    print("wrote scripts/_listing_copy.json — now run scripts/build_listing_demo.py")


if __name__ == "__main__":
    asyncio.run(main())
