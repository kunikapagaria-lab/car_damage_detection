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

import httpx
from PIL import Image, ImageDraw, ImageFont

BACKEND_URL = "http://localhost:8010"
INFERENCE_URL = "http://localhost:8001"

ANGLES = ["front", "rear", "left", "right"]

# (plate, color, scan_count) — scan_count > 1 gives each vehicle a damage
# timeline so the diff viewer and alerts feed have something to show.
VEHICLES = [
    ("MH12AB1234", (200, 60, 60), 3),
    ("DL08CAF9922", (60, 130, 200), 2),
    ("KA05MN4567", (90, 180, 90), 3),
    ("TN09XY7788", (210, 170, 40), 1),
    ("GJ01RT3311", (150, 90, 200), 2),
    ("UP16BQ6541", (80, 80, 80), 4),
    ("RJ14CD8890", (220, 120, 60), 1),
    ("WB20EF2245", (40, 160, 160), 2),
]


def make_plate_image(plate: str, color: tuple[int, int, int], variant: int) -> bytes:
    """Render a simple placeholder 'vehicle photo' — the dummy predictor only
    hashes pixel bytes for its random seed, so content just needs to vary."""
    img = Image.new("RGB", (960, 640), color=color)
    draw = ImageDraw.Draw(img)
    rng = random.Random(f"{plate}-{variant}")
    for _ in range(40):
        x, y = rng.randint(0, 960), rng.randint(0, 640)
        r = rng.randint(5, 30)
        shade = tuple(max(0, min(255, c + rng.randint(-25, 25))) for c in color)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=shade)
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    draw.rectangle([260, 560, 700, 620], fill=(255, 255, 255))
    draw.text((280, 565), plate, fill=(0, 0, 0), font=font)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
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
        for plate, color, scan_count in VEHICLES:
            print(f"\nSeeding {plate} ({scan_count} scan(s))...")
            for i in range(scan_count):
                angle = ANGLES[i % len(ANGLES)]
                image_bytes = make_plate_image(plate, color, variant=i)
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
