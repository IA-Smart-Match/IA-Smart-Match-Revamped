# Mascot tutorial + class-exercise redesign mockups

Owner-review mockups on the `Frontend-Experimental` branch. **Not app code** — nothing
here is imported by `apps/`. Static HTML/CSS/JS only (Google Fonts from the web; no build).

## View them

From the repo root:

```bash
python3 -m http.server -d docs/design/class-exercise/mascot-tutorial 8765 --bind 127.0.0.1
```

| Mockup | URL |
|---|---|
| A · Playful Learning (Duolingo-style path) | http://127.0.0.1:8765/redesign/a-playful/ |
| B · Friendly Tech (calm product, left step rail) | http://127.0.0.1:8765/redesign/b-friendly-tech/ |
| C · Soft Studio (mascot palette, step-card deck) | http://127.0.0.1:8765/redesign/c-soft-studio/ |
| Original tour mockup (CPP green, 2D vs 3D mascot) | http://127.0.0.1:8765/mockup/ |

Each redesign has a reviewer bar at the top to jump between screens and a "Tour" button
to replay the mascot walkthrough. Serve from this folder — opening `index.html` via
`file://` breaks the shared `../../mockup/assets/` art.

## What's here

- `redesign/<a|b|c>/NOTES.md` — palette + contrast, type, clutter counts, pose map, next refinements.
- `redesign/<a|b|c>/screenshots/` — every screen at 1440×900 plus key screens at 390×844.
- `mockup/assets/` — the 2D mascot ("Bree") poses and faces shared by all mockups.
- `PLAN.md` — library shortlist, performance budget for the VM and classroom PCs, tour architecture.
- `IMAGE-PROMPTS.md` — prompts to generate more mascot poses with an image model.

The img2threejs 3D workspace and the first round of before/after screenshots stay local
(the owner chose 2D; 3D was dropped).
