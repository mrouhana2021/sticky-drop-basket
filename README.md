# StickyBounce

A mixed-reality game where digital balls fall down your screen and bounce off **real orange sticky notes** you hold up in front of your laptop/tablet's camera.

Built as a fun activity for kids.

This fork runs in **single-device mode**: one laptop (or 2-in-1 like a Surface) is both the camera and the screen. No projector, no separate camera, no calibration step — you just watch the game on the laptop screen with your own live camera feed as the background.

---

## How it works

```
Laptop camera (front or rear)
     │
     ▼
Python + OpenCV  ──── detects orange sticky notes (position + angle)
     │                also streams the live camera frame itself
     │  WebSocket (JSON: notes + frame)
     ▼
Browser + Matter.js  ──── draws the camera frame as the background,
                           runs physics sim, renders balls on top
     │
     ▼
Laptop screen  ──── you watch the whole thing right there
```

1. `server.py` captures the webcam feed, detects orange sticky notes with color detection (HSV thresholding), and streams both the note positions **and** the camera frame itself to the browser over a local WebSocket.
2. `index.html` draws that camera frame as the canvas background, and Matter.js turns each detected note into a static rigid body.
3. Colorful balls spawn from the top and fall under gravity, deflecting off wherever a note is.
4. Because detection happens on the exact frame that gets displayed, note position and screen position always match — no homography/calibration needed.

---

## Hardware required

- A laptop or 2-in-1 (tested for Windows) with a webcam — front-facing, or rear-facing on something like a Surface
- **Orange sticky notes**

---

## Setup

**1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it** (PowerShell):
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**2. Clone the repo and install dependencies:**
```bash
git clone <repo-url>
cd "Sticky Bounce"
uv sync
```

---

## Running the game

**Terminal:**
```bash
uv run server.py
```

**Browser:** open `index.html` (double-click it, or drag it into a browser tab). Press **F** to fullscreen.

Balls will start falling. Hold an orange sticky note up in front of the camera and watch them bounce off it — you'll see yourself doing it live on screen, with the notes and balls drawn right on top of the video.

---

## Front camera vs. rear camera (e.g. Surface)

By default `server.py` uses camera index `0` and **mirrors** the image, like a selfie cam — good for a laptop's built-in front camera where you're facing the screen and want left/right to match what you see in a mirror.

If you'd rather hold the device up and point its **rear** camera at the notes (so you can watch the screen while the back of the laptop/tablet faces the notes/wall), turn mirroring off and pick the rear camera's index:

```bash
uv run server.py --camera 1 --no-mirror
```

Not sure which index is the rear camera? Preview each one first:
```bash
uv run tune.py --camera 0
uv run tune.py --camera 1
```
Whichever shows the *outward-facing* view is your rear camera — use that index with `--no-mirror` when you launch `server.py`. (Mirroring only affects how it looks/feels; it doesn't affect detection accuracy either way.)

---

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `F` | Toggle fullscreen |
| `D` | Toggle debug outlines (shows detected note boundaries in red) |

---

## Tuning & troubleshooting

### Notes not being detected, or your hand/face is being detected as a "note"?

Orange sits close to skin tone in hue, so this is the main thing to tune. Run the tuning tool to check detection live:
```bash
uv run tune.py
```
Hold an orange sticky note in front of the camera — it should turn **cyan** and get a green box. If it doesn't, or if skin/background is getting picked up instead, open `server.py` and `tune.py` and adjust these values at the top (keep them identical in both files):

```python
ORANGE_LOWER = np.array([5,  130, 120])   # H_min, S_min, V_min
ORANGE_UPPER = np.array([22, 255, 255])   # H_max, S_max, V_max
```

- **Skin getting detected?** Raise `S_min` and/or `V_min` (2nd/3rd numbers) — skin is usually less saturated/bright than sticky-note paper under normal indoor light.
- **Real notes not detected?** Lower `S_min`/`V_min`, or widen the hue range a little (e.g. `4` to `25`).
- There's also an aspect-ratio filter (`MIN_ASPECT_RATIO` / `MAX_ASPECT_RATIO`, default `0.4`–`2.5`) that rejects long skinny blobs like an arm or sleeve, since a sticky note is roughly square.

HSV hue reference (OpenCV uses 0–180):

| Color  | H range |
|--------|---------|
| Orange | 4–20    |
| Yellow | 18–35   |
| Pink   | 145–180 + 0–10 |
| Green  | 35–85   |

### Wrong camera, or want the rear camera?
```bash
uv run server.py --camera 1            # try a different index
uv run server.py --camera 1 --no-mirror  # rear camera, unmirrored
```

### Laptop feels slow / choppy video

The camera frame is streamed to the browser as JPEG over the WebSocket. If it's laggy, lower `JPEG_QUALITY` or `CAPTURE_WIDTH`/`CAPTURE_HEIGHT` at the top of `server.py` (and update the matching `W`/`H` at the top of `index.html`'s script — they must stay equal for notes to line up with the video).

---

## Making it more fun

All tweaks are in `index.html`:

| What | Variable | Default | Try |
|------|----------|---------|-----|
| Spawn faster | `SPAWN_INTERVAL_MS` | `1400` | `800` |
| Bouncier balls | `restitution` in `Bodies.circle(...)` | `0.65` | `0.9` |
| Faster falling | `gravity.y` in `Engine.create(...)` | `1.5` | `2.5` |
| Bigger balls | `BALL_RADIUS` | `18` | `28` |
| More balls max | `MAX_BALLS` | `40` | `80` |
| Spawn position | `const x = W / 2` | center | `W * 0.3` |
| Hoop gap width | `RIM_GAP` | `110` | `90` (harder) / `140` (easier) |
| Baskets needed to finish a round | `RACE_TARGET` | `5` | `10` for a longer race |
| Hoop vertical range | `HOOP_Y_MIN` / `HOOP_Y_MAX` | `0.38`–`0.58` of screen height | raise/lower to taste |

---

## Competition mode

The game is now a timed race, not just an endless ball-drop:

1. **Start screen** — press **Start**, with an optional **2 Player Mode** checkbox.
2. **Countdown** — 3, 2, 1, GO!, then balls start falling and the clock starts.
3. **Race to `RACE_TARGET` baskets** (5 by default) — the hoop relocates after every basket, so each one has to be aimed for fresh. The HUD at the top shows your running time and basket count.
4. **Finish** — the clock stops the instant the last basket goes in.
   - Single-player: shows your time and a **Retry** button (back to the start screen).
   - 2-player mode: Player 1's finish screen shows **Onto Player 2 →**; after Player 2 finishes, it shows both times, declares the winner (lower time wins), and offers **Retry** to restart the whole match.

---

## Legacy: projector + separate camera mode

The original version of this project targeted a different physical setup: a projector displaying the game on a wall, and a *separate* camera (e.g. an iPhone via Continuity Camera) watching that wall from a different angle. That needed a one-time calibration step (`calibrate.py`) to map camera-space to screen-space via homography.

That mode isn't wired up in this fork (`server.py`/`index.html` now assume the camera and the display are the same device, so no homography is computed). `calibrate.py` is kept in the repo for reference only — see the note at the top of that file if you ever want to revive that setup.

---

## Tech stack

- **Python** — OpenCV (color detection + JPEG frame streaming), websockets
- **JavaScript** — Matter.js (physics), Canvas (rendering + video compositing)
- **uv** — Python package manager
