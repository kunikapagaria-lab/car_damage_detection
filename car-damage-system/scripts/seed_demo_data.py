"""Populate the demo with realistic-looking vehicles, scan history, and alerts.

Runs against the live backend (:8010) and inference (:8001) services using
the exact same HTTP endpoints the frontend uses — no direct DB writes — so it
also doubles as a smoke test of the upload -> inspect -> ingest -> diff ->
webhook pipeline.

Usage (with both services already running):
    python scripts/seed_demo_data.py

Note: not idempotent — re-running adds more scan history to the same
vehicles (harmless, gives a richer timeline) but also registers another
webhook row each time, which will duplicate alert entries per scan. Fine for
occasional re-seeding; if you run it often, prune extra rows from
webhook_registrations.
"""

from __future__ import annotations

import io
import random
import sys
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

BACKEND_URL = "http://localhost:8010"
INFERENCE_URL = "http://localhost:8001"

ANGLES = ["front", "rear", "left", "right"]

# scan_count > 1 gives each vehicle a damage timeline so the diff viewer and
# alerts feed have something to show.
VEHICLES = [
    ("MH12AB1234", 3),
    ("DL08CAF9922", 2),
    ("KA05MN4567", 3),
    ("TN09XY7788", 1),
    ("GJ01RT3311", 2),
    ("UP16BQ6541", 4),
    ("RJ14CD8890", 1),
    ("WB20EF2245", 2),
]

# Real photos (Pexels, free license — see sample_photos/SOURCE.md), one set
# per angle. Each vehicle is pinned to one photo per angle (by index) so its
# own scan history stays visually consistent while different vehicles in
# the fleet show different cars.
PHOTOS_DIR = Path(__file__).parent / "sample_photos"
PHOTO_SETS = {
    "front": ["front_1.jpg", "front_2.jpg", "front_3.jpg", "front_4.jpg"],
    "rear": ["rear_1.jpg", "rear_2.jpg"],
    "left": ["side_1.jpg", "side_2.jpg"],
    "right": ["side_1.jpg", "side_2.jpg"],
}


def make_plate_image(plate: str, vehicle_index: int, angle: str, variant: int) -> bytes:
    """Load a real vehicle photo for this angle, overlay the plate number,
    and add a light per-scan pixel jitter — the dummy predictor hashes
    pixel bytes for its random seed, so repeated scans of the same base
    photo need slightly different bytes to produce varied detections."""
    photos = PHOTO_SETS[angle]
    photo_path = PHOTOS_DIR / photos[vehicle_index % len(photos)]
    img = Image.open(photo_path).convert("RGB")

    rng = random.Random(f"{plate}-{angle}-{variant}")
    draw = ImageDraw.Draw(img)
    for _ in range(15):
        x, y = rng.randint(0, img.width - 1), rng.randint(0, img.height - 1)
        draw.point((x, y), fill=(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)))

    try:
        font = ImageFont.truetype("arial.ttf", max(20, img.width // 24))
    except OSError:
        font = ImageFont.load_default()
    pad = 10
    label_w, label_h = int(img.width * 0.32), int(img.height * 0.08)
    x0, y0 = img.width - label_w - pad, img.height - label_h - pad
    draw.rectangle([x0, y0, x0 + label_w, y0 + label_h], fill=(255, 255, 255))
    draw.text((x0 + pad, y0 + pad // 2), plate, fill=(15, 23, 42), font=font)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def inspect_frame(client: httpx.Client, image_bytes: bytes, camera_id: str) -> dict:
    resp = client.post(
        f"{INFERENCE_URL}/api/v1/inspect/frame",
        files={"image": (f"{camera_id}.jpg", image_bytes, "image/jpeg")},
        data={"camera_id": camera_id, "vehicle_id": ""},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def submit_scan(client: httpx.Client, plate: str, angle: str, image_bytes: bytes, inspect_result: dict) -> dict:
    import json

    meta = {
        "plate_number": plate,
        "location_tag": "Gate 1",
        "inspection_results": [{
            "camera_id": inspect_result["camera_id"],
            "angle": angle,
            "damages": inspect_result["damages"],
            "plate_result": inspect_result["plate_result"],
            "inference_time_ms": inspect_result["inference_time_ms"],
            "captured_at": inspect_result["captured_at"],
        }],
    }
    resp = client.post(
        f"{BACKEND_URL}/api/v1/scans",
        data={"metadata": json.dumps(meta)},
        files={"images": (f"{inspect_result['camera_id']}.jpg", image_bytes, "image/jpeg")},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if not body.get("success"):
        raise RuntimeError(f"scan ingest failed for {plate}: {body}")
    return body["data"]


def register_demo_webhook(client: httpx.Client) -> None:
    """Register the local webhook-echo container (see docker-compose.yml) so
    new-damage events actually fire and populate the Alerts page (otherwise
    no webhook subscriber = no alerts). Resolved via the docker-compose
    network's internal DNS from inside the api container — no external
    network calls involved."""
    resp = client.post(
        f"{BACKEND_URL}/api/v1/webhooks/register",
        json={"url": "http://webhook-echo:8080/post", "secret": "demo-webhook-secret"},
        timeout=10,
    )
    if resp.status_code == 201:
        print("  registered demo webhook -> http://webhook-echo:8080/post")
    else:
        print(f"  webhook registration skipped ({resp.status_code}): {resp.text[:200]}")


def wait_for_services(client: httpx.Client) -> None:
    for name, url in [("backend", f"{BACKEND_URL}/health"), ("inference", f"{INFERENCE_URL}/health")]:
        for attempt in range(10):
            try:
                if client.get(url, timeout=3).status_code == 200:
                    print(f"  {name} is up")
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        else:
            sys.exit(f"ERROR: {name} not reachable at {url} — start the services first.")


def main() -> None:
    print("Checking services...")
    with httpx.Client() as client:
        wait_for_services(client)
        register_demo_webhook(client)

        total_scans = 0
        for vehicle_index, (plate, scan_count) in enumerate(VEHICLES):
            print(f"\nSeeding {plate} ({scan_count} scan(s))...")
            for i in range(scan_count):
                angle = ANGLES[i % len(ANGLES)]
                image_bytes = make_plate_image(plate, vehicle_index, angle, variant=i)
                inspect_result = inspect_frame(client, image_bytes, camera_id=f"cam_{angle}")
                scan = submit_scan(client, plate, angle, image_bytes, inspect_result)
                n_damages = len(inspect_result["damages"])
                print(f"  scan {i + 1}/{scan_count}: {n_damages} damage(s) detected -> scan {scan['id']}")
                total_scans += 1
                time.sleep(0.3)

        print(f"\nDone. Seeded {len(VEHICLES)} vehicles / {total_scans} scans.")
        print("Open the dashboard to see vehicles, scan history, diffs, and alerts populated.")


if __name__ == "__main__":
    main()
