"""Low-level HTTP client wrapper with auth, retry, and error handling."""

from __future__ import annotations

import time
from typing import Any

import httpx

from .exceptions import (
    DraftAPIError,
    DraftConflictError,
    DraftConnectionError,
    DraftNotFoundError,
    DraftValidationError,
)

_ERROR_MAP = {
    404: DraftNotFoundError,
    409: DraftConflictError,
    422: DraftValidationError,
}

_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0


class HttpClient:
    """Thin httpx wrapper with auth, retry on 429, and structured errors."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = 600.0,
    ):
        headers: dict[str, str] = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    # -- public verbs --------------------------------------------------------

    def get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params=params or None)

    def post(self, path: str, json: Any = None) -> Any:
        return self._request("POST", path, json=json)

    def patch(self, path: str, json: Any = None) -> Any:
        return self._request("PATCH", path, json=json)

    def put(self, path: str, json: Any = None) -> Any:
        return self._request("PUT", path, json=json)

    def delete(self, path: str) -> None:
        self._request("DELETE", path)

    def get_text(self, path: str) -> str:
        """GET that returns plain text instead of JSON."""
        resp = self._raw("GET", path)
        return resp.text

    # -- internals -----------------------------------------------------------

    def _raw(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.ConnectError as exc:
            raise DraftConnectionError(str(exc)) from exc
        self._raise_for_status(resp)
        return resp

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._client.request(method, path, **kwargs)
            except httpx.ConnectError as exc:
                raise DraftConnectionError(str(exc)) from exc

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", _BACKOFF_BASE * (2**attempt)))
                time.sleep(retry_after)
                continue

            self._raise_for_status(resp)

            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()

        # exhausted retries on 429
        raise DraftAPIError(429, "Rate limited after retries")

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.is_success:
            return

        detail = ""
        error_type = None
        try:
            body = resp.json()
            detail = body.get("detail", body.get("message", str(body)))
            error_type = body.get("error_type")
        except Exception:
            detail = resp.text or f"HTTP {resp.status_code}"

        exc_cls = _ERROR_MAP.get(resp.status_code, DraftAPIError)
        if exc_cls is DraftAPIError:
            raise DraftAPIError(resp.status_code, detail, error_type)
        raise exc_cls(detail)
