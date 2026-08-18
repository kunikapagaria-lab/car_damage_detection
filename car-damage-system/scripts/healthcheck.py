"""System health-check script.

Checks every service in the stack and prints a coloured status table.
Exits with code 0 if all healthy, 1 if any service is down.

Usage
─────
    python scripts/healthcheck.py

Environment overrides
─────────────────────
    DATABASE_URL  REDIS_URL  MINIO_ENDPOINT  MINIO_ACCESS_KEY
    MINIO_SECRET_KEY  BACKEND_URL  INFERENCE_URL
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx

# ── ANSI colours ──────────────────────────────────────────────────────────────

_RST  = "\033[0m"
_BOLD = "\033[1m"
_GRN  = "\033[92m"
_RED  = "\033[91m"
_YLW  = "\033[93m"
_CYN  = "\033[96m"
_GRY  = "\033[90m"


def _ok(s: str)   -> str: return f"{_GRN}{s}{_RST}"
def _fail(s: str) -> str: return f"{_RED}{s}{_RST}"
def _warn(s: str) -> str: return f"{_YLW}{s}{_RST}"
def _bold(s: str) -> str: return f"{_BOLD}{s}{_RST}"


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    name: str
    healthy: bool
    latency_ms: float
    detail: str


# ── Individual checks ─────────────────────────────────────────────────────────

async def _check_postgres() -> CheckResult:
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/car_damage",
    ).replace("+asyncpg", "")
    t0 = time.monotonic()
    try:
        import asyncpg  # type: ignore[import]
        conn = await asyncpg.connect(url, timeout=5)
        await conn.fetchval("SELECT 1")
        await conn.close()
        ms = (time.monotonic() - t0) * 1000
        return CheckResult("PostgreSQL", True, ms, "SELECT 1 OK")
    except Exception as exc:
        ms = (time.monotonic() - t0) * 1000
        return CheckResult("PostgreSQL", False, ms, str(exc)[:80])


async def _check_redis() -> CheckResult:
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    t0 = time.monotonic()
    try:
        import redis.asyncio as aioredis  # type: ignore[import]
        r = aioredis.from_url(url, socket_connect_timeout=5)
        await r.ping()
        await r.aclose()
        ms = (time.monotonic() - t0) * 1000
        return CheckResult("Redis", True, ms, "PING → PONG")
    except Exception as exc:
        ms = (time.monotonic() - t0) * 1000
        return CheckResult("Redis", False, ms, str(exc)[:80])


async def _check_minio() -> CheckResult:
    endpoint  = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    access    = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    secret    = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
    bucket    = os.environ.get("BUCKET_FULL_IMAGES", "car-damage-full-images")
    t0 = time.monotonic()
    try:
        from aiobotocore.session import AioSession  # type: ignore[import]
        session = AioSession()
        async with session.create_client(
            "s3",
            endpoint_url=f"http://{endpoint}",
            aws_access_key_id=access,
            aws_secret_access_key=secret,
            region_name="us-east-1",
        ) as s3:
            await s3.head_bucket(Bucket=bucket)
        ms = (time.monotonic() - t0) * 1000
        return CheckResult("MinIO", True, ms, f"bucket '{bucket}' accessible")
    except Exception as exc:
        ms = (time.monotonic() - t0) * 1000
        detail = str(exc)[:80]
        if "NoSuchBucket" in detail:
            return CheckResult("MinIO", False, ms, f"bucket '{bucket}' not found")
        return CheckResult("MinIO", False, ms, detail)


async def _check_http(name: str, url: str, timeout: float = 5.0) -> CheckResult:
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
        ms = (time.monotonic() - t0) * 1000
        ok = resp.status_code < 400
        try:
            body = resp.json()
            status_str = body.get("status", str(resp.status_code))
        except Exception:
            status_str = str(resp.status_code)
        return CheckResult(name, ok, ms, f"HTTP {resp.status_code} — {status_str}")
    except Exception as exc:
        ms = (time.monotonic() - t0) * 1000
        return CheckResult(name, False, ms, str(exc)[:80])


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def run_all_checks() -> list[CheckResult]:
    backend_url   = os.environ.get("BACKEND_URL",   "http://localhost:8000")
    inference_url = os.environ.get("INFERENCE_URL", "http://localhost:8001")

    results = await asyncio.gather(
        _check_postgres(),
        _check_redis(),
        _check_minio(),
        _check_http("Backend API",       f"{backend_url}/health"),
        _check_http("Inference Service", f"{inference_url}/health"),
        _check_http("Inference /status", f"{inference_url}/api/v1/model/status"),
    )
    return list(results)


# ── Pretty printer ────────────────────────────────────────────────────────────

def _print_table(results: list[CheckResult]) -> None:
    COL_W = [28, 12, 12, 52]
    sep = f"+{'+'.join('-'*(w+2) for w in COL_W)}+"

    def row(cells: list[str]) -> str:
        parts = []
        for cell, w in zip(cells, COL_W):
            # strip ANSI for width calculation
            stripped = cell
            for code in (_RST, _BOLD, _GRN, _RED, _YLW, _CYN, _GRY):
                stripped = stripped.replace(code, "")
            padding = max(0, w - len(stripped))
            parts.append(f" {cell}{' ' * padding} ")
        return f"|{'|'.join(parts)}|"

    print()
    print(sep)
    print(row([
        _bold("Service"),
        _bold("Status"),
        _bold("Latency"),
        _bold("Detail"),
    ]))
    print(sep)

    all_ok = True
    for r in results:
        status  = _ok("✓ HEALTHY") if r.healthy else _fail("✗ DOWN")
        latency = f"{r.latency_ms:6.1f} ms"
        if not r.healthy:
            all_ok = False
        print(row([r.name, status, latency, r.detail]))

    print(sep)
    print()

    if all_ok:
        print(_ok(_bold("  All services healthy.")) + "\n")
    else:
        failed = [r.name for r in results if not r.healthy]
        print(_fail(_bold(f"  DEGRADED — {len(failed)} service(s) down: {', '.join(failed)}")) + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{_CYN}{_bold('DamageVision — System Health Check')}{_RST}")
    print(f"{_GRY}{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}{_RST}")

    results = asyncio.run(run_all_checks())
    _print_table(results)

    any_down = any(not r.healthy for r in results)
    sys.exit(1 if any_down else 0)


if __name__ == "__main__":
    main()
