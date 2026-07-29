from __future__ import annotations

import json
import random
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class NetworkError(RuntimeError):
    pass


def request_bytes(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 45.0,
    retries: int = 2,
) -> bytes:
    request_headers = {
        "User-Agent": "paper-research-agent/0.1 (+https://github.com/)",
        **(headers or {}),
    }
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = Request(
                url=url,
                data=body,
                headers=request_headers,
                method=method,
            )
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")[:1000]
            last_error = NetworkError(f"HTTP {exc.code} for {url}: {details}")
            if exc.code < 500 and exc.code != 429:
                break
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
        if attempt < retries:
            time.sleep((2**attempt) + random.random() * 0.2)
    raise NetworkError(f"Request failed for {url}: {last_error}") from last_error


def request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 45.0,
    retries: int = 2,
) -> dict[str, Any]:
    body = None
    request_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    raw = request_bytes(
        url,
        method=method,
        headers=request_headers,
        body=body,
        timeout=timeout,
        retries=retries,
    )
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NetworkError(f"Invalid JSON returned by {url}") from exc
    if not isinstance(value, dict):
        raise NetworkError(f"Expected a JSON object from {url}")
    return value
