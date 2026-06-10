"""OpenAI-compatible LLM client, tiered fast / smart.

Targets Akamai Inference Cloud at the venue (set AKAMAI_BASE_URL +
AKAMAI_API_KEY + MODEL_FAST/MODEL_SMART), but works against ANY
OpenAI-compatible endpoint (local ollama, etc.) so we can build before
credentials arrive.

`chat()` returns the raw assistant text + a StageRecord. `chat_json()`
parses strict JSON, stripping ```json fences, and on failure issues one
"repair this JSON" retry against the fast tier.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from .ledger import llm_cost_usd, stage_timer
from .models import StageRecord


class LLMError(RuntimeError):
    pass


def _base_url() -> str:
    url = os.getenv("AKAMAI_BASE_URL", "").strip().rstrip("/")
    if not url:
        raise LLMError(
            "AKAMAI_BASE_URL is not set. Point it at Akamai Inference Cloud or any "
            "OpenAI-compatible endpoint (e.g. http://localhost:11434 for ollama)."
        )
    return url


def _model_for(tier: str) -> str:
    if tier == "smart":
        model = os.getenv("MODEL_SMART", "").strip()
    else:
        model = os.getenv("MODEL_FAST", "").strip()
    if not model:
        raise LLMError(f"No model configured for tier '{tier}'. Set MODEL_FAST / MODEL_SMART.")
    return model


def _headers() -> dict[str, str]:
    key = os.getenv("AKAMAI_API_KEY", "").strip()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def extract_json(text: str) -> Any:
    """Best-effort JSON extraction from an LLM response.

    Strips reasoning-model <think>…</think> blocks, handles ```json fences and
    leading/trailing prose by grabbing the first balanced { } or [ ] block.
    Raises json.JSONDecodeError on failure.
    """
    text = _THINK_RE.sub("", text)
    # If a think block was left unclosed (truncated), drop everything before
    # the last </think> we can find, else before the first '{'/'['.
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1]
    text = text.strip()
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the first balanced object/array.
    start = min(
        (i for i in (text.find("{"), text.find("[")) if i != -1),
        default=-1,
    )
    if start == -1:
        raise json.JSONDecodeError("no JSON object found", text, 0)
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise json.JSONDecodeError("unbalanced JSON", text, start)


async def chat(
    tier: str,
    system: str,
    user: str,
    *,
    stage: str,
    temperature: float = 0.7,
    force_json: bool = True,
    max_tokens: int = 2048,
    timeout: float = 90.0,
) -> tuple[str, StageRecord]:
    """One chat completion. Returns (assistant_text, StageRecord)."""
    model = _model_for(tier)
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if force_json:
        payload["response_format"] = {"type": "json_object"}
    # Qwen3 (and other reasoning models) emit <think> blocks that waste tokens
    # and break JSON. Disable thinking via vLLM's chat_template_kwargs.
    if "qwen" in model.lower():
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    engine = f"{tier}:{model}"
    url = f"{_base_url()}/v1/chat/completions"
    headers = _headers()
    with stage_timer(stage, engine) as rec:
        async def _post() -> httpx.Response:
            async with httpx.AsyncClient(timeout=timeout) as client:
                return await client.post(url, headers=headers, json=payload)

        try:
            resp = await _post()
        except httpx.HTTPError as e:
            rec.ok = False
            rec.note = str(e)
            raise LLMError(f"LLM request failed: {e}") from e

        # Some OpenAI-compatible servers (e.g. older vLLM) reject
        # response_format with a 400. Drop it and retry once on plain prompting;
        # extract_json() still recovers the JSON downstream.
        if resp.status_code >= 400 and force_json and "response_format" in payload:
            payload.pop("response_format", None)
            try:
                resp = await _post()
            except httpx.HTTPError as e:
                rec.ok = False
                rec.note = str(e)
                raise LLMError(f"LLM request failed: {e}") from e

        if resp.status_code >= 400:
            rec.ok = False
            rec.note = f"HTTP {resp.status_code}: {resp.text[:200]}"
            raise LLMError(rec.note)

        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            rec.ok = False
            rec.note = f"malformed response: {str(data)[:200]}"
            raise LLMError(rec.note) from e

        usage = data.get("usage") or {}
        rec.tokens_in = int(usage.get("prompt_tokens", 0) or 0)
        rec.tokens_out = int(usage.get("completion_tokens", 0) or 0)
        rec.est_cost_usd = llm_cost_usd(tier, rec.tokens_in, rec.tokens_out)

    return content, rec


async def chat_json(
    tier: str,
    system: str,
    user: str,
    *,
    stage: str,
    temperature: float = 0.7,
    timeout: float = 60.0,
) -> tuple[Any, list[StageRecord]]:
    """Chat that must return JSON. On parse failure, one fast-tier repair call.

    Returns (parsed_json, [stage_records]). The records list always reflects
    every billable call made (the main call plus any repair call).
    """
    records: list[StageRecord] = []
    content, rec = await chat(
        tier, system, user, stage=stage, temperature=temperature, timeout=timeout
    )
    records.append(rec)
    try:
        return extract_json(content), records
    except json.JSONDecodeError:
        pass

    # Repair pass: cheapest tier, just fix the JSON.
    repair_system = (
        "You are a JSON repair tool. The user will paste malformed or fenced text "
        "that is supposed to be a single valid JSON value. Output ONLY the corrected, "
        "minified JSON value. No prose, no code fences."
    )
    fixed, repair_rec = await chat(
        "fast",
        repair_system,
        content,
        stage="json_repair",
        temperature=0.0,
        timeout=timeout,
    )
    records.append(repair_rec)
    return extract_json(fixed), records
