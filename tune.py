#!/usr/bin/env python3
"""
Detection tuning tool - run this standalone to check if orange notes are
detected, and to find the right --camera index (e.g. front vs. rear camera
on a 2-in-1 like a Surface).
Shows live camera feed with cyan highlight where orange is detected.
Press Q to quit.

Usage:
    uv run tune.py                        # auto-picks last-found camera, mirrored
    uv run tune.py --camera 1              # try a specific index (e.g. rear camera)
    uv run tune.py --camera 1 --no-mirror  # preview a rear camera unmirrored,
                                            # matching how server.py will show it
"""

import cv2
import numpy as np
import argparse
import sys

# ── These must match server.py ─────────────────────────────────────────────────
ORANGE_LOWER = np.array([5,  130, 120])
ORANGE_UPPER = np.array([22, 255, 255])
MIN_CONTOUR_AREA = 800
MAX_CONTOUR_AREA = 60_000
MIN_ASPECT_RATIO = 0.4
MAX_ASPECT_RATIO = 2.5


def list_cameras(max_test: int = 6) -> list[int]:
    found = []
    for i in range(max_test):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            found.append(i)
            cap.release()
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=None,
                        help="Camera index to preview (omit to auto-pick)")
    parser.add_argument("--no-mirror", action="store_true",
                        help="Don't mirror the preview -- use for a rear-facing camera")
    args = parser.parse_args()

    if args.camera is not None:
        camera_index = args.camera
    else:
        indices = list_cameras()
        if not indices:
            print("No cameras found.")
            sys.exit(1)
        camera_index = indices[-1]  # last = most recently added, often external/rear
        print(f"Using camera {camera_index}  (all found: {indices})")
        print("Not the right one? Re-run with --camera N to try another index.")

    mirror = not args.no_mirror

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"ERROR: could not open camera {camera_index}")
        sys.exit(1)

    cv2.namedWindow("Detection Tuning", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Detection Tuning", 960, 540)
    print("Hold an orange sticky note in front of the camera.")
    print("It should turn CYAN when detected. Press Q to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        if mirror:
            frame = cv2.flip(frame, 1)

        hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, ORANGE_LOWER, ORANGE_UPPER)

        kernel = np.ones((7, 7), np.uint8)
        mask   = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask   = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        display = frame.copy()
        display[mask > 0] = (255, 255, 0)  # cyan highlight

        count = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if not (MIN_CONTOUR_AREA < area < MAX_CONTOUR_AREA):
                continue
            rect = cv2.minAreaRect(cnt)
            (_, _), (w, h), _ = rect
            rw, rh = max(w, h), min(w, h)
            if rh == 0 or not (MIN_ASPECT_RATIO < rw / rh < MAX_ASPECT_RATIO):
                continue
            count += 1
            box = cv2.boxPoints(rect).astype(np.int32)
            cv2.drawContours(display, [box], 0, (0, 255, 0), 2)

        status = f"cam {camera_index} ({'mirrored' if mirror else 'unmirrored'}) - Detected: {count} note(s)"
        cv2.rectangle(display, (0, 0), (620, 45), (0, 0, 0), -1)
        cv2.putText(display, status, (8, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (0, 255, 0) if count else (0, 80, 255), 2)

        cv2.imshow("Detection Tuning", display)
        if cv2.waitKey(30) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
