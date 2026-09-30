# Mascot image-gen prompts — pink pony guide

Paste-ready prompts to extend the mascot sheet. **Always attach the original sheet
(or `mockup/assets/pose1-guide.webp`) as the reference image** — every prompt below
assumes image-to-image / character-reference mode. Generate one pose per image.

## 0. How to use

1. Attach the reference image and select "character reference" / "keep identity"
   (Higgsfield: Nano Banana / GPT Image with reference; Midjourney: `--cref <url> --cw 100`).
2. Paste the **Character lock** block, then **one** pose block, then the **Output spec**.
3. Keep the same seed across a batch if the tool allows it; regenerate rather than edit
   when the face drifts.
4. Name files `pose-<nn>-<slug>.png` so they drop straight into `mockup/assets/`.

## 1. Character lock (paste first, every time)

```
The same character as the reference image: a chibi pink pony mascot, 2.5 heads tall,
soft salmon-pink coat with a lighter blush muzzle, rosy blush ovals on both cheeks,
large glossy dark-brown eyes with two white catchlights, small curved smile,
pointed pink ears with lighter pink inner ears, a big fluffy chocolate-brown mane
with a thick swooping forelock over the forehead, a long fluffy chocolate-brown tail,
dark-brown hooves, wearing a green short-sleeve polo shirt with a white quarter-zip
collar. Stands upright on two legs, arms like short rounded forelegs with hooves.
Thick warm-brown ink outline, soft cel shading with a gentle watercolor texture,
cozy friendly kawaii sticker style. Exactly match the reference's proportions,
colors, face, and line weight.
```

## 2. Output spec (paste last, every time)

```
Full body, centered, character fills about 80% of the frame height, three-quarter
front view unless stated, isolated on a pure transparent background (or flat #FFFFFF
if transparency is unavailable), no background scenery, no text, no watermark, no
border, no drop shadow except a soft oval contact shadow under the hooves.
Square 1024x1024, crisp edges, sticker-ready.
```

**Negative / avoid** (for tools that take one):
`extra limbs, extra fingers, human hands, realistic horse anatomy, photorealistic,
3d render, plastic, cat ears, unicorn horn, wings, different outfit, logo on shirt,
text, speech bubble, background, harsh shadows, deformed face, cropped hooves`

> Shirt colour: the green polo is part of the character's identity. If the owner
> wants the UI off green, a variant is to swap only the shirt — add
> `wearing a <periwinkle / coral / sky-blue> polo shirt instead of green` to the
> lock. Decide once and use it for every pose, or the set will not match.

## 3. Pose prompts — mapped to where the app uses them

Each block goes between the lock and the output spec.

### Tour & navigation

**01 · Pointing right (tour: "look over here")**
```
Pose: standing turned slightly to the right, one foreleg stretched out pointing
confidently to the right edge of the frame, other hoof on hip, eyes following the
point, bright encouraging smile, mane bouncing with motion, small sparkle near the
pointing hoof.
```

**02 · Pointing up (tour: "the tabs at the top")**
```
Pose: looking up, one foreleg raised high pointing straight up, standing on tiptoe,
mouth open in an excited "see?" expression, tail flicking up behind.
```

**03 · Pointing down (tour: "your list is below")**
```
Pose: leaning forward and looking down, one foreleg pointing down toward the bottom
of the frame, other hoof resting on knee, curious helpful expression.
```

**04 · Holding a clipboard (tour step intro / "here's the plan")**
```
Pose: holding a small clipboard against the chest with both forelegs, one ear tilted,
confident teacher-like smile, a tiny pencil tucked behind one ear.
```

**05 · Open arms (welcome back)**
```
Pose: both forelegs spread open wide in a warm welcoming gesture, head tilted,
eyes closed happily in a big grin, as if saying "welcome back!".
```

### Working moments

**06 · Adjusting sliders (weights screen)**
```
Pose: standing beside a large floating control panel with three chunky rounded
sliders, one hoof pushing a slider knob upward, tongue slightly out in concentration,
determined focused eyes. Panel is simple flat shapes in soft grey with no text.
```

**07 · Thinking with lightbulb (hint / "try this")**
```
Pose: one hoof on chin, eyes looking up and to the side, thoughtful small smile,
a glowing yellow lightbulb floating above the head with tiny rays.
```

**08 · Comparing two cards (save & compare screen)**
```
Pose: holding up two small blank cards, one in each foreleg, looking back and forth
between them with raised eyebrows, playful "hmm, which one?" expression.
```

**09 · Reading a long list (ranked list / loading list)**
```
Pose: holding a long paper scroll that unrolls down to the ground, reading it with
wide interested eyes, one ear perked up, small motion lines at the scroll's end.
```

**10 · Sending invitations (results: invite 30)**
```
Pose: mid-toss, throwing a small bundle of paper envelopes into the air with both
forelegs, envelopes fluttering around, cheerful open-mouth smile, one hind hoof lifted.
```

**11 · Waiting / loading (spinner states)**
```
Pose: sitting cross-legged on the ground, holding a small hourglass in both hooves,
calm patient half-closed eyes, gentle smile, a few floating "..." dots rendered as
three small round shapes (no text).
```

### Feedback moments

**12 · Oops / gentle error**
```
Pose: sheepish apologetic pose, one hoof scratching the back of the head, small sweat
drop by the forehead, awkward lopsided smile, ears slightly drooped, still friendly.
```

**13 · Locked / "wait for your instructor"**
```
Pose: holding a large cute padlock in both forelegs, patient friendly expression,
one eye winking, as if saying "not yet — soon!".
```

**14 · Empty state / nothing here yet**
```
Pose: peeking out from behind a large rounded empty box, only the head, mane and two
hooves visible over the edge, curious big eyes, tiny question-mark shape above
(drawn as a shape, not text).
```

**15 · High five (step complete)**
```
Pose: jumping slightly toward the viewer with one foreleg raised for a high five,
huge happy grin, eyes squeezed shut with joy, small star sparkles at the raised hoof.
```

**16 · Trophy (round finished / you're done)**
```
Pose: proudly holding a small golden trophy above the head with both forelegs, chest
puffed out, sparkling eyes, confetti pieces falling around in pink, periwinkle and
cream.
```

**17 · Thumbs-up hoof (saved / confirmed)**
```
Pose: standing relaxed, one foreleg giving a hoof "thumbs-up" toward the viewer, a
confident wink, warm smile.
```

### Idle loop frames (for a subtle breathing / blinking idle)

**18 · Idle A — neutral standing**
```
Pose: neutral relaxed standing pose, forelegs at the sides, soft smile, eyes open,
facing three-quarter front. This is the base frame for an idle animation loop.
```

**19 · Idle B — blink**
```
Identical to a neutral relaxed standing pose, forelegs at the sides, soft smile,
three-quarter front — but with both eyes gently closed in a blink. Keep everything
else pixel-identical in position and size.
```

**20 · Idle C — stretch / yawn**
```
Pose: stretching both forelegs up above the head in a big lazy yawn, eyes closed,
mouth open in a small yawn, tail relaxed.
```

## 4. Expression sheet (head-only, for the tour bubble avatar)

```
[Character lock]
A clean expression sheet of the SAME pony character's head and shoulders only,
arranged in a 4 x 2 grid of equal cells on a transparent background, identical
size and angle in every cell, no text, no labels:
1 happy smile, 2 excited open-mouth grin with sparkly eyes,
3 curious one ear up with tilted head, 4 thinking with eyes looking up,
5 surprised round eyes and small "o" mouth, 6 proud smug closed-eye smile,
7 apologetic with small sweat drop, 8 sleepy content with closed eyes.
Thick warm-brown outline, soft cel shading, kawaii sticker style.
```

Crop the grid into `face-<nn>-<slug>.png` at 256×256.

## 5. Optional scene tiles (onboarding / empty-state backgrounds)

**Campus welcome banner (wide)**
```
[Character lock]
Wide 16:9 illustration: the pony standing on a soft rounded hill waving, a simple
stylized modern campus building silhouette far behind in pale periwinkle, a few
rounded pastel clouds, lots of empty space on the left for a headline, soft pastel
gradient sky from cream to light periwinkle. No text, no logos.
```

**Night / all done (session over)**
```
[Character lock]
Wide 16:9 illustration: the pony curled up asleep on a big fluffy white cloud, a
crescent moon and small stars, deep periwinkle-to-lavender night gradient, calm and
cozy, no text.
```

## 6. Quality check before adding an image to the set

- Face matches the reference (eye shape, blush, forelock) — reject any drift.
- Same outline weight and shading as `pose1-guide.webp` when placed side by side.
- Hooves, not hands. No extra limbs. Shirt collar is the white quarter-zip.
- Transparent background with no halo; trim, then export WebP q≈85 at 2× display
  size (e.g. 512 px tall for a 256 px slot).
