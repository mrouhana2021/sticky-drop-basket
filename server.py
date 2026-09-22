#!/usr/bin/env python3
"""
Sticky Bounce - Python backend (single-laptop mode)

The laptop's own webcam is both the "camera" and the thing the "screen"
mirrors: this script captures frames, detects orange sticky notes in them,
and streams BOTH the (mirrored) camera frame and the detected note
rectangles to the browser over WebSocket. Because the browser draws the
same frame it detects notes in, note coordinates line up with the video
pixel-for-pixel -- no projector, no separate camera, no calibration step
needed.

Usage:
    uv run server.py                        # front/built-in webcam, mirrored
    uv run server.py --camera 1 --no-mirror # rear camera (e.g. Surface),
                                             # shown un-mirrored since you're
                                             # pointing it away from yourself

Front vs. rear camera:
    A front-facing webcam is mirrored by default so the screen behaves like
    a mirror (raise your left hand, it appears on the left). A rear-facing
    camera (e.g. a Surface's back camera, used to look at notes on a table
    or wall in front of you while watching the screen) should NOT be
    mirrored -- pass --no-mirror. Not sure which index is which? Run
    tune.py --camera N for each index to preview it before committing.
"""

import cv2
import numpy as np
import asyncio
import websockets
import json
import threading
import time
import base64
import argparse

# ── Config ────────────────────────────────────────────────────────────────────
CAMERA_INDEX      = 0     # overridden by --camera
MIRROR            = True  # overridden by --no-mirror (use for rear cameras)
WEBSOCKET_HOST    = "localhost"
WEBSOCKET_PORT    = 8765
DETECTION_FPS     = 15
CAPTURE_WIDTH     = 1280  # must match W in index.html
CAPTURE_HEIGHT    = 720   # must match H in index.html
JPEG_QUALITY      = 70    # lower = less websocket bandwidth, blockier image

# Orange sticky-note HSV ranges (OpenCV: H 0-180, S/V 0-255).
# Orange sits close to skin tone in hue, so S/V minimums are kept fairly
# high to reject skin (which is usually less saturated under normal indoor
# light) -- if real notes aren't detected, lower these with tune.py; if your
# hand/face gets picked up as a "note", raise them.
ORANGE_LOWER = np.array([5,  130, 120])
ORANGE_UPPER = np.array([22, 255, 255])

MIN_CONTOUR_AREA = 800     # px^2 -- ignore small noise
MAX_CONTOUR_AREA = 60_000  # px^2 -- ignore huge blobs (e.g. a whole orange shirt)
MIN_ASPECT_RATIO = 0.4     # long/short side ratio bounds -- a post-it is
MAX_ASPECT_RATIO = 2.5     # roughly square, an arm or sleeve is not

DEBUG_MODE = False

# ── Shared state (GIL-safe for simple value replacement) ──────────────────────
detected_notes: list[dict] = []
latest_frame_b64: str | None = None


# ── Detection ─────────────────────────────────────────────────────────────────

def detect_notes(frame: np.ndarray) -> list[dict]:
    """Return a list of dicts {x, y, width, height, angle} in frame-pixel coords."""
    hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, ORANGE_LOWER, ORANGE_UPPER)

    kernel = np.ones((7, 7), np.uint8)
    mask   = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask   = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    notes = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if not (MIN_CONTOUR_AREA < area < MAX_CONTOUR_AREA):
            continue

        rect              = cv2.minAreaRect(cnt)
        center, (w, h), _ = rect
        cx, cy            = center
        rw, rh            = max(w, h), min(w, h)
        angle             = rect[2]

        if rh == 0 or not (MIN_ASPECT_RATIO < rw / rh < MAX_ASPECT_RATIO):
            continue

        notes.append({
            "x":      float(cx),
            "y":      float(cy),
            "width":  float(rw),
            "height": float(rh),
            "angle":  float(angle),
        })

    return notes


# ── Camera loop (runs in background thread) ───────────────────────────────────

def camera_loop() -> None:
    global detected_notes, latest_frame_b64

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(f"[camera] ERROR: could not open camera {CAMERA_INDEX}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAPTURE_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)

    interval = 1.0 / DETECTION_FPS
    print(f"[camera] Capturing at {DETECTION_FPS} fps (camera {CAMERA_INDEX})")

    show_debug = DEBUG_MODE
    if show_debug:
        cv2.namedWindow("Debug", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Debug", 960, 540)
        print("[camera] Debug window open - press Q to close it")

    while True:
        t0 = time.monotonic()
        ret, frame = cap.read()
        if ret:
            if MIRROR:
                # Mirror horizontally so the screen behaves like a mirror
                # (raise your left hand, it appears on the left). Only makes
                # sense for a front/selfie camera -- rear cameras run with
                # MIRROR=False so the image matches what's really in front
                # of the device.
                frame = cv2.flip(frame, 1)

            detected_notes = detect_notes(frame)

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ok:
                latest_frame_b64 = base64.b64encode(buf).decode("ascii")

            if show_debug:
                hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                mask = cv2.inRange(hsv, ORANGE_LOWER, ORANGE_UPPER)
                debug = frame.copy()
                debug[mask > 0] = (255, 255, 0)  # highlight detected mask in cyan
                for note in detected_notes:
                    cx, cy = int(note["x"]), int(note["y"])
                    cv2.circle(debug, (cx, cy), 8, (0, 255, 0), -1)
                cv2.putText(debug, f"notes: {len(detected_notes)}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                cv2.imshow("Debug", debug)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    show_debug = False
                    cv2.destroyAllWindows()

        elapsed = time.monotonic() - t0
        time.sleep(max(0.0, interval - elapsed))

    cap.release()


# ── WebSocket handler ─────────────────────────────────────────────────────────

async def ws_handler(websocket) -> None:
    addr = websocket.remote_address
    print(f"[ws] Browser connected: {addr}")
    try:
        while True:
            payload = {"notes": detected_notes}
            if latest_frame_b64 is not None:
                payload["frame"] = f"data:image/jpeg;base64,{latest_frame_b64}"
            await websocket.send(json.dumps(payload))
            await asyncio.sleep(1.0 / DETECTION_FPS)
    except websockets.exceptions.ConnectionClosed:
        print(f"[ws] Browser disconnected: {addr}")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=0,
                        help="Camera index (default 0; try tune.py to find the right one)")
    parser.add_argument("--no-mirror", action="store_true",
                        help="Don't mirror the image -- use for a rear-facing camera")
    parser.add_argument("--debug", action="store_true",
                        help="Show live camera window with detection overlay")
    args = parser.parse_args()
    global CAMERA_INDEX, MIRROR, DEBUG_MODE
    CAMERA_INDEX = args.camera
    MIRROR       = not args.no_mirror
    DEBUG_MODE   = args.debug

    cam_thread = threading.Thread(target=camera_loop, daemon=True)
    cam_thread.start()

    print(f"[ws] Listening on ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
    print("[ws] Open index.html in your browser on this laptop.")

    async with websockets.serve(ws_handler, WEBSOCKET_HOST, WEBSOCKET_PORT,
                                 max_size=4 * 1024 * 1024):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
