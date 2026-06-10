"""Mocked-API unit tests: JSON parsing/repair, pydantic validation, ledger
math, and the pipeline state machine. No network calls."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend import llm, magnific, pipeline
from backend.ledger import llm_cost_usd, summarize
from backend.models import StageRecord, RunState


# --------------------------------------------------------------------------
# JSON extraction / repair
# --------------------------------------------------------------------------
def test_extract_json_plain():
    assert llm.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    assert llm.extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_with_prose():
    text = 'Sure! Here you go:\n{"plans": [{"x": 1}]} \nHope that helps.'
    assert llm.extract_json(text) == {"plans": [{"x": 1}]}


def test_extract_json_balanced_nested():
    text = 'noise [{"a":{"b":[1,2]}}] trailing'
    assert llm.extract_json(text) == [{"a": {"b": [1, 2]}}]


def test_extract_json_raises_on_garbage():
    with pytest.raises(json.JSONDecodeError):
        llm.extract_json("no json here at all")


async def test_chat_json_repairs_bad_json(monkeypatch):
    calls = []

    async def fake_chat(tier, system, user, *, stage, temperature=0.7, timeout=60.0, force_json=True):
        calls.append((tier, stage))
        if stage == "concepts":
            return "Here: {oops not json", StageRecord(stage=stage, model_or_engine=f"{tier}:m")
        return '{"fixed": true}', StageRecord(stage=stage, model_or_engine=f"{tier}:m")

    monkeypatch.setattr(llm, "chat", fake_chat)
    result, records = await llm.chat_json("smart", "sys", "usr", stage="concepts")
    assert result == {"fixed": True}
    assert len(records) == 2  # main call + repair call billed
    assert calls[1] == ("fast", "json_repair")  # repair always on fast tier


# --------------------------------------------------------------------------
# Pydantic validation in stages
# --------------------------------------------------------------------------
async def test_concepts_stage_drops_invalid_and_requires_three(monkeypatch):
    async def fake_chat_json(tier, system, user, *, stage, temperature=0.7, timeout=60.0):
        data = {
            "concepts": [
                {"id": "c1", "channel": "instagram_square", "headline": "A", "body": "B", "cta": "Buy", "visual_concept": "V"},
                {"id": "c2", "channel": "story_vertical", "headline": "A", "body": "B", "cta": "Buy", "visual_concept": "V"},
                {"id": "c3", "channel": "billboard_wide", "headline": "A", "body": "B", "cta": "Buy", "visual_concept": "V"},
                "not-a-dict",  # dropped
                {"headline": "no id no channel", "body": "b", "cta": "c", "visual_concept": "v"},  # coerced valid
            ]
        }
        return data, [StageRecord(stage=stage, model_or_engine=f"{tier}:m")]

    monkeypatch.setattr(pipeline, "chat_json", fake_chat_json)
    concepts, recs = await pipeline.concepts_stage("a product")
    assert len(concepts) >= 3
    assert all(c.channel in pipeline.CHANNELS for c in concepts)


async def test_concepts_stage_raises_when_too_few(monkeypatch):
    async def fake_chat_json(tier, system, user, *, stage, temperature=0.7, timeout=60.0):
        return {"concepts": [{"id": "c1", "channel": "instagram_square", "headline": "A", "body": "B", "cta": "C", "visual_concept": "V"}]}, []

    monkeypatch.setattr(pipeline, "chat_json", fake_chat_json)
    with pytest.raises(llm.LLMError):
        await pipeline.concepts_stage("a product")


async def test_param_plan_enforces_rules_and_falls_back(monkeypatch):
    from backend.models import Concept

    concepts = [
        Concept(id="c1", channel="billboard_wide", headline="H", body="B", cta="C", visual_concept="V"),
        Concept(id="c2", channel="instagram_square", headline="H", body="B", cta="C", visual_concept="V"),
        Concept(id="c3", channel="story_vertical", headline="H", body="B", cta="C", visual_concept="V"),
    ]

    async def fake_chat_json(tier, system, user, *, stage, temperature=0.7, timeout=60.0):
        # model returns wrong aspect + out-of-range creativity + bad factor
        return {"plans": [
            {"concept_id": "c1", "image_prompt": "p", "aspect_ratio": "square_1_1",
             "relight_prompt": "warm", "creativity": 99, "upscale_factor": "16x", "rationale": "r"},
        ]}, [StageRecord(stage=stage, model_or_engine=f"{tier}:m")]

    monkeypatch.setattr(pipeline, "chat_json", fake_chat_json)
    plans, recs = await pipeline.param_plan_stage("brief", concepts)
    p = plans[0]
    assert p.aspect_ratio == "wide_16_9"      # corrected to channel
    assert p.upscale_factor == "8x"           # billboard rule applied
    assert -10 <= p.creativity <= 10          # clamped


# --------------------------------------------------------------------------
# Ledger math
# --------------------------------------------------------------------------
def test_llm_cost(monkeypatch):
    monkeypatch.setenv("COST_FAST_PER_MTOK", "0.10")
    monkeypatch.setenv("COST_SMART_PER_MTOK", "2.00")
    assert llm_cost_usd("fast", 500_000, 500_000) == pytest.approx(0.10)
    assert llm_cost_usd("smart", 1_000_000, 0) == pytest.approx(2.00)


def test_summarize():
    stages = [
        StageRecord(stage="concepts", model_or_engine="fast:m", tokens_in=800, tokens_out=200, est_cost_usd=0.0001),
        StageRecord(stage="param_plan", model_or_engine="smart:m", tokens_in=100, tokens_out=100, est_cost_usd=0.001),
        StageRecord(stage="draft", model_or_engine="magnific:mystic", credits=1),
    ]
    s = summarize(stages)
    assert s["total_tokens"] == 1200
    assert s["smart_calls"] == 1
    assert s["fast_token_pct"] == pytest.approx(83.3, abs=0.2)
    assert s["total_credits"] == 1


# --------------------------------------------------------------------------
# Pipeline state machine (all external calls mocked)
# --------------------------------------------------------------------------
async def test_run_pipeline_happy_path(monkeypatch, tmp_path):
    async def fake_concepts(brief):
        from backend.models import Concept
        cs = [
            Concept(id="c1", channel="billboard_wide", headline="H", body="B", cta="C", visual_concept="V"),
            Concept(id="c2", channel="instagram_square", headline="H", body="B", cta="C", visual_concept="V"),
            Concept(id="c3", channel="story_vertical", headline="H", body="B", cta="C", visual_concept="V"),
        ]
        return cs, [StageRecord(stage="concepts", model_or_engine="fast:m", tokens_in=900, tokens_out=100)]

    async def fake_plans(brief, concepts):
        plans = [pipeline._fallback_plan(c) for c in concepts]
        return plans, [StageRecord(stage="param_plan", model_or_engine="smart:m", tokens_in=200, tokens_out=200)]

    async def fake_mystic(prompt, ar):
        return "http://img/draft", StageRecord(stage="draft", model_or_engine="magnific:mystic", credits=1)

    async def fake_relight(image, rp):
        return "http://img/relit", StageRecord(stage="relight", model_or_engine="magnific:relight", credits=2)

    async def fake_upscale(image, factor, creativity, prompt):
        return "http://img/final", StageRecord(stage="upscale", model_or_engine="magnific:upscaler", credits=3)

    async def fake_download(url, dest: Path):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"img")
        return dest

    monkeypatch.setattr(pipeline, "concepts_stage", fake_concepts)
    monkeypatch.setattr(pipeline, "param_plan_stage", fake_plans)
    monkeypatch.setattr(magnific, "mystic", fake_mystic)
    monkeypatch.setattr(magnific, "relight", fake_relight)
    monkeypatch.setattr(magnific, "upscale", fake_upscale)
    monkeypatch.setattr(magnific, "download", fake_download)

    state = RunState(run_id="t1", brief="a product")
    await pipeline.run_pipeline(state, tmp_path)

    assert state.status == "done"
    assert state.stage == "done"
    assert len(state.creatives) == 3
    assert all(c.status == "done" for c in state.creatives)
    assert all(c.final_url and c.draft_url and c.relit_url for c in state.creatives)


async def test_run_pipeline_degrades_on_magnific_failure(monkeypatch, tmp_path):
    from backend.models import Concept

    async def fake_concepts(brief):
        return [Concept(id="c1", channel="instagram_square", headline="H", body="B", cta="C", visual_concept="V")] * 1 + [
            Concept(id="c2", channel="story_vertical", headline="H", body="B", cta="C", visual_concept="V"),
            Concept(id="c3", channel="billboard_wide", headline="H", body="B", cta="C", visual_concept="V"),
        ], []

    async def fake_plans(brief, concepts):
        return [pipeline._fallback_plan(c) for c in concepts], []

    async def ok_mystic(prompt, ar):
        return "http://img/draft", StageRecord(stage="draft", model_or_engine="magnific:mystic", credits=1)

    async def boom_relight(image, rp):
        raise magnific.MagnificError("relight exploded")

    async def ok_upscale(image, factor, creativity, prompt):
        return "http://img/final", StageRecord(stage="upscale", model_or_engine="magnific:upscaler", credits=3)

    async def fake_download(url, dest: Path):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"img")
        return dest

    monkeypatch.setattr(pipeline, "concepts_stage", fake_concepts)
    monkeypatch.setattr(pipeline, "param_plan_stage", fake_plans)
    monkeypatch.setattr(magnific, "mystic", ok_mystic)
    monkeypatch.setattr(magnific, "relight", boom_relight)
    monkeypatch.setattr(magnific, "upscale", ok_upscale)
    monkeypatch.setattr(magnific, "download", fake_download)

    state = RunState(run_id="t2", brief="a product")
    await pipeline.run_pipeline(state, tmp_path)

    # Relight failed but upscale ran off the draft -> run completes, degraded.
    assert state.status == "degraded"
    assert all(c.draft_url for c in state.creatives)
    assert all(c.relit_url is None for c in state.creatives)


def test_magnific_budget_cap():
    b = magnific.MagnificBudget(limit=2)
    b.charge(1)
    b.charge(1)
    with pytest.raises(magnific.BudgetExceeded):
        b.charge(1)
