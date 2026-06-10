"""Pydantic data contracts for the Ad-in-a-Box pipeline.

These schemas are the single source of truth shared by the LLM stages,
the Magnific stages, the FastAPI layer, and the frontend (via RunState JSON).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Channel = Literal["instagram_square", "story_vertical", "billboard_wide"]
AspectRatio = Literal["square_1_1", "story_9_16", "wide_16_9"]
UpscaleFactor = Literal["2x", "4x", "8x"]

# Map a channel to its native aspect ratio so the smart tier (and our
# fallbacks) stay internally consistent.
CHANNEL_ASPECT: dict[str, AspectRatio] = {
    "instagram_square": "square_1_1",
    "story_vertical": "story_9_16",
    "billboard_wide": "wide_16_9",
}

# Freepik / Mystic expects its own aspect-ratio vocabulary.
ASPECT_TO_FREEPIK: dict[str, str] = {
    "square_1_1": "square_1_1",
    "story_9_16": "social_story_9_16",
    "wide_16_9": "widescreen_16_9",
}


class Concept(BaseModel):
    id: str
    channel: Channel
    headline: str = Field(description="<= 8 words")
    body: str = Field(description="<= 30 words")
    cta: str = Field(description="<= 4 words")
    visual_concept: str = Field(description="1-2 sentences describing the image")


class ParamPlan(BaseModel):
    concept_id: str
    image_prompt: str
    aspect_ratio: AspectRatio
    relight_prompt: str
    creativity: int = Field(ge=-10, le=10)
    upscale_factor: UpscaleFactor
    rationale: str = Field(description="1 sentence: why these params for this product/channel")


class StageRecord(BaseModel):
    stage: str
    model_or_engine: str
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    est_cost_usd: float = 0.0
    credits: int = 0  # Magnific credits for image stages
    ok: bool = True
    note: str = ""


class Creative(BaseModel):
    concept: Concept
    plan: ParamPlan
    draft_url: str | None = None
    relit_url: str | None = None
    final_url: str | None = None
    video_url: str | None = None  # optional animated ad (Magnific video, hero only)
    status: Literal["pending", "drafting", "relighting", "upscaling", "done", "degraded"] = "pending"
    stages: list[StageRecord] = Field(default_factory=list)


class ListingItem(BaseModel):
    """One product photo run through the E-commerce Listing Factory."""

    id: str
    source_url: str | None = None  # original messy seller photo (served path)
    clean_url: str | None = None  # storefront-ready result
    title: str = ""  # SEO title (LLM)
    description: str = ""  # SEO description (LLM)
    tags: list[str] = Field(default_factory=list)
    category: str = ""
    suggested_price: str = ""
    # The LLM's per-image enhancement decision (drives Magnific):
    remove_background: bool = True
    relight_prompt: str = ""
    upscale_factor: UpscaleFactor = "2x"
    rationale: str = ""
    status: Literal["pending", "analyzing", "cleaning", "done", "degraded"] = "pending"
    stages: list[StageRecord] = Field(default_factory=list)


class ListingRun(BaseModel):
    run_id: str
    status: Literal["pending", "running", "done", "degraded", "error"] = "pending"
    stage: str = "queued"
    items: list[ListingItem] = Field(default_factory=list)
    stages: list[StageRecord] = Field(default_factory=list)  # LLM-level stages
    error: str | None = None
    demo_mode: bool = False


class RunState(BaseModel):
    run_id: str
    brief: str
    status: Literal["pending", "running", "done", "degraded", "error"] = "pending"
    stage: str = "queued"
    concepts: list[Concept] = Field(default_factory=list)
    creatives: list[Creative] = Field(default_factory=list)
    stages: list[StageRecord] = Field(default_factory=list)  # LLM-level stages
    error: str | None = None
    demo_mode: bool = False
