# Manual Magnific generation sheet (web UI)

No API/MCP access on this account → generate these 6 hero shots **by hand** at
magnific.com using your 30k credits, download each, and save with the exact
filename shown. Then run `py scripts/build_real_demos.py` to wire them into the
DEMO_MODE cache.

All prompts/params below are the **real** LLM choices captured live from Akamai
(Qwen3-14B smart tier) — see `scripts/_live_plans.json`.

Per creative do three UI steps: **Generate (Mystic)** → **Relight** → **Upscale**.
Save the Mystic output as `<cid>_draft` and the final upscaled output as
`<cid>_final` (PNG or JPG, either is fine). Saving the relight step as
`<cid>_relit` is optional but nice for the slider.

Save everything under:  `scripts/real_images/demo_coffee/`  and  `scripts/real_images/demo_shoe/`

---

## ☕ COFFEE  (brief: specialty single-origin coffee bag, hand-roasted, small batches)

### c1 — Instagram square · aspect **1:1** · upscale **4x** · creativity **+3**
- **Generate prompt:** A close-up of a hand-roasted coffee bean with a rustic coffee bag in the background, golden light highlighting the texture of the bean and the bag, cinematic lighting, natural textures, warm tones, high detail
- **Relight:** warm golden-hour key light from camera right, soft wraparound shadows, amber rim light
- **Save:** `demo_coffee/c1_draft.png`, `demo_coffee/c1_final.png`

### c2 — Story vertical · aspect **9:16** · upscale **4x** · creativity **+2**
- **Generate prompt:** A person sipping coffee with a close-up of the coffee bag and a map showing the origin of the beans, soft natural lighting, warm tones, cinematic composition, focus on the person and the bag
- **Relight:** soft natural daylight from camera left, warm ambient light, subtle shadows
- **Save:** `demo_coffee/c2_draft.png`, `demo_coffee/c2_final.png`

### c6 — Billboard wide · aspect **16:9** · upscale **8x** (money-shot) · creativity **+5**
- **Generate prompt:** A bold, textured shot of a coffee bag with a steaming cup and a sunlit backdrop highlighting the craftsmanship, dramatic lighting, high contrast, cinematic composition, dark background
- **Relight:** dramatic directional sunlight from camera left, high contrast, deep shadows, warm golden light
- **Save:** `demo_coffee/c6_draft.png`, `demo_coffee/c6_final.png`

---

## 👟 SHOE  (brief: lightweight trail running shoe, grippy all-terrain soles)

### c1 — Instagram square · aspect **1:1** · upscale **4x** · creativity **+2**
- **Generate prompt:** A trail runner mid-stride on a rocky path, focused and determined, with the shoe's soles clearly showing grip on uneven terrain. The scene is dynamic, with natural lighting from above, emphasizing the texture of the shoe's sole and the rugged trail. Style: photorealistic, cinematic.
- **Relight:** soft natural daylight from above, directional shadows to highlight the shoe's sole texture, cool blue tones with warm highlights from the rocks
- **Save:** `demo_shoe/c1_draft.png`, `demo_shoe/c1_final.png`

### c2 — Story vertical · aspect **9:16** · upscale **4x** · creativity **+1**
- **Generate prompt:** Close-up of the shoe's sole with dirt and rocks, showing grip, set against a mountain backdrop. The sole is in sharp focus, with natural textures and dirt embedded in the treads. Style: hyper-realistic, with a dramatic mountain landscape in the background.
- **Relight:** dramatic side lighting from the left, creating deep shadows and high contrast, cool blue tones with warm highlights from the rocks
- **Save:** `demo_shoe/c2_draft.png`, `demo_shoe/c2_final.png`

### c6 — Billboard wide · aspect **16:9** · upscale **8x** (money-shot) · creativity **+4**
- **Generate prompt:** A runner in motion on a rocky trail, mid-step, with the shoe's soles clearly showing grip on uneven ground. The scene is set in a forest with sunlight filtering through the trees, creating a dynamic and natural lighting effect. Style: cinematic, photorealistic.
- **Relight:** golden-hour key light from the front-right, soft shadows, warm amber tones with cool highlights from the forest canopy
- **Save:** `demo_shoe/c6_draft.png`, `demo_shoe/c6_final.png`

---

Approx credit spend: 6 generates + 6 relights + 6 upscales (two at 8x). Plenty
of headroom in 30k. When done: `py scripts/build_real_demos.py`
