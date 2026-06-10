"""Freepik API client (Magnific engines): Mystic text-to-image, Relight, Upscaler.

ALL endpoint paths and request field names are isolated in this file. They
changed after the April 2026 Magnific rebrand — verify against
https://docs.freepik.com at the venue and adjust the constants / payload
builders below; nothing else in the codebase should need to change.

Async pattern for every engine: POST submits a job -> {task_id}; GET polls
{task_id} until status is completed/failed; on success we download the image
bytes and persist them under static/runs/{run_id}/ so the UI can serve them.
"""
from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path
from typing import Any

import httpx

from .ledger import stage_timer
from .models import ASPECT_TO_FREEPIK, StageRecord

# Two interchangeable providers expose the same Magnific engines with identical
# paths + field names — only the base URL and auth header differ:
#   Route B (direct):  https://api.magnific.com   header x-magnific-api-key
#   Route A (Freepik): https://api.freepik.com    header x-freepik-api-key
# We auto-pick by whichever key is set (MAGNIFIC_API_KEY wins).

# --- Endpoint paths (verified against docs.magnific.com) -------------------
PATH_MYSTIC = "/v1/ai/mystic"
PATH_UPSCALER = "/v1/ai/image-upscaler"
PATH_RELIGHT = "/v1/ai/image-relight"
PATH_REMOVE_BG = "/v1/ai/beta/remove-background"

# Rough credit cost per engine call, for the ledger headline only.
CREDITS = {"mystic": 1, "relight": 2, "upscale": 3, "remove_bg": 1}

POLL_INTERVAL_S = 2.0
POLL_TIMEOUT_S = 120.0


class MagnificError(RuntimeError):
    pass


class BudgetExceeded(MagnificError):
    pass


class MagnificBudget:
    """Hard cap on billable Magnific calls per run (MAX_MAGNIFIC_CALLS_PER_RUN)."""

    def __init__(self, limit: int | None = None):
        if limit is None:
            limit = int(os.getenv("MAX_MAGNIFIC_CALLS_PER_RUN", "6"))
        self.limit = limit
        self.used = 0

    def charge(self, n: int = 1) -> None:
        if self.used + n > self.limit:
            raise BudgetExceeded(
                f"Magnific budget exhausted ({self.used}/{self.limit} calls used)"
            )
        self.used += n


def _provider() -> tuple[str, str, str]:
    """Return (base_url, auth_header_name, api_key) for the active provider."""
    mag = os.getenv("MAGNIFIC_API_KEY", "").strip()
    if mag:
        base = os.getenv("MAGNIFIC_BASE_URL", "https://api.magnific.com").rstrip("/")
        return base, "x-magnific-api-key", mag
    fp = os.getenv("FREEPIK_API_KEY", "").strip()
    if fp:
        base = os.getenv("FREEPIK_BASE_URL", "https://api.freepik.com").rstrip("/")
        return base, "x-freepik-api-key", fp
    raise MagnificError("Set MAGNIFIC_API_KEY (api.magnific.com) or FREEPIK_API_KEY (api.freepik.com).")


def _headers() -> dict[str, str]:
    _base, header_name, key = _provider()
    return {header_name: key, "Content-Type": "application/json"}


def _extract_task_id(body: dict) -> str:
    data = body.get("data", body)
    for k in ("task_id", "id", "taskId"):
        if isinstance(data, dict) and data.get(k):
            return str(data[k])
        if body.get(k):
            return str(body[k])
    raise MagnificError(f"could not find task id in response: {str(body)[:200]}")


def _extract_status(body: dict) -> str:
    data = body.get("data", body)
    status = (data.get("status") if isinstance(data, dict) else None) or body.get("status")
    return str(status or "").upper()


def _extract_image_url(body: dict) -> str | None:
    data = body.get("data", body)
    # Freepik returns generated[] of URLs, or generated[].url, or output urls.
    for container in (data, body):
        if not isinstance(container, dict):
            continue
        gen = container.get("generated") or container.get("output") or container.get("images")
        if isinstance(gen, list) and gen:
            first = gen[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return first.get("url") or first.get("image_url")
        if container.get("image_url"):
            return container["image_url"]
    return None


async def _submit_and_poll(path: str, payload: dict, *, timeout: float = POLL_TIMEOUT_S) -> str:
    """Submit a Freepik job and poll until it yields an image URL.

    Returns the image URL. Raises MagnificError on failure/timeout with a
    clear, surfaced message.
    """
    base, _h, _k = _provider()
    url = f"{base}{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=_headers(), json=payload)
        if resp.status_code >= 400:
            raise MagnificError(f"submit {path} -> HTTP {resp.status_code}: {resp.text[:300]}")
        body = resp.json()

        # Some endpoints may return the image synchronously.
        direct = _extract_image_url(body)
        if direct:
            return direct
        task_id = _extract_task_id(body)

        waited = 0.0
        interval = POLL_INTERVAL_S
        while waited < timeout:
            await asyncio.sleep(interval)
            waited += interval
            interval = min(interval * 1.3, 8.0)  # gentle backoff
            poll = await client.get(f"{url}/{task_id}", headers=_headers())
            if poll.status_code >= 400:
                raise MagnificError(
                    f"poll {path}/{task_id} -> HTTP {poll.status_code}: {poll.text[:200]}"
                )
            pbody = poll.json()
            status = _extract_status(pbody)
            if status in ("COMPLETED", "SUCCESS", "DONE", "FINISHED"):
                img = _extract_image_url(pbody)
                if not img:
                    raise MagnificError(f"completed but no image url: {str(pbody)[:200]}")
                return img
            if status in ("FAILED", "ERROR"):
                raise MagnificError(f"task failed: {str(pbody)[:200]}")
        raise MagnificError(f"timeout after {timeout:.0f}s polling {path}/{task_id}")


async def download(url: str, dest: Path) -> Path:
    """Download an image URL to dest, returning the path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    return dest


async def _to_image_field(image: str) -> str:
    """Relight/Upscaler accept a URL or base64. Pass URLs through; base64-encode
    local file paths."""
    if image.startswith(("http://", "https://")):
        return image
    p = Path(image)
    if p.exists():
        return base64.b64encode(p.read_bytes()).decode()
    return image  # assume already base64


# --- Public engine calls ---------------------------------------------------

async def mystic(prompt: str, aspect_ratio: str) -> tuple[str, StageRecord]:
    """Text-to-image draft. aspect_ratio is one of our AspectRatio literals."""
    payload = {
        "prompt": prompt,
        "aspect_ratio": ASPECT_TO_FREEPIK.get(aspect_ratio, "square_1_1"),
    }
    with stage_timer("draft", "magnific:mystic") as rec:
        rec.credits = CREDITS["mystic"]
        try:
            url = await _submit_and_poll(PATH_MYSTIC, payload)
        except MagnificError as e:
            rec.ok = False
            rec.note = str(e)
            raise
    return url, rec


async def relight(image: str, relight_prompt: str) -> tuple[str, StageRecord]:
    payload = {
        "image": await _to_image_field(image),
        "prompt": relight_prompt,
        "light_transfer_strength": 80,
    }
    with stage_timer("relight", "magnific:relight") as rec:
        rec.credits = CREDITS["relight"]
        try:
            url = await _submit_and_poll(PATH_RELIGHT, payload)
        except MagnificError as e:
            rec.ok = False
            rec.note = str(e)
            raise
    return url, rec


async def remove_background(image: str) -> tuple[str, StageRecord]:
    """Cut the subject out of its background -> transparent/clean PNG."""
    payload = {"image": await _to_image_field(image)}
    with stage_timer("remove_bg", "magnific:remove-bg") as rec:
        rec.credits = CREDITS["remove_bg"]
        try:
            url = await _submit_and_poll(PATH_REMOVE_BG, payload)
        except MagnificError as e:
            rec.ok = False
            rec.note = str(e)
            raise
    return url, rec


_FACTOR_MAP = {"2x": 2, "4x": 4, "8x": 8}


async def upscale(
    image: str, factor: str, creativity: int, prompt: str
) -> tuple[str, StageRecord]:
    payload = {
        "image": await _to_image_field(image),
        "scale_factor": _FACTOR_MAP.get(factor, 4),
        "optimized_for": "standard",
        "prompt": prompt,
        "creativity": creativity,
        "hdr": 0,
        "resemblance": 0,
        "engine": "magnific_sharpy",
    }
    with stage_timer("upscale", "magnific:upscaler") as rec:
        rec.credits = CREDITS["upscale"]
        rec.note = f"{factor}, creativity {creativity:+d}"
        try:
            url = await _submit_and_poll(PATH_UPSCALER, payload)
        except MagnificError as e:
            rec.ok = False
            rec.note = str(e)
            raise
    return url, rec
