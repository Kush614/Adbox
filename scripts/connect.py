"""Connect + verify Akamai Inference Cloud and Freepik (Magnific) from the CLI.

    py scripts/connect.py            # check config + list Akamai models + ping Freepik
    py scripts/connect.py --smoke    # also run a tiny fast-tier LLM call (cheap)
    py scripts/connect.py --spend    # also submit a real 1-credit Mystic job (costs a credit)

Reads credentials from .env (or the real environment). Prints a clear PASS/FAIL
per service. Use the model ids it lists to fill MODEL_FAST / MODEL_SMART.
"""
from __future__ import annotations

import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

OK = "\033[92mPASS\033[0m"
BAD = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"


def mask(v: str | None) -> str:
    if not v:
        return "(unset)"
    return v[:5] + "…" + f"({len(v)} chars)" if len(v) > 6 else "set"


async def check_akamai(smoke: bool) -> bool:
    base = os.getenv("AKAMAI_BASE_URL", "").strip().rstrip("/")
    key = os.getenv("AKAMAI_API_KEY", "").strip()
    fast = os.getenv("MODEL_FAST", "").strip()
    smart = os.getenv("MODEL_SMART", "").strip()
    print("\n== Akamai AI Inference Cloud ==")
    print(f"  AKAMAI_BASE_URL = {base or '(unset)'}")
    print(f"  AKAMAI_API_KEY  = {mask(key)}")
    print(f"  MODEL_FAST      = {fast or '(unset)'}")
    print(f"  MODEL_SMART     = {smart or '(unset)'}")
    if not base:
        print(f"  {BAD} AKAMAI_BASE_URL is required.")
        return False

    headers = {"Authorization": f"Bearer {key}"} if key else {}
    ok = True
    # 1) list models (free) — also helps pick MODEL_FAST / MODEL_SMART
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{base}/v1/models", headers=headers)
        if r.status_code == 200:
            data = r.json()
            ids = [m.get("id") for m in data.get("data", data if isinstance(data, list) else [])]
            ids = [i for i in ids if i]
            print(f"  {OK} GET /v1/models -> {len(ids)} models")
            for i in ids[:20]:
                tag = ""
                if i == fast:
                    tag = "  <- MODEL_FAST"
                if i == smart:
                    tag = "  <- MODEL_SMART"
                print(f"        {i}{tag}")
            if fast and fast not in ids:
                print(f"  {WARN} MODEL_FAST '{fast}' not in the model list above.")
            if smart and smart not in ids:
                print(f"  {WARN} MODEL_SMART '{smart}' not in the model list above.")
        else:
            print(f"  {WARN} GET /v1/models -> HTTP {r.status_code}: {r.text[:150]}")
            print("        (endpoint may not expose /v1/models; will rely on the smoke test)")
    except httpx.HTTPError as e:
        print(f"  {BAD} could not reach {base}: {e}")
        ok = False

    # 2) optional smoke: tiny chat completion on the fast tier
    if smoke and ok:
        if not fast:
            print(f"  {WARN} --smoke skipped: MODEL_FAST unset.")
        else:
            try:
                async with httpx.AsyncClient(timeout=40) as c:
                    r = await c.post(
                        f"{base}/v1/chat/completions",
                        headers={**headers, "Content-Type": "application/json"},
                        json={
                            "model": fast,
                            "messages": [{"role": "user", "content": "Reply with the single word: pong"}],
                            "max_tokens": 5,
                            "temperature": 0,
                        },
                    )
                if r.status_code == 200:
                    msg = r.json()["choices"][0]["message"]["content"].strip()
                    print(f"  {OK} chat smoke ({fast}) -> {msg!r}")
                else:
                    print(f"  {BAD} chat smoke -> HTTP {r.status_code}: {r.text[:200]}")
                    ok = False
            except (httpx.HTTPError, KeyError, IndexError) as e:
                print(f"  {BAD} chat smoke failed: {e}")
                ok = False
    return ok


async def check_freepik(spend: bool) -> bool:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from backend import magnific  # noqa: E402

    print("\n== Magnific ==")
    try:
        base, header_name, key = magnific._provider()
    except magnific.MagnificError as e:
        print(f"  {BAD} {e}")
        return False
    print(f"  provider header = {header_name}")
    print(f"  base            = {base}")
    print(f"  key             = {mask(key)}")

    headers = {header_name: key}
    ok = True
    # Cheap auth probe: an unknown task id should 404 (key accepted) rather than 401/403 (key rejected).
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{base}{magnific.PATH_MYSTIC}/connectivity-probe", headers=headers)
        if r.status_code in (401, 403):
            print(f"  {BAD} key rejected -> HTTP {r.status_code}: {r.text[:150]}")
            ok = False
        else:
            print(f"  {OK} key authenticates (probe -> HTTP {r.status_code}, not 401/403)")
    except httpx.HTTPError as e:
        print(f"  {WARN} could not reach {base}: {e}")

    if spend and ok:
        # Submit a real 1-credit Mystic job and poll once or twice.
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from backend import magnific  # noqa: E402

        try:
            print("  submitting a 1-credit Mystic test job…")
            url, rec = await magnific.mystic("a red apple on a white table, product photo", "square_1_1")
            print(f"  {OK} Mystic returned an image in {rec.latency_ms} ms: {url[:80]}…")
        except Exception as e:  # noqa: BLE001
            print(f"  {BAD} Mystic test failed: {e}")
            print("        -> check PATH_MYSTIC + payload fields in backend/magnific.py against docs.freepik.com")
            ok = False
    elif not spend:
        print(f"  {WARN} skipped the real image test (costs 1 credit). Re-run with --spend to confirm Magnific.")
    return ok


async def main() -> int:
    smoke = "--smoke" in sys.argv
    spend = "--spend" in sys.argv
    a = await check_akamai(smoke)
    f = await check_freepik(spend)
    print("\n== summary ==")
    print(f"  Akamai : {OK if a else BAD}")
    print(f"  Freepik: {OK if f else BAD}")
    if a and f:
        print("\n  Ready. Set DEMO_MODE=0 in .env and run:")
        print('    py -m uvicorn backend.main:app --reload --port 8000')
        return 0
    print("\n  Fix the FAIL items above (fill .env), then re-run this script.")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
