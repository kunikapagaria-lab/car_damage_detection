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


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _vertical_gradient(w: int, h: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        draw.line([(0, y), (w, y)], fill=_lerp(top, bottom, y / h))
    return img


def make_plate_image(plate: str, body_color: tuple[int, int, int], variant: int) -> bytes:
    """Render a stylized car-silhouette 'vehicle photo' — same look as the
    app's own SamplePresets.tsx demo gallery, ported to PIL so seeded scans
    show an actual car rather than an abstract placeholder. The dummy
    predictor just hashes pixel bytes for its random seed, so content only
    needs to vary enough between scans to produce different detections."""
    w, h = 640, 400
    img = _vertical_gradient(w, h, (30, 41, 59), (2, 6, 23))
    draw = ImageDraw.Draw(img, "RGBA")
    rng = random.Random(f"{plate}-{variant}")

    # Slight per-vehicle/per-scan color jitter so repeated scans still hash
    # to different bytes (needed for the dummy predictor's varied output).
    jitter = lambda c: max(20, min(235, c + rng.randint(-12, 12)))  # noqa: E731
    shade = tuple(jitter(c) for c in body_color)
    dark = tuple(max(15, c - 60) for c in shade)

    # Car body silhouette (front-3/4 view), matching SamplePresets.tsx
    body = [
        (100, 260), (120, 200), (240, 150), (360, 140), (460, 180),
        (540, 220), (530, 280), (450, 280), (210, 280), (130, 280),
    ]
    draw.polygon(body, fill=shade, outline=(148, 163, 184))

    # Windows
    windows = [(245, 155), (355, 145), (445, 185), (350, 190), (250, 190)]
    draw.polygon(windows, fill=(148, 163, 184, 90), outline=(203, 213, 225))

    # Wheels
    for cx in (170, 490):
        cy = 280
        draw.ellipse([cx - 38, cy - 38, cx + 38, cy + 38], fill=(15, 23, 42), outline=(100, 116, 139), width=4)
        draw.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], fill=(148, 163, 184))

    # Headlight
    draw.rectangle([102, 210, 122, 225], fill=(254, 240, 138))

    # Body shading line
    draw.line([body[1], body[8]], fill=dark + (140,), width=2)

    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    draw.rectangle([20, h - 44, 220, h - 12], fill=(255, 255, 255))
    draw.text((30, h - 40), plate, fill=(15, 23, 42), font=font)
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
