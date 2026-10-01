"""Minimal CoinGecko API client (Python standard library only).

The API key is read from the environment / .env file and is only ever sent
in a request header. It is never printed, logged or written to disk.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URLS = {
    "pro": "https://pro-api.coingecko.com/api/v3",
    "demo": "https://api.coingecko.com/api/v3",
}
HEADER_NAMES = {
    "pro": "x-cg-pro-api-key",
    "demo": "x-cg-demo-api-key",
}


class ApiError(Exception):
    """Raised when a request fails after retries. Never contains the key."""

    def __init__(self, path: str, status: int | None, message: str):
        self.path = path
        self.status = status
        super().__init__(f"{path} -> {status}: {message}")


def load_dotenv(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines from a .env file into os.environ (if not already set)."""
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class CoinGeckoClient:
    def __init__(self, api_key: str | None = None, environment: str | None = None,
                 max_retries: int = 4, timeout: int = 30, min_interval: float = 0.15):
        self.api_key = api_key if api_key is not None else os.environ.get("COINGECKO_API_KEY", "")
        env = (environment or os.environ.get("COINGECKO_ENVIRONMENT", "pro")).strip().lower()
        if env not in BASE_URLS:
            raise ValueError("COINGECKO_ENVIRONMENT must be 'pro' or 'demo'")
        self.environment = env
        self.base_url = BASE_URLS[env]
        self.max_retries = max_retries
        self.timeout = timeout
        self.min_interval = min_interval
        self.calls = 0
        self._last_call = 0.0

    @property
    def has_key(self) -> bool:
        return bool(self.api_key and self.api_key.strip() and "your" not in self.api_key.lower())

    @property
    def is_paid(self) -> bool:
        return self.environment == "pro"

    def get(self, path: str, params: dict | None = None):
        if not self.has_key:
            raise ApiError(path, None, "COINGECKO_API_KEY is missing. Add it to .env (local) or GitHub Secrets.")
        query = ""
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            for k, v in clean.items():
                if isinstance(v, bool):
                    clean[k] = "true" if v else "false"
            query = "?" + urllib.parse.urlencode(clean)
        url = f"{self.base_url}{path}{query}"
        headers = {
            "accept": "application/json",
            "user-agent": "market-rotation-tracker/1.0",
            HEADER_NAMES[self.environment]: self.api_key,
        }
        last_err = "unknown error"
        last_status = None
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    self.calls += 1
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                self.calls += 1
                last_status = e.code
                last_err = _safe_body(e)
                if e.code in (401, 403):
                    hint = ("Check that COINGECKO_ENVIRONMENT matches your key: a paid (Analyst) key uses 'pro', "
                            "a free Demo key uses 'demo'.")
                    raise ApiError(path, e.code, f"{last_err} | {hint}") from None
                if e.code == 404 or e.code == 400 or e.code == 422:
                    raise ApiError(path, e.code, last_err) from None
                retry_after = e.headers.get("Retry-After") if e.headers else None
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                last_err = type(e).__name__
                delay = 2 ** attempt
            if attempt < self.max_retries:
                time.sleep(min(delay, 30))
        raise ApiError(path, last_status, last_err)


def _safe_body(err: urllib.error.HTTPError) -> str:
    try:
        body = err.read().decode("utf-8", errors="replace")[:300]
    except Exception:
        body = ""
    return body or err.reason or "HTTP error"
