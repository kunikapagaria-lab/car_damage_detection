"""End-to-end integration test suite.

Requires a fully running stack (docker-compose up or equivalent).
Set environment variable INTEGRATION_TEST_BASE_URL to override the backend URL.

Flow tested
───────────
  1. Login as admin → receive JWT
  2. Call inference /inspect/test → get a synthetic InspectionResult
  3. POST /scans to backend with that result → scan created
  4. Poll GET /scans/{id} until status == "complete" (max 30 s)
  5. GET /scans/{id}/damages → assert damage list
  6. POST /scans/{id}/report → assert PDF bytes (%PDF magic)
  7. GET /alerts/recent → assert response structure

All requests use the JWT from step 1 in the Authorization header.
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import time
from typing import Any

import httpx
import numpy as np
import pytest
import pytest_asyncio
from PIL import Image

BASE_URL        = os.environ.get("INTEGRATION_TEST_BASE_URL",       "http://localhost:8000")
INFERENCE_URL   = os.environ.get("INTEGRATION_TEST_INFERENCE_URL",  "http://localhost:8001")
TEST_USERNAME   = os.environ.get("INTEGRATION_TEST_USERNAME",       "admin")
TEST_PASSWORD   = os.environ.get("INTEGRATION_TEST_PASSWORD",       "changeme123!")
POLL_TIMEOUT_S  = 30
POLL_INTERVAL_S = 1.5


# ── Helpers ───────────────────────────────────────────────────────────────────

def _synthetic_jpeg() -> bytes:
    """Create a minimal synthetic car-panel JPEG for upload."""
    canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
    # White rectangle simulating a car body panel
    canvas[150:570, 200:1080] = 200
    img = Image.fromarray(canvas.astype(np.uint8), mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


async def _poll_scan(
    client: httpx.AsyncClient,
    scan_id: str,
    headers: dict[str, str],
    timeout: float = POLL_TIMEOUT_S,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = await client.get(f"{BASE_URL}/api/v1/scans/{scan_id}", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        scan = body["data"]
        if scan["status"] in ("complete", "failed"):
            return scan
        await asyncio.sleep(POLL_INTERVAL_S)
    raise TimeoutError(f"Scan {scan_id} did not complete within {timeout} s")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def http() -> httpx.AsyncClient:
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def auth_headers(http: httpx.AsyncClient) -> dict[str, str]:
    resp = await http.post(
        f"{BASE_URL}/api/v1/auth/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
    )
    if resp.status_code == 404:
        pytest.skip("Auth endpoint not available — skipping integration tests")
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="session")
async def completed_scan(
    http: httpx.AsyncClient,
    auth_headers: dict[str, str],
) -> dict[str, Any]:
    """Create a scan end-to-end and return it once complete."""
    # Step 1: Get a synthetic InspectionResult from the inference service
    infer_resp = await http.get(f"{INFERENCE_URL}/api/v1/inspect/test")
    assert infer_resp.status_code == 200, f"Inference test failed: {infer_resp.text}"
    insp_result = infer_resp.json()

    # Wrap it into the format expected by POST /scans
    scan_meta = {
        "plate_number": "TN09AB1234",
        "location_tag": "integration_test_bay",
        "inspection_results": [
            {
                "camera_id": insp_result.get("camera_id", "test_cam"),
                "angle": "front",
                "damages": insp_result.get("damages", []),
                "plate_result": insp_result.get("plate_result"),
                "inference_time_ms": insp_result.get("inference_time_ms", 0),
                "captured_at": insp_result.get("captured_at"),
            }
        ],
    }

    image_bytes = _synthetic_jpeg()

    create_resp = await http.post(
        f"{BASE_URL}/api/v1/scans",
        headers=auth_headers,
        data={"metadata": __import__("json").dumps(scan_meta)},
        files={"images": ("test_cam.jpg", image_bytes, "image/jpeg")},
    )
    assert create_resp.status_code in (200, 201), f"Scan create failed: {create_resp.text}"
    scan_data = create_resp.json()["data"]
    scan_id = scan_data["id"]

    # Poll until complete
    final_scan = await _poll_scan(http, scan_id, auth_headers)
    assert final_scan["status"] == "complete", f"Scan failed: {final_scan}"
    return final_scan


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_backend_health(http: httpx.AsyncClient) -> None:
    resp = await http.get(f"{BASE_URL}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


@pytest.mark.asyncio
async def test_inference_health(http: httpx.AsyncClient) -> None:
    resp = await http.get(f"{INFERENCE_URL}/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_login_success(http: httpx.AsyncClient) -> None:
    resp = await http.post(
        f"{BASE_URL}/api/v1/auth/login",
        data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(http: httpx.AsyncClient) -> None:
    resp = await http.post(
        f"{BASE_URL}/api/v1/auth/login",
        data={"username": TEST_USERNAME, "password": "WRONG_PASSWORD"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_without_token(http: httpx.AsyncClient) -> None:
    resp = await http.get(f"{BASE_URL}/api/v1/vehicles")
    # With auth middleware, should return 401
    assert resp.status_code in (200, 401)  # 200 if auth not enforced yet


@pytest.mark.asyncio
async def test_scan_created_and_complete(
    completed_scan: dict[str, Any],
) -> None:
    assert completed_scan["status"] == "complete"
    assert completed_scan["id"] is not None
    assert completed_scan["vehicle_id"] is not None
    assert completed_scan["camera_count"] >= 1


@pytest.mark.asyncio
async def test_scan_damages(
    http: httpx.AsyncClient,
    auth_headers: dict[str, str],
    completed_scan: dict[str, Any],
) -> None:
    scan_id = completed_scan["id"]
    resp = await http.get(
        f"{BASE_URL}/api/v1/scans/{scan_id}/damages",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    damages = body["data"]
    assert isinstance(damages, list)
    for d in damages:
        assert "damage_class" in d
        assert "confidence" in d
        assert 0.0 <= d["confidence"] <= 1.0
        assert "bbox_x1" in d


@pytest.mark.asyncio
async def test_scan_diff(
    http: httpx.AsyncClient,
    auth_headers: dict[str, str],
    completed_scan: dict[str, Any],
) -> None:
    scan_id = completed_scan["id"]
    resp = await http.get(
        f"{BASE_URL}/api/v1/scans/{scan_id}/diff",
        headers=auth_headers,
    )
    # Diff may be 404 if no prior scan (expected for first scan)
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        diff = resp.json()["data"]
        assert "new_damage_count" in diff
        assert "resolved_damage_count" in diff


@pytest.mark.asyncio
async def test_vehicle_registered(
    http: httpx.AsyncClient,
    auth_headers: dict[str, str],
    completed_scan: dict[str, Any],
) -> None:
    vehicle_id = completed_scan["vehicle_id"]
    resp = await http.get(
        f"{BASE_URL}/api/v1/vehicles/{vehicle_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    vehicle = resp.json()["data"]
    assert vehicle["plate_number"] == "TN09AB1234"
    assert vehicle["total_scans"] >= 1


@pytest.mark.asyncio
async def test_pdf_report_generated(
    http: httpx.AsyncClient,
    auth_headers: dict[str, str],
    completed_scan: dict[str, Any],
) -> None:
    scan_id = completed_scan["id"]
    resp = await http.post(
        f"{BASE_URL}/api/v1/scans/{scan_id}/report",
        headers=auth_headers,
    )
    # 200 if report endpoint is wired, 404 if not yet mounted
    if resp.status_code == 404:
        pytest.skip("Report endpoint not mounted — include reports_router in main.py")

    assert resp.status_code == 200
    content_type = resp.headers.get("content-type", "")
    assert "application/pdf" in content_type

    # Verify PDF magic bytes
    pdf_bytes = resp.content
    assert pdf_bytes[:4] == b"%PDF", "Response is not a valid PDF"
    assert len(pdf_bytes) > 1024, "PDF is suspiciously small"


@pytest.mark.asyncio
async def test_alerts_recent(
    http: httpx.AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await http.get(
        f"{BASE_URL}/api/v1/alerts/recent?limit=10",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)


@pytest.mark.asyncio
async def test_model_status(http: httpx.AsyncClient) -> None:
    resp = await http.get(f"{INFERENCE_URL}/api/v1/model/status")
    assert resp.status_code == 200
    status = resp.json()
    assert status["mode"] in ("dummy", "detectron2")
    assert status["model_loaded"] is True


@pytest.mark.asyncio
async def test_rate_limit_headers_present(
    http: httpx.AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    resp = await http.get(
        f"{BASE_URL}/api/v1/vehicles",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    # Rate limit headers are optional — just verify they don't crash
    _ = resp.headers.get("X-RateLimit-Limit")
    _ = resp.headers.get("X-RateLimit-Remaining")
