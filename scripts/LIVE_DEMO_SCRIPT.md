# Live demo script — Ad-in-a-Box (~4–5 min + Q&A)

Format: **[DO]** = your hands. **[SAY]** = your mouth. **[EXPLAIN]** = the depth
behind the step — use it when a judge leans in or asks "wait, how?". Don't recite
[EXPLAIN] unprompted; live demos die from over-narration.

---

## ⏱ T-minus 60 seconds (before judges arrive)

```
1. Server up:      .venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000
2. Browser at:     http://127.0.0.1:8000   (hard-refresh, Ad Studio tab)
3. Sound ON (the ad videos have audio — it's a wow moment)
4. Close other tabs; zoom browser to ~110% so the back row sees the slider
5. Backup: repo is public — if the laptop dies, clone-and-run is 60s anywhere
```

DEMO_MODE=1 replays **real captured Magnific output** instantly — no network
needed. You can demo in a faraday cage.

---

## 1 · The hook (0:00)

**[SAY]**
> "Making one ad campaign takes a copywriter, an art director, a retoucher, and
> a video editor. I'm going to do it in one sentence. Watch the whole thing —
> copy, images, video, even the landing page — come out of one line of text."

**[DO]** Nothing yet. Hands off the keyboard. Eye contact. Then…

## 2 · One sentence in (0:20)

**[DO]** Click the **perfume chip** — it auto-runs. Cards appear instantly.

**[SAY]** (while cards render)
> "Two LLMs on **Akamai Inference Cloud** just ran. A small, cheap **Qwen3-8B**
> wrote six ad concepts — that's the high-token grunt work. Then the bigger
> **Qwen3-14B** ran *exactly once* as the art director: it picked the best three
> and — here's our whole idea — it didn't make the images. It wrote the
> **parameters** for Magnific to make the images."

**[EXPLAIN — if asked "what parameters?"]**
> The smart tier emits strict JSON per creative: the full image prompt, the
> aspect ratio for the channel, a relight prompt phrased as light direction +
> quality + color temperature, a creativity integer from −10 to +10 (negative =
> stay faithful for product accuracy, positive = let Magnific reinvent detail),
> an upscale factor, and a one-sentence rationale. It's a typed contract —
> `ParamPlan` in `backend/models.py` — not freeform prompting.

**[EXPLAIN — if asked about the GPUs/models]**
> Both models are FP8-quantized — that format only exists for modern NVIDIA
> tensor cores, served by vLLM on Akamai's GPU cluster. FP8 roughly doubles
> GPU throughput at the same quality, and our tiering is GPU economics: the
> small model soaks up token volume, the big one spends a single GPU call.

## 3 · The before/after — the money shot (1:00)

**[DO]** Go to the **Billboard 16:9 card**. Drag the slider **slowly** from
left to right. Pause halfway. Then all the way.

**[SAY]**
> "Left: Magnific's raw text-to-image draft. Right: after two more Magnific
> engines — **Relight**, with lighting *the LLM chose* — read the chip: 'dramatic
> warm spotlight from above' — and the **Upscaler** at 8x with creativity +5,
> also the LLM's call. And this italic line? The model explaining *why*: a
> billboard earns print detail, and high creativity invents the silk and mist
> around an accurate bottle. Every creative justifies its own art direction."

**[EXPLAIN — if asked "is this real output?"]**
> Yes — every image you're seeing is real Magnific API output, generate →
> relight → upscale. The originals run up to 10,880 pixels; we serve web-sized
> copies. The repo has the full chain committed, and the demo replays it
> offline so venue Wi-Fi can't hurt us. It did die mid-hackathon. We shipped
> anyway.

## 4 · The ad video (1:50)

**[DO]** Click **▶ Ad video** on the billboard card. Let it play with SOUND
(~5s). Don't talk over the first 2 seconds.

**[SAY]** (as mist swirls)
> "Feeds don't show posters, they show motion. So the hero frame becomes a
> five-second ad video — Magnific's video engine, seeded from our relit hero,
> with sound. And notice we're now on the landing page this ad drives to —
> every call-to-action in this app is clickable, down to add-to-cart."

**[DO]** Click **Add to cart** (toast pops), close the modal.

## 5 · The ledger — the Akamai slide, live (2:30)

**[DO]** Scroll up to the **Inference & spend ledger**. Trace the headline.

**[SAY]**
> "Here's what CFOs ask about. The cheap fast tier handled ~39% of the tokens.
> The expensive smart tier ran **once**. Total LLM cost for this whole campaign:
> **a tenth of a cent**. And every Magnific credit — draft, relight, upscale,
> video — itemized per stage with latency. We don't just use AI, we *price every
> decision*. That's the Akamai play: right-sized models, GPU-seconds as budget."

**[EXPLAIN — if asked about cost numbers]**
> Token counts and latencies come from the live runs (`usage` off the API);
> costs are $/Mtok constants in `.env` — $0.10 fast, $1.00 smart. Magnific
> credits per engine are in `backend/magnific.py`. Live runs also carry a hard
> budget cap — `MAX_MAGNIFIC_CALLS_PER_RUN=6` — and clamp upscale to 4x;
> the 8x money shot is reserved for the cached demo. Cost control is in the
> pipeline, not a slide.

## 6 · Feature two: the Listing Factory (3:10)

**[DO]** Click the **Listing Factory** tab → **Run factory**. Cards + the
export toolbar appear.

**[SAY]**
> "Same engine, second product. Give it messy seller photos — a phone pic of
> sneakers on the floor. The Akamai smart tier writes the SEO title, the
> description, tags, even a price — and *decides the cleanup recipe per photo*.
> Magnific executes: background removal, studio relight, upscale."

**[DO]** Drag the **sneaker slider**: messy wood floor → black studio shot.

**[SAY]**
> "Messy photo in. Storefront shot out. And it doesn't stop at pretty —"

**[DO]** Point at the **export toolbar**, click **⬇ Shopify CSV** (file downloads).

**[SAY]**
> "— one click exports every listing as an import-ready file: Shopify product
> CSV, a Google Merchant Center feed — that's **free** Google Shopping placement,
> zero ad spend — and a Meta catalog for Instagram Shops. From phone photo to
> three sales channels in under a minute."

**[EXPLAIN — if asked about integrations depth]**
> The pipeline ends in typed Pydantic objects, so each platform is just an
> adapter — `backend/publishers/exports.py` today, and the live API pushes
> (Shopify Admin GraphQL, Content API, Marketing API) slot in beside it.
> Because the LLM already plans per-channel, extending the channel list to
> PMax or Reels specs makes it emit platform-compliant assets automatically.

## 7 · Close (4:15)

**[DO]** Back to Ad Studio tab, billboard on screen.

**[SAY]**
> "One sentence in. Six concepts, three finished creatives, an ad video, a
> landing page, and a storefront export — out. For a tenth of a cent of
> inference. **Akamai decides. Magnific renders.** Happy to go deeper anywhere."

---

## 🧨 Q&A ammunition (one breath each)

- **"What's actually novel?"** → "Separating *deciding* from *rendering*. The
  LLM is the art director, not the artist — it emits a typed, rationale-carrying
  parameter plan, and the ledger prices each decision. That's a reusable
  pattern, not a prompt."
- **"How do you use Akamai exactly?"** → "Two-tier inference on Akamai's GPU
  cloud — FP8 Qwen3 models behind vLLM, OpenAI-compatible. Fast 8B does token
  volume, 14B runs once per campaign. When the venue gateway died we
  re-provisioned an inference box on Akamai Connected Cloud via API — the
  pipeline is endpoint-portable."
- **"How do you use Magnific exactly?"** → "Five engines: Mystic text-to-image,
  Relight with LLM-chosen light direction, the Upscaler with LLM-chosen
  creativity and factor, background removal for listings, and the video engine
  for hero spots."
- **"What breaks if an API fails?"** → "One creative degrades to its best
  available image and the run continues — never aborts. Malformed LLM JSON gets
  one cheap repair call. And the whole demo replays real output offline."
- **"Is this a business?"** → "The Listing Factory alone is a Shopify app:
  messy photos to storefront with free Google Shopping distribution. The export
  buttons you saw are the first mile of that integration, working today."
- **"What would you do with a week?"** → "Live pushes — Shopify Admin API,
  Content API, Marketing API — plus PMax-spec channels so the smart tier emits
  platform-compliant assets natively. The adapter layer is already shaped
  for it."

## 🚑 If something breaks live

| Symptom | Move |
|---|---|
| Browser hangs / tab crash | Reopen `http://127.0.0.1:8000` — demo replay is instant, restart the click path |
| Server died | `.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000` (5 seconds), keep talking through the hook |
| Video won't play | Open `backend/static/runs/demo_perfume/c6_video.mp4` directly — same file |
| Laptop catastrophic | Repo is public: clone → pip install → run, 60 seconds on any machine; README carries the screenshots and GIFs as proof meanwhile |
| Judge wants live (non-demo) run | Be straight: "live mode needs the LLM endpoint + Magnific key wired; demo mode replays *captured real output* so judging isn't hostage to venue Wi-Fi — that resilience is itself a feature" |
