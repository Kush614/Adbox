"""Pipeline state machine: concepts -> param plans -> per-creative image stages.

Stage functions mutate the shared RunState in place so the FastAPI layer can
stream progress to the UI by simply re-serializing the state on each poll.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

from pydantic import ValidationError

from . import magnific
from .llm import LLMError, chat_json
from .magnific import BudgetExceeded, MagnificBudget, MagnificError
from .models import (
    CHANNEL_ASPECT,
    Concept,
    Creative,
    ParamPlan,
    RunState,
)

CHANNELS = ["instagram_square", "story_vertical", "billboard_wide"]
MAX_IN_FLIGHT = 3

# Live runs cap upscale to keep credit burn + latency sane during judging;
# the 8x money-shot is reserved for DEMO_MODE cached runs (see risks table).
LIVE_MAX_UPSCALE = os.getenv("LIVE_MAX_UPSCALE", "4x")
_FACTOR_ORDER = {"2x": 2, "4x": 4, "8x": 8}


# --------------------------------------------------------------------------
# Stage 1 (fast tier): concepts
# --------------------------------------------------------------------------
_CONCEPTS_SYSTEM = """You are a senior advertising creative director.
Given a product brief, invent punchy, channel-aware ad concepts.

Return STRICT JSON only, shape:
{"concepts": [
  {"id": "c1", "channel": "instagram_square", "headline": "...", "body": "...",
   "cta": "...", "visual_concept": "..."}
]}

Rules:
- Exactly 6 concepts: 2 for each channel of
  ["instagram_square", "story_vertical", "billboard_wide"].
- headline <= 8 words. body <= 30 words. cta <= 4 words.
- visual_concept: 1-2 vivid sentences describing the image we should generate.
- ids must be unique (c1..c6). No prose outside the JSON."""


def _concepts_user(brief: str) -> str:
    return f"Product brief:\n{brief}\n\nGenerate the 6 concepts now."


async def concepts_stage(brief: str) -> tuple[list[Concept], list]:
    raw, records = await chat_json(
        "fast", _CONCEPTS_SYSTEM, _concepts_user(brief), stage="concepts", temperature=0.9
    )
    items = raw.get("concepts", raw) if isinstance(raw, dict) else raw
    concepts: list[Concept] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(items or []):
        if not isinstance(item, dict):
            continue
        item.setdefault("id", f"c{i + 1}")
        if item["id"] in seen_ids:
            item["id"] = f"{item['id']}_{i}"
        # Coerce an unknown channel into a valid one round-robin.
        if item.get("channel") not in CHANNELS:
            item["channel"] = CHANNELS[i % len(CHANNELS)]
        try:
            concepts.append(Concept(**item))
            seen_ids.add(item["id"])
        except ValidationError:
            continue
    if len(concepts) < 3:
        raise LLMError(f"concepts stage produced only {len(concepts)} valid concepts (<3)")
    return concepts, records


# --------------------------------------------------------------------------
# Stage 2 (smart tier): Magnific parameter plans
# --------------------------------------------------------------------------
_PLAN_SYSTEM = """You are an expert art director who controls the Magnific
image engines (by Freepik). You pick the 3 strongest ad concepts and write a
precise generation + enhancement plan for each.

You understand Magnific's controls:
- image_prompt: a detailed text-to-image prompt for Mystic. Include subject,
  composition, lens/style, mood, and lighting intent. Be concrete.
- relight_prompt: phrase lighting as direction + quality + color temperature,
  e.g. "warm golden-hour key light from camera left, soft wraparound shadows,
  amber rim light". This drives the Relight engine.
- creativity: integer -10..10. NEGATIVE = stay faithful to the draft (good for
  product accuracy, packaging, text). POSITIVE = let Magnific reinvent detail
  and texture (good for dramatic, painterly, hero shots). Choose deliberately.
- upscale_factor: "2x" | "4x" | "8x". RULE: billboard_wide -> "8x" (needs print
  resolution), story_vertical -> "4x", instagram_square -> "4x".
- aspect_ratio must match the channel: instagram_square->square_1_1,
  story_vertical->story_9_16, billboard_wide->wide_16_9.
- rationale: ONE sentence explaining why these exact params suit this product
  and channel. This is shown to judges, so make it sharp and specific.

Return STRICT JSON only, shape:
{"plans": [
  {"concept_id": "c1", "image_prompt": "...", "aspect_ratio": "wide_16_9",
   "relight_prompt": "...", "creativity": 4, "upscale_factor": "8x",
   "rationale": "..."}
]}
Pick 3 concepts that maximize channel variety. No prose outside the JSON."""


def _plan_user(brief: str, concepts: list[Concept]) -> str:
    lines = [f"Product brief:\n{brief}\n", "Concepts to choose from:"]
    for c in concepts:
        lines.append(
            f"- {c.id} [{c.channel}] headline={c.headline!r} "
            f"visual={c.visual_concept!r}"
        )
    lines.append("\nPick the best 3 and emit their Magnific plans now.")
    return "\n".join(lines)


async def param_plan_stage(
    brief: str, concepts: list[Concept]
) -> tuple[list[ParamPlan], list]:
    raw, records = await chat_json(
        "smart", _PLAN_SYSTEM, _plan_user(brief, concepts), stage="param_plan", temperature=0.4
    )
    items = raw.get("plans", raw) if isinstance(raw, dict) else raw
    by_id = {c.id: c for c in concepts}
    plans: list[ParamPlan] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        cid = item.get("concept_id")
        concept = by_id.get(cid)
        if concept is None:
            continue
        # Enforce channel/aspect + upscale rules regardless of model drift.
        item["aspect_ratio"] = CHANNEL_ASPECT[concept.channel]
        if "upscale_factor" not in item or item["upscale_factor"] not in _FACTOR_ORDER:
            item["upscale_factor"] = "8x" if concept.channel == "billboard_wide" else "4x"
        try:
            item["creativity"] = int(item.get("creativity", 0))
        except (TypeError, ValueError):
            item["creativity"] = 0
        item["creativity"] = max(-10, min(10, item["creativity"]))
        try:
            plans.append(ParamPlan(**item))
        except ValidationError:
            continue
    # Guarantee at least one plan by falling back to the first concepts.
    if not plans:
        for concept in concepts[:3]:
            plans.append(_fallback_plan(concept))
    return plans[:3], records


def _fallback_plan(concept: Concept) -> ParamPlan:
    return ParamPlan(
        concept_id=concept.id,
        image_prompt=f"{concept.visual_concept} High-end commercial product photography, studio quality.",
        aspect_ratio=CHANNEL_ASPECT[concept.channel],
        relight_prompt="soft warm key light from camera left, gentle shadows, clean highlights",
        creativity=2,
        upscale_factor="8x" if concept.channel == "billboard_wide" else "4x",
        rationale=f"Balanced defaults for a {concept.channel} placement.",
    )


# --------------------------------------------------------------------------
# Image stages (Magnific), per creative, concurrent
# --------------------------------------------------------------------------
def _clamp_live_factor(factor: str) -> str:
    if _FACTOR_ORDER.get(factor, 4) > _FACTOR_ORDER.get(LIVE_MAX_UPSCALE, 4):
        return LIVE_MAX_UPSCALE
    return factor


async def process_creative(
    creative: Creative,
    run_dir: Path,
    budget: MagnificBudget,
    sem: asyncio.Semaphore,
) -> None:
    """mystic -> relight -> upscale. Any image-stage failure degrades this
    creative (keep the best image we have) but never aborts the run."""
    async with sem:
        plan = creative.plan
        cid = creative.concept.id

        # --- draft (Mystic) ---
        # Drafts are low-res and cheap; the MAX_MAGNIFIC_CALLS budget guards the
        # expensive relight + upscale stages only (3 + 3 = 6), per spec.
        creative.status = "drafting"
        try:
            url, rec = await magnific.mystic(plan.image_prompt, plan.aspect_ratio)
            creative.stages.append(rec)
            saved = await magnific.download(url, run_dir / f"{cid}_draft.jpg")
            creative.draft_url = f"/static/runs/{run_dir.name}/{saved.name}"
        except (MagnificError, BudgetExceeded, OSError) as e:
            creative.status = "degraded"
            _note_failure(creative, "draft", e)
            return  # no draft -> nothing downstream can run

        # --- relight ---
        creative.status = "relighting"
        relit_local = run_dir / f"{cid}_relit.jpg"
        try:
            budget.charge(1)
            url, rec = await magnific.relight(str(saved), plan.relight_prompt)
            creative.stages.append(rec)
            saved_relit = await magnific.download(url, relit_local)
            creative.relit_url = f"/static/runs/{run_dir.name}/{saved_relit.name}"
            upscale_src = str(saved_relit)
        except (MagnificError, BudgetExceeded, OSError) as e:
            _note_failure(creative, "relight", e)
            upscale_src = str(saved)  # fall back to draft for upscale

        # --- upscale (final) ---
        creative.status = "upscaling"
        factor = _clamp_live_factor(plan.upscale_factor)
        try:
            budget.charge(1)
            url, rec = await magnific.upscale(
                upscale_src, factor, plan.creativity, plan.image_prompt
            )
            creative.stages.append(rec)
            saved_final = await magnific.download(url, run_dir / f"{cid}_final.jpg")
            creative.final_url = f"/static/runs/{run_dir.name}/{saved_final.name}"
            creative.status = "done" if creative.relit_url else "degraded"
        except (MagnificError, BudgetExceeded, OSError) as e:
            _note_failure(creative, "upscale", e)
            creative.status = "degraded"


def _note_failure(creative: Creative, stage: str, e: Exception) -> None:
    from .models import StageRecord

    creative.stages.append(
        StageRecord(stage=stage, model_or_engine="magnific", ok=False, note=str(e)[:200])
    )


# --------------------------------------------------------------------------
# Top-level orchestration
# --------------------------------------------------------------------------
async def run_pipeline(state: RunState, static_dir: Path) -> None:
    try:
        state.status = "running"

        state.stage = "concepts"
        concepts, recs = await concepts_stage(state.brief)
        state.stages.extend(recs)
        state.concepts = concepts

        state.stage = "param_plan"
        plans, recs = await param_plan_stage(state.brief, concepts)
        state.stages.extend(recs)

        by_id = {c.id: c for c in concepts}
        state.creatives = [
            Creative(concept=by_id[p.concept_id], plan=p)
            for p in plans
            if p.concept_id in by_id
        ]

        state.stage = "images"
        run_dir = static_dir / "runs" / state.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        budget = MagnificBudget()
        sem = asyncio.Semaphore(MAX_IN_FLIGHT)
        await asyncio.gather(
            *(process_creative(c, run_dir, budget, sem) for c in state.creatives)
        )

        degraded = any(c.status == "degraded" for c in state.creatives)
        state.status = "degraded" if degraded else "done"
        state.stage = "done"
    except (LLMError, Exception) as e:  # noqa: BLE001 - surface any pipeline failure
        state.status = "error"
        state.error = str(e)
        state.stage = "error"


# --------------------------------------------------------------------------
# CLI checkpoint:  py -m backend.pipeline "solar-powered camping lantern"
# --------------------------------------------------------------------------
async def _cli(brief: str) -> None:
    import json as _json

    from .ledger import summarize

    state = RunState(run_id=uuid.uuid4().hex[:8], brief=brief)
    concepts, recs = await concepts_stage(brief)
    state.stages.extend(recs)
    print(f"\n=== {len(concepts)} concepts (fast tier) ===")
    for c in concepts:
        print(f"  [{c.channel}] {c.id}: {c.headline}  | cta: {c.cta}")

    plans, recs = await param_plan_stage(brief, concepts)
    state.stages.extend(recs)
    print(f"\n=== {len(plans)} Magnific plans (smart tier) ===")
    for p in plans:
        print(_json.dumps(p.model_dump(), indent=2))

    print("\n=== ledger ===")
    print(_json.dumps(summarize(state.stages), indent=2))


if __name__ == "__main__":
    import sys

    from dotenv import load_dotenv

    load_dotenv()
    brief_arg = sys.argv[1] if len(sys.argv) > 1 else "a solar-powered camping lantern that charges your phone"
    asyncio.run(_cli(brief_arg))
