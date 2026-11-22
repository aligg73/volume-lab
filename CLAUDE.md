# Volume Lab

A mixed-reality version of a Montessori volume lesson for schoolchildren. In the real lesson the teacher:
1. shows the golden-bead **thousand cube** (10 × 10 × 10 cm = 1000 cm³) and turns it into **1 litre** of water,
2. pours that litre into differently shaped glass vessels (tall jar, wide bowl, round flask), so children see the amount stays the same in every shape,
3. uses a measuring jug with **red stickers** covering holes at different heights. Standing over a red basin, the teacher peels the stickers off and water jets out, farther from the deeper holes (water pressure increases with depth).

Goal: children do this with their own hands. There's no controller: a tablet camera tracks the hand, the child sees a simple digital hand on screen (not the camera image), and real hand movements grab the jug, pour, and peel stickers.

## Files

- `index.html`: **main app.** Hand-tracking mixed reality (front camera "mirror mode" by default, back camera optional). Self-contained, one file.
- `desktop.html`: earlier prototype. Mouse/touch on a 3D table, plus an experimental WebXR "Enter AR" mode for Quest (controller or pinch grab). Shares the same physics; keep it working but it's secondary.
- `tests/gesture_sim.py`: Playwright test that feeds synthetic hand landmarks into `index.html?debug` and checks melt → pour → peel.

## Stack and constraints

- Plain HTML + JS, no build step. Libraries load from CDNs and are pinned:
  - three.js **0.128.0** UMD build (`window.THREE`) from jsdelivr. Old version on purpose: it still ships non-module builds and `examples/js`. If you upgrade, switch to ES modules + an import map, and note r152+ colour management changes how hex colours look (the lights were tuned for linear output with no `outputEncoding`).
  - MediaPipe `@mediapipe/tasks-vision` **0.10.14**, `HandLandmarker`, `runningMode: 'VIDEO'`, `numHands: 2`, GPU delegate with CPU fallback. The model `.task` file loads from `storage.googleapis.com`.
- **The camera needs a secure context**: https://, or `localhost`. A LAN address like `http://192.168.x.x` will NOT get camera access.
- Claude artifact pages block the camera (sandboxed iframe), so the MR app must be hosted elsewhere (GitHub Pages, Netlify, etc.).
- Target device: Lenovo IdeaPad Tab (Android, Chrome). Keep the frame cost low: renderer pixel ratio is capped at 1.5, and the hand canvas runs at CSS pixel size.

## Architecture (index.html)

Layers, bottom to top: `<video>` camera feed (object-fit: cover, mirrored for the front camera) → `#wall` (covers the camera image by default; "Show camera" hides it. Do NOT hide the video itself with opacity/visibility: Chrome on Android may stop delivering frames) → three.js canvas (transparent, over a CSS wall gradient) → `#fx` 2D canvas (digital hands) → UI cards.

**Units:** metres, millilitres, seconds; y is up. The shelf top is y = 0. The jug group's origin is the centre of its base.

**Physics model:** cheap and deterministic, no fluid simulation.
- Jug = cylinder R = 0.055 m, H = 0.17 m. The water level comes from the volume (V / πR² along the jug axis). The surface is drawn by clipping a water cylinder with a world-space plane (`levelPlane`), plus an elliptical cap disk scaled 1/cos(tilt).
- Pour: retained capacity in a tilted cylinder is `A(H − R·tanθ)`, or `A·H²/(4R·tanθ)` past the point where the surface reaches the base. Any excess flows over the lowest rim point at ≤ 420 ml/s.
- Holes: Torricelli, v = √(2·g·depth), Q = 0.62 · A_hole · v (5 mm holes). Depth = surface height − hole height, in world space.
- `land(p0, v0)`: ballistic stepping. Water lands in the first vessel whose rim plane it crosses inside the rim, and stops at that vessel's water surface or wall. Otherwise it spills onto the shelf (puddle). Volume is moved instantly, so **total water is conserved exactly**. That's a teaching point; keep it true.
- Vessels are lathe profiles `[[radius, y], …]` with a precomputed volume→height table (`hAt`), so any shape works.

**Hand interaction** (`processHands` → `act`), all in screen pixels, with thresholds scaled by palm length (wrist → middle knuckle):
- hands are rescaled about their centre to a fixed palm size `handPx` (= `HAND` 0.075 m projected at jug depth; tune with `?hand=0.09`), so a hand near the camera doesn't get huge. Size = max(wrist→middle MCP, index→pinky MCP / 0.75), scale smoothed 0.2/frame. Gestures run on the rescaled hand, so what's drawn is what interacts
- landmarks are smoothed (factor 0.55 per frame); a hand unseen for 350 ms releases what it holds
- fist (grip): middle/ring/pinky tips average < 1.25 palm from the wrist AND index tip < 1.45. Releases at > 1.55 (hysteresis)
- pinch: thumb–index tip distance < 0.30 palm, releases at > 0.50; never at the same time as a grip
- grab the jug: a fist within ~0.9 × jug screen height of the jug centre. The jug follows the hand centre on the plane z = 0.02 (no depth). Tilt = change in the knuckle-line angle (index MCP → pinky MCP) since the grab, × 1.3, clamped to ±130°
- peel: pinch within ~0.55 palm of a sticker, then pull; fully off after 0.9 palm of travel
- cube: index fingertip (or a pinch) touches it → melts into 1000 ml
- releasing the jug puts it on the shelf if there's room, otherwise back on its stand in the basin

**Digital hands:** a white "glove" silhouette (palm polygon + round finger strokes; outline pass then fill pass into an offscreen canvas, composited at 0.9 alpha) with a cuff and drop shadow. Colour shows state: blue = fist/holding, red = pinch/peeling. With no hands tracked, a "Show your hands to the camera" hint appears. Deliberately not photo-realistic: the camera image (and the child's face) distracted from the task.

## Testing

- Logic without a camera: `python -m http.server 8000`, then `python tests/gesture_sim.py` (without a local Playwright: `uv run --with playwright==1.59.0 python tests/gesture_sim.py`, which matches the cached Chromium). Screenshots go to `tests/out/`. Extend it whenever you change gestures or physics.
- On the tablet with live debugging: enable USB debugging, connect, then
  `adb reverse tcp:8000 tcp:8000` → open `http://localhost:8000/` in Chrome on the tablet. That counts as a secure context, so the camera works. Use `chrome://inspect` on the desktop for console and performance.
- The help panel shows tracked hands and the tracking fps. Under ~12 fps it feels laggy.

## Known limitations

- No real depth from a single camera: interaction is 2.5D (screen plane).
- Water passes through walls; no splashing.
- The surface cap is approximate at steep tilt with little water left.
- The digital hand always draws in front of the jug. With "Show camera" on, the real hand and the (smaller) digital hand don't line up; that view is for the teacher/debugging.
- Gesture thresholds are tuned on synthetic hands only, not yet on real children's hands.
