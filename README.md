# 📦 Ad-in-a-Box — one sentence in, a full ad campaign out

**Akamai Inference Cloud decides. Magnific renders.**

Built for the **AI Inference Hack Day @ AWS Builder Loft SF** — targeting the Akamai 1st-place prize and Best Use of Magnific.

Type one sentence describing a product. A two-tier LLM pipeline on **Akamai Inference Cloud** writes the campaign and — this is the core idea — **decides every Magnific enhancement parameter** (image prompt, light direction, creativity dial, upscale factor) per channel. **Magnific** then executes: text-to-image → relight → upscale → even a 5-second hero **ad video** with sound. A second feature, the **E-commerce Listing Factory**, turns messy seller photos into storefront-ready listings with LLM-written SEO copy.

> **The novelty:** the LLM is the *art director*, not the artist. It emits structured, per-channel enhancement parameters **with a one-sentence rationale for each choice**, and a live inference ledger proves the economics of every decision.

---

## 🎬 See it working

### Ad Studio — one brief → 3 channel-ready creatives (+ video)
![Ad Studio: full run for a luxury perfume — ledger + Instagram/Story/Billboard creatives](docs/screenshots/ad-studio.png)

### Real Magnific hero ad videos (image → video, with sound)
| Coffee | Trail shoe | Perfume |
|---|---|---|
| ![Coffee hero ad video](docs/screenshots/coffee-video.gif) | ![Shoe hero ad video](docs/screenshots/shoe-video.gif) | ![Perfume hero ad video](docs/screenshots/perfume-video.gif) |

*Full-quality MP4s with audio are committed in the repo: [`coffee`](backend/static/runs/demo_coffee/c6_video.mp4) · [`shoe`](backend/static/runs/demo_shoe/c6_video.mp4) · [`perfume`](backend/static/runs/demo_perfume/c6_video.mp4)*

### The Magnific before/after (draft → LLM-directed relight + upscale)
![Perfume billboard: Mystic draft vs relit+upscaled final](docs/screenshots/perfume-before-after.jpg)
![Coffee billboard: Mystic draft vs relit+upscaled final](docs/screenshots/coffee-before-after.jpg)

### E-commerce Listing Factory — messy seller photo → storefront listing
![Listing Factory: 3 messy photos cleaned + SEO copy + prices + tags](docs/screenshots/listing-factory.png)
![Sneaker: messy floor photo vs storefront-ready shot](docs/screenshots/listing-before-after.jpg)

---

## 🧠 How we use Akamai Inference Cloud

Two right-sized models, **tiered by cost**, on an OpenAI-compatible endpoint:

| Tier | Model | Runs | Job | Why this tier |
|---|---|---|---|---|
| **fast** | `Qwen/Qwen3-8B-FP8` | per run | Writes **6 ad concepts** (headline, body, CTA, visual concept) — the token-heavy creative drafting | Cheap tokens for bulk work |
| **smart** | `Qwen/Qwen3-14B-FP8` | **exactly once** | Picks the best 3 concepts and emits a **structured Magnific parameter plan** per creative | One expensive, high-judgment call |

The smart tier's output is a strict-JSON `ParamPlan` — the contract between the LLM and Magnific:

```json
{
  "concept_id": "c6",
  "image_prompt": "Wide cinematic shot of a luxury faceted crystal perfume bottle…",
  "aspect_ratio": "wide_16_9",
  "relight_prompt": "dramatic warm spotlight from above, deep shadows, amber glow through the glass",
  "creativity": 5,
  "upscale_factor": "8x",
  "rationale": "A billboard hero earns 8x print detail, and +5 creativity lets Magnific invent the silk-and-mist drama around the rigidly accurate bottle."
}
```

**The live inference ledger** (visible in the UI on every run) proves the economics:

> Fast tier handled **38.9%** of tokens · smart tier ran **1×** · total LLM cost **$0.0013** · 38 Magnific credits

Every stage is itemized: model, latency, tokens, credits, estimated cost. A whole campaign's LLM bill is **about a tenth of a cent**.

**Engineering details that make this production-ish, not demo-ware:**
- OpenAI-compatible client ([`backend/llm.py`](backend/llm.py)) works against Akamai Inference Cloud or any compatible endpoint; strict-JSON extraction with reasoning-model `<think>` stripping and a one-shot cheap-tier **JSON repair pass** on parse failure
- When the venue gateway died mid-hackathon, we **self-provisioned a replacement inference box on Akamai Connected Cloud** via the API — the pipeline is endpoint-portable by design

## 🎨 How we use Magnific

Five engines, all driven by LLM-chosen parameters:

| Engine | Used for | The LLM decides |
|---|---|---|
| **Mystic (text-to-image)** | Draft creative per channel | The full image prompt + aspect ratio |
| **Relight** | Channel-specific mood lighting | Light **direction, quality, color temperature** ("warm golden-hour key from camera left, amber rim light") |
| **Upscaler** | Final 4x–8x print/feed-ready asset | **Creativity** (−10…+10: negative = product accuracy, positive = reinvented detail) + **factor** per channel (billboard→8x, story/square→4x) |
| **Background removal** | Listing Factory cleanup | Whether to cut the product out of its messy scene |
| **Video (Seedance Pro 2.0)** | 5s 1080p hero **ad videos** with sound effects | — (seeded from the relit hero frame + camera push-in) |

Pipeline per creative: `generate → relight → upscale` (+ `video` for the billboard hero).
Pipeline per listing: `remove background → studio relight → upscale` + SEO title/description/tags/category/price.

## 🏗 Architecture

```mermaid
flowchart LR
    A["Brief<br/>(one sentence)"] --> B["fast tier<br/>Qwen3-8B on Akamai<br/>6 concepts"]
    B --> C["smart tier<br/>Qwen3-14B on Akamai<br/>runs ONCE: picks 3 +<br/>writes Magnific params"]
    C --> D["Magnific Mystic<br/>text-to-image draft"]
    D --> E["Magnific Relight<br/>LLM-chosen lighting"]
    E --> F["Magnific Upscaler<br/>LLM-chosen creativity/factor"]
    E --> G["Magnific Video<br/>5s hero ad w/ sound"]
    F --> H["UI: before/after slider,<br/>clickable CTAs, ledger"]
    G --> H

    I["Messy seller photos"] --> J["smart tier: SEO copy +<br/>per-image enhancement plan"]
    J --> K["Magnific: bg removal →<br/>relight → upscale"]
    K --> L["Storefront listings<br/>(copy-paste ready)"]
```

- **Backend:** FastAPI + httpx, async pipeline with per-creative concurrency (semaphore-bounded), in-memory run store, polling API (`POST /run`, `GET /run/{id}`, `POST /listings`, `GET /listings/{id}`)
- **Frontend:** single static HTML file, zero build step — dark neo-brutalist UI with before/after sliders, video player, landing-page modals, live progress steps, and the inference ledger
- **Data contracts:** Pydantic models ([`backend/models.py`](backend/models.py)) shared by the LLM stages, Magnific stages, API, and UI

## 🛡 Cost & failure engineering (built in, not bolted on)

- **`MAX_MAGNIFIC_CALLS_PER_RUN`** — hard budget cap on billable Magnific calls per run
- **`LIVE_MAX_UPSCALE=4x`** — live runs clamp the 8x money-shot to 4x to control credit burn; 8x lives in the cached demo
- **Graceful degradation** — any image-stage failure degrades that one creative (keeps the best image it has) and never aborts the run; the UI shows a ⚠ degraded note
- **`DEMO_MODE=1`** — replays pre-baked runs of **real captured Magnific output** instantly and fully offline (venue-Wi-Fi insurance). The Wi-Fi did die mid-hackathon; the demo didn't.
- **JSON repair pass** — malformed LLM JSON gets one cheap-tier repair call instead of failing the run

## ✅ What's real (transparency for judges)

- **All 9 campaign images and all 3 ad videos are real Magnific API output** — generate → relight → upscale chains, no mockups. The 4x/8x originals run up to 10,880px; web-sized copies are committed for a snappy UI.
- **All 3 Listing Factory transformations are real Magnific output** (background removal → relight → upscale) on real stock "messy" photos.
- **Coffee & shoe campaign concepts/params came verbatim from live Akamai Qwen3 runs** — captured with real token counts, latencies, and costs in [`scripts/_live_plans.json`](scripts/_live_plans.json). The perfume campaign and listing SEO were authored to the same pipeline contracts while the venue gateway was down mid-build (see resilience note above); their ledger figures mirror the captured real-run magnitudes.
- The ledger math, budget caps, and degradation paths are live code — see [`backend/ledger.py`](backend/ledger.py), [`backend/magnific.py`](backend/magnific.py), [`backend/pipeline.py`](backend/pipeline.py).

## 🚀 Run it (offline, 60 seconds)

```bash
git clone https://github.com/Kush614/Adbox && cd Adbox
python -m venv .venv && .venv/Scripts/activate    # Windows; use .venv/bin/activate on mac/linux
pip install -r requirements.txt
copy .env.example .env                             # DEMO_MODE=1 works with zero credentials
python -m uvicorn backend.main:app --port 8000
```

Open **http://127.0.0.1:8000** → click a product chip (it auto-runs) → drag the before/after slider → hit **▶ Ad video** → switch to the **Listing Factory** tab → **Run factory**.

**Live mode:** fill `AKAMAI_BASE_URL`/`AKAMAI_API_KEY` (any OpenAI-compatible endpoint works) + a Magnific/Freepik API key in `.env`, set `DEMO_MODE=0`. Verify connectivity with `python scripts/connect.py --smoke`.

## 📁 Repo map

```
backend/
  pipeline.py          # concepts → param plan → per-creative image stages (the ad pipeline)
  listing_factory.py   # SEO copy + per-image enhancement decisions → cleanup pipeline
  llm.py               # tiered OpenAI-compatible client, strict-JSON + repair pass
  magnific.py          # Magnific engines client (Mystic/Relight/Upscaler/RemoveBG) + budget
  ledger.py            # per-stage cost/latency tracking → the UI ledger
  models.py            # Pydantic contracts shared by LLM ⇄ Magnific ⇄ API ⇄ UI
  main.py              # FastAPI app + DEMO_MODE replay
  demo/                # pre-baked runs (real Magnific output) for offline replay
  static/runs/         # committed real campaign assets (images + hero videos)
  static/listings/     # committed real listing before/after assets
frontend/index.html    # the whole UI — one file, no build step
scripts/
  run_live_plans.py    # capture real Akamai LLM runs into _live_plans.json
  build_real_demos.py  # wire real Magnific assets into the demo cache
  build_listing_demo.py# same for the Listing Factory
  connect.py           # PASS/FAIL connectivity checker for Akamai + Magnific
  DEMO_SCRIPT.md       # the 3-minute demo script
tests/                 # pipeline unit tests (pytest)
```

## 🏆 Why this should win

1. **A real insight, not a wrapper:** separating *deciding* (LLM) from *rendering* (Magnific) — with the decision expressed as a typed, rationale-carrying parameter plan — is a pattern, not a prompt.
2. **Both sponsors used where they're strongest:** Akamai for tiered, cost-engineered inference (provable in the ledger); Magnific for five different engines including video.
3. **Two products, one engine:** the ad studio *and* the listing factory share the same decide→render architecture.
4. **Ships under pressure:** budget caps, graceful degradation, offline replay of real output — and when the venue gateway died, we re-provisioned inference on Akamai cloud via API mid-hackathon.
5. **Everything on this page is reproducible from the repo in one minute, offline.**
