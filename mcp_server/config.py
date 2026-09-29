"""MCP server configuration (env-based; no DB access from MCP)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class McpSettings:
    api_base_url: str
    request_timeout_seconds: float


def get_settings() -> McpSettings:
    base = os.getenv("TRANSFORMATION_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    timeout = float(os.getenv("TRANSFORMATION_API_TIMEOUT", "60"))
    return McpSettings(api_base_url=base, request_timeout_seconds=timeout)
