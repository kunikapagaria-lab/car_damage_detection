"""Shared pytest fixtures and event loop configuration."""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop shared across the entire test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()
