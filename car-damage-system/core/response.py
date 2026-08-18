"""Consistent JSON envelope factory for all API responses."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def ok(data: Any, meta: dict | None = None, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data,
            "error": None,
            "meta": meta or {},
        },
    )


def err(error: str, detail: str = "", status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "data": None,
            "error": error,
            "meta": {"detail": detail},
        },
    )
