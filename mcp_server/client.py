"""HTTP client for Transformation Rules REST APIs."""

from __future__ import annotations

from typing import Any

import httpx


class TransformationApiError(Exception):
    """API returned an error response."""

    def __init__(self, status_code: int, message: str, body: Any | None = None):
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {message}")


class TransformationApiClient:
    def __init__(self, base_url: str, *, timeout_seconds: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds

    def _url(self, path: str) -> str:
        path = path if path.startswith("/") else f"/{path}"
        return f"{self.base_url}{path}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method,
                self._url(path),
                params=params,
                json=json_body,
            )
        if response.status_code >= 400:
            try:
                body = response.json()
                detail = body.get("detail", body)
                if isinstance(detail, dict):
                    message = detail.get("message") or detail.get("error") or str(detail)
                else:
                    message = str(detail)
            except Exception:
                message = response.text or response.reason_phrase
                body = None
            raise TransformationApiError(response.status_code, message, body)
        if response.status_code == 204:
            return None
        return response.json()

    async def list_rules(
        self,
        *,
        status: str = "active",
        tag: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"status": status}
        if tag:
            params["tag"] = tag
        return await self._request("GET", "/rules", params=params)

    async def get_rule(self, rule_code: str) -> dict[str, Any]:
        code = (rule_code or "").strip()
        return await self._request("GET", f"/rules/{code}")

    async def execute_selected(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/rules/execute-selected", json_body=payload)

    async def execute_rule(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/rules/execute", json_body=payload)

    async def list_logs(
        self,
        *,
        limit: int = 20,
        status: str | None = None,
        rule_code: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if rule_code:
            params["rule_code"] = rule_code
        return await self._request("GET", "/rules/logs", params=params)
