"""Generate DEMO_MODE cached runs (venue Wi-Fi insurance).

Writes two pre-baked RunState JSON files to backend/demo/ plus matching
before/after creative images to backend/static/runs/demo_*/.

The images are self-contained SVGs (no image library needed) deliberately
styled so the DRAFT looks flat/desaturated and the FINAL looks relit +
upscaled — the before/after slider reveal is the demo's money shot.

>>> py scripts/build_demos.py     # regenerate

At the venue, replace the SVGs with REAL captured Magnific outputs for the
strongest live result, keeping the same filenames; the JSON needs no change.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "backend" / "demo"
STATIC_RUNS = ROOT / "backend" / "static" / "runs"

DIMS = {"square_1_1": (1000, 1000), "story_9_16": (720, 1280), "wide_16_9": (1600, 900)}
CHANNEL_AR = {
    "instagram_square": "square_1_1",
    "story_vertical": "story_9_16",
    "billboard_wide": "wide_16_9",
}


def _svg(w: int, h: int, hue: int, headline: str, cta: str, *, final: bool) -> str:
    """Build a stylized ad-creative SVG. final=True adds directional relight,
    rim light, vivid saturation and a vignette; draft is flat and muted."""
    sat = 70 if final else 22
    light = 58 if final else 46
    bg1 = f"hsl({hue},{sat}%,{light}%)"
    bg2 = f"hsl({(hue + 28) % 360},{sat}%,{max(8, light - 30)}%)"
    prod = f"hsl({(hue + 12) % 360},{sat + 10 if final else 18}%,{38 if final else 42}%)"
    cx, cy = w / 2, h * 0.52
    pw, ph = w * 0.40, h * 0.34
    glow = (
        f'<radialGradient id="key" cx="32%" cy="22%" r="75%">'
        f'<stop offset="0%" stop-color="hsl({hue},90%,82%)" stop-opacity="{0.9 if final else 0.0}"/>'
        f'<stop offset="55%" stop-color="hsl({hue},80%,60%)" stop-opacity="{0.25 if final else 0.0}"/>'
        f'<stop offset="100%" stop-color="#000" stop-opacity="0"/></radialGradient>'
    )
    rim = (
        f'<rect x="{cx - pw/2}" y="{cy - ph/2}" width="{pw}" height="{ph}" rx="26" '
        f'fill="none" stroke="hsl({(hue+200)%360},95%,80%)" stroke-width="5" stroke-opacity="0.9"/>'
        if final else ""
    )
    vignette = (
        '<radialGradient id="vig" cx="50%" cy="50%" r="75%">'
        '<stop offset="60%" stop-color="#000" stop-opacity="0"/>'
        '<stop offset="100%" stop-color="#000" stop-opacity="0.45"/></radialGradient>'
        '<rect width="100%" height="100%" fill="url(#vig)"/>'
        if final else ""
    )
    badge = "FINAL · MAGNIFIC 8x" if final else "DRAFT"
    fs = int(min(w, h) * 0.072)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
<stop offset="0%" stop-color="{bg1}"/><stop offset="100%" stop-color="{bg2}"/></linearGradient>
{glow}
</defs>
<rect width="100%" height="100%" fill="url(#bg)"/>
<rect width="100%" height="100%" fill="url(#key)"/>
<ellipse cx="{cx}" cy="{cy + ph*0.62}" rx="{pw*0.62}" ry="{ph*0.10}" fill="#000" fill-opacity="{0.32 if final else 0.16}"/>
<rect x="{cx - pw/2}" y="{cy - ph/2}" width="{pw}" height="{ph}" rx="26" fill="{prod}"/>
<rect x="{cx - pw/2}" y="{cy - ph/2}" width="{pw*0.5}" height="{ph}" rx="26" fill="#fff" fill-opacity="{0.10 if final else 0.04}"/>
{rim}
<text x="{cx}" y="{cy + ph*0.06}" font-family="Georgia,serif" font-size="{int(fs*0.6)}" fill="#fff" fill-opacity="0.92" text-anchor="middle">{_esc(headline.split()[0])}</text>
{vignette}
<text x="6%" y="{h*0.13:.0f}" font-family="Helvetica,Arial,sans-serif" font-weight="bold" font-size="{fs}" fill="#fff" fill-opacity="0.96">{_esc(headline)}</text>
<rect x="6%" y="{h*0.86:.0f}" width="{fs*4.4:.0f}" height="{fs*1.5:.0f}" rx="10" fill="#fff" fill-opacity="0.95"/>
<text x="{w*0.06 + fs*2.2:.0f}" y="{h*0.86 + fs*1.0:.0f}" font-family="Helvetica,Arial,sans-serif" font-weight="bold" font-size="{int(fs*0.5)}" fill="hsl({hue},70%,30%)" text-anchor="middle">{_esc(cta)}</text>
<text x="{w-12}" y="{h-16}" font-family="Helvetica,Arial,sans-serif" font-size="{int(fs*0.34)}" fill="#fff" fill-opacity="0.7" text-anchor="end">{badge}</text>
</svg>"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _stage(stage, eng, ms, ti=0, to=0, cost=0.0, credits=0):
    return {
        "stage": stage, "model_or_engine": eng, "latency_ms": ms,
        "tokens_in": ti, "tokens_out": to, "est_cost_usd": cost,
        "credits": credits, "ok": True, "note": "",
    }


def build_run(run_id: str, brief: str, hue: int, creatives: list[dict]) -> dict:
    run_dir = STATIC_RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    state_creatives = []
    for cr in creatives:
        ch = cr["channel"]
        ar = CHANNEL_AR[ch]
        w, h = DIMS[ar]
        cid = cr["id"]
        draft = run_dir / f"{cid}_draft.svg"
        final = run_dir / f"{cid}_final.svg"
        draft.write_text(_svg(w, h, hue, cr["headline"], cr["cta"], final=False), encoding="utf-8")
        final.write_text(_svg(w, h, hue, cr["headline"], cr["cta"], final=True), encoding="utf-8")
        base = f"/static/runs/{run_id}"
        state_creatives.append({
            "concept": {
                "id": cid, "channel": ch, "headline": cr["headline"], "body": cr["body"],
                "cta": cr["cta"], "visual_concept": cr["visual_concept"],
            },
            "plan": {
                "concept_id": cid, "image_prompt": cr["image_prompt"], "aspect_ratio": ar,
                "relight_prompt": cr["relight_prompt"], "creativity": cr["creativity"],
                "upscale_factor": cr["upscale_factor"], "rationale": cr["rationale"],
            },
            "draft_url": f"{base}/{cid}_draft.svg",
            "relit_url": f"{base}/{cid}_final.svg",
            "final_url": f"{base}/{cid}_final.svg",
            "status": "done",
            "stages": [
                _stage("draft", "magnific:mystic", 8200, credits=1),
                _stage("relight", "magnific:relight", 12400, credits=2),
                _stage("upscale", "magnific:upscaler", 17600, credits=3),
            ],
        })

    return {
        "run_id": run_id, "brief": brief, "status": "done", "stage": "done",
        "demo_mode": True,
        "concepts": [c["concept"] for c in state_creatives],
        "creatives": state_creatives,
        "stages": [
            # Fast tier emits verbose concept copy -> most of the tokens.
            _stage("concepts", "fast:llama-fast", 740, ti=600, to=3200, cost=0.00038),
            # Smart tier runs ONCE, emits compact JSON params -> few tokens.
            _stage("param_plan", "smart:llama-smart", 2180, ti=380, to=360, cost=0.00074),
        ],
    }


COFFEE = [
    dict(id="c1", channel="billboard_wide",
         headline="Mornings, Reinvented", body="Single-origin beans, hand-roasted in micro-batches for a cup with real depth and zero compromise.",
         cta="Shop the Roast", visual_concept="A lone coffee bag on weathered oak, steam curling, dawn light raking across.",
         image_prompt="Premium single-origin coffee bag on weathered oak table, volumetric dawn light, shallow depth of field, editorial product photography, 8k",
         relight_prompt="warm golden-hour key light from camera left, long soft shadows, amber rim light on the bag edge",
         creativity=4, upscale_factor="8x",
         rationale="Billboard needs print-grade detail, so 8x and +4 creativity let Magnific rebuild the foil texture under a dramatic golden-hour relight."),
    dict(id="c2", channel="instagram_square",
         headline="Taste the Origin", body="Notes of cocoa, citrus, and warm caramel from a single hillside harvest.",
         cta="Taste It", visual_concept="Overhead flat-lay of beans forming a ring around the bag on linen.",
         image_prompt="Top-down flat lay of coffee beans encircling a kraft coffee bag on natural linen, soft daylight, lifestyle product shot",
         relight_prompt="soft diffused overhead daylight, gentle warm fill, subtle highlight on the beans",
         creativity=2, upscale_factor="4x",
         rationale="The square feed shot prioritizes packaging accuracy, so +2 creativity keeps the label crisp while 4x is plenty for mobile."),
    dict(id="c3", channel="story_vertical",
         headline="Brew Bolder", body="Your 9am, upgraded. Slow-roasted, fast-shipped.",
         cta="Brew Now", visual_concept="Vertical hero of the bag with a pour-over and rising steam.",
         image_prompt="Vertical hero shot of coffee bag beside a glass pour-over, rising steam, moody cafe backdrop, cinematic",
         relight_prompt="warm tungsten key from upper right, cozy cafe glow, steam catching the light",
         creativity=3, upscale_factor="4x",
         rationale="Stories autoplay small, so 4x suffices, and +3 creativity adds the cinematic steam-and-glow mood that stops a thumb."),
]

SHOE = [
    dict(id="c1", channel="billboard_wide",
         headline="Own Every Trail", body="A featherweight runner with all-terrain grip that bites into mud, rock, and root.",
         cta="Find Your Pair", visual_concept="Side profile of the shoe mid-stride over rugged trail, dust kicking up.",
         image_prompt="Dynamic side profile of a trail running shoe over rocky terrain, kicked-up dust, dramatic backlight, sports product photography, 8k",
         relight_prompt="hard low-angle backlight from camera right, crisp rim light, cool ambient fill, kicked dust catching the sun",
         creativity=5, upscale_factor="8x",
         rationale="A billboard rewards drama, so 8x plus +5 creativity lets Magnific sculpt the sole tread and dust under a hard rim-lit backlight."),
    dict(id="c2", channel="instagram_square",
         headline="Grip That Holds", body="Multi-directional lugs and a rock plate keep you planted on any surface.",
         cta="Shop Soles", visual_concept="Close 3/4 of the outsole showing aggressive lugs on wet stone.",
         image_prompt="Three-quarter close-up of trail shoe outsole on wet stone, water droplets, detailed lug pattern, studio product macro",
         relight_prompt="bright neutral studio key with cool fill, sharp specular highlights on the wet rubber",
         creativity=2, upscale_factor="4x",
         rationale="This is a detail/proof shot, so low +2 creativity preserves the real lug geometry while 4x keeps it sharp in-feed."),
    dict(id="c3", channel="story_vertical",
         headline="Light. Fast. Yours.", body="Run longer on less. The trail is calling.",
         cta="Gear Up", visual_concept="Vertical action shot of the shoe on a runner mid-leap on a ridgeline.",
         image_prompt="Vertical action shot of trail shoe on a runner leaping along a mountain ridgeline at sunset, motion energy, cinematic",
         relight_prompt="warm sunset key from camera left, energetic rim light, cool sky ambient, motion glow",
         creativity=4, upscale_factor="4x",
         rationale="Vertical motion needs energy not resolution, so 4x with +4 creativity amps the sunset rim light and sense of speed."),
]


def main():
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    runs = {
        "coffee": build_run("demo_coffee", "A specialty single-origin coffee bag, hand-roasted in small batches.", 28, COFFEE),
        "shoe": build_run("demo_shoe", "A lightweight trail running shoe with grippy all-terrain soles.", 145, SHOE),
    }
    for name, run in runs.items():
        out = DEMO_DIR / f"{name}.json"
        out.write_text(json.dumps(run, indent=2), encoding="utf-8")
        print(f"wrote {out}  ({len(run['creatives'])} creatives)")
    print("done. set DEMO_MODE=1 to replay.")


if __name__ == "__main__":
    main()
