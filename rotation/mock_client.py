"""A fake CoinGeckoClient that returns data shaped exactly like the real API
(verified field-by-field against docs.coingecko.com — see docs/api-verification.md),
so `python run.py demo` can exercise the full pipeline with no key and no network.

Each call also nudges an internal clock forward and drifts prices with a fixed
seed, so running `demo` repeatedly builds up a multi-point history, just like
hourly GitHub Actions runs would.
"""
from __future__ import annotations

import random
from pathlib import Path

STATE_FILE = Path(".demo_state") / "clock"  # not under docs/data: this is a dev-only fixture, never published

SECTOR_BIAS = {
    # Deliberately gives each sector a different story so the dashboard and
    # the quadrant map have something interesting to show in the demo.
    "ai": 0.8, "defi": 0.1, "rwa": 1.3, "meme": -0.9,
    "l1": 0.2, "l2": -0.2, "gaming": -0.1, "depin": 0.4,
}


def _rng_for_tick(tick: int, salt: str) -> random.Random:
    return random.Random(hash((tick, salt)) & 0xFFFFFFFF)


def _read_tick() -> int:
    if STATE_FILE.exists():
        try:
            return int(STATE_FILE.read_text().strip())
        except ValueError:
            return 0
    return 0


def _write_tick(n: int) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(str(n))


class MockCoinGeckoClient:
    """Drop-in replacement for CoinGeckoClient used only by `run.py demo`."""

    environment = "demo-mock"
    has_key = True
    is_paid = False

    def __init__(self, cfg: dict, tick: int | None = None):
        self.cfg = cfg
        self.calls = 0
        self.tick = _read_tick() if tick is None else tick
        _write_tick(self.tick + 1)

    def get(self, path: str, params: dict | None = None):
        self.calls += 1
        params = params or {}
        if path == "/coins/markets":
            if "ids" in params:
                return self._benchmarks(params["ids"].split(","))
            return self._sector_markets(params.get("category", "unknown"), params.get("per_page", 40))
        if path == "/coins/list":
            return self._coins_list()
        if path.endswith("/pools") and "/onchain/networks/" in path:
            return self._pools(path)
        if path.endswith("/holders_chart"):
            return self._holders_chart(path)
        raise AssertionError(f"MockCoinGeckoClient: unhandled path {path}")

    # -- fixtures, shaped like verified real responses ---------------------

    def _benchmarks(self, ids: list[str]) -> list[dict]:
        out = []
        for cid in ids:
            r = _rng_for_tick(self.tick, cid)
            base = 0.0
            out.append(_market_row(cid, cid[:3].upper(), cid.title(),
                                    price=r.uniform(1, 70000),
                                    r24h=base + r.uniform(-2, 2),
                                    r7d=base + r.uniform(-6, 6),
                                    r30d=base + r.uniform(-15, 15),
                                    mcap=r.uniform(5e10, 1.6e12),
                                    vol=r.uniform(1e9, 3e10)))
        return out

    def _sector_markets(self, category: str, per_page: int) -> list[dict]:
        bias = SECTOR_BIAS.get(_key_for_category(category, self.cfg), 0.0)
        out = []
        n = min(per_page, 18)
        damped_tick = min(self.tick, 8)  # keep the simulated trend from running away over many demo ticks
        for i in range(n):
            r = _rng_for_tick(self.tick, f"{category}:{i}")
            drift = bias * (1 + 0.12 * damped_tick) + r.uniform(-1.5, 1.5)
            out.append(_market_row(
                f"{category}-token-{i}", f"T{i}{category[:2].upper()}", f"{category.title()} Token {i}",
                price=r.uniform(0.001, 500),
                r24h=drift * 0.5 + r.uniform(-2, 2),
                r7d=drift + r.uniform(-4, 4),
                r30d=drift * 1.8 + r.uniform(-10, 10),
                mcap=r.uniform(2.5e7, 8e9),
                vol=r.uniform(6e5, 4e8),
            ))
        return out

    def _coins_list(self) -> list[dict]:
        out = []
        networks = ["ethereum", "base", "binance-smart-chain", "solana", "arbitrum-one"]
        for sec in self.cfg["sectors"]:
            for i in range(18):  # cover every token _sector_markets can produce, like the real /coins/list does
                r = _rng_for_tick(0, f"{sec['category']}:{i}:platform")
                net = networks[i % len(networks)]
                addr = ("0x" + "".join(r.choice("0123456789abcdef") for _ in range(40))
                        if net != "solana" else
                        "".join(r.choice("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
                                for _ in range(32)))
                out.append({"id": f"{sec['category']}-token-{i}", "symbol": f"t{i}", "name": f"Token {i}",
                            "platforms": {net: addr}})
        return out

    def _pools(self, path: str) -> dict:
        r = _rng_for_tick(self.tick, path)
        buys, sells = r.randint(50, 900), r.randint(50, 900)
        return {"data": [{
            "id": "mock_pool_1", "type": "pool",
            "attributes": {
                "base_token_price_usd": str(r.uniform(0.01, 50)),
                "name": "MOCK / USDC",
                "pool_created_at": "2026-01-01T00:00:00Z",
                "fdv_usd": str(r.uniform(1e6, 1e9)),
                "market_cap_usd": str(r.uniform(1e6, 1e9)),
                "price_change_percentage": {"h24": str(r.uniform(-10, 10))},
                "transactions": {"h24": {"buys": buys, "sells": sells,
                                          "buyers": int(buys * 0.7), "sellers": int(sells * 0.7)}},
                "volume_usd": {"h24": str(r.uniform(1e4, 5e6))},
                "reserve_in_usd": str(r.uniform(1e5, 5e7)),
            },
            "relationships": {"base_token": {"data": {"id": "mock_base", "type": "token"}},
                               "quote_token": {"data": {"id": "mock_quote", "type": "token"}}},
        }]}

    def _holders_chart(self, path: str) -> dict:
        r = _rng_for_tick(self.tick, path)
        start = r.randint(2000, 50000)
        growth = r.uniform(-0.05, 0.08)
        end = int(start * (1 + growth))
        return {"data": {"id": "mock", "type": "token_holders_snapshot",
                          "attributes": {"token_holders_list": [
                              ["2026-01-01T00:00:00.000Z", start],
                              ["2026-01-07T00:00:00.000Z", end],
                          ]}},
                "meta": {"token": {"name": "Mock", "symbol": "mock", "coingecko_coin_id": None, "address": "0x0"}}}


def _key_for_category(category: str, cfg: dict) -> str:
    for sec in cfg["sectors"]:
        if sec["category"] == category:
            return sec["key"]
    return category


def _market_row(cid, symbol, name, price, r24h, r7d, r30d, mcap, vol) -> dict:
    return {
        "id": cid, "symbol": symbol, "name": name,
        "image": "", "current_price": price, "market_cap": mcap, "market_cap_rank": None,
        "fully_diluted_valuation": mcap, "total_volume": vol,
        "high_24h": price * 1.02, "low_24h": price * 0.98,
        "price_change_24h": price * r24h / 100, "price_change_percentage_24h": r24h,
        "market_cap_change_24h": mcap * r24h / 100, "market_cap_change_percentage_24h": r24h,
        "circulating_supply": None, "total_supply": None, "max_supply": None,
        "ath": price * 2, "ath_change_percentage": -50.0, "ath_date": "2025-01-01T00:00:00.000Z",
        "atl": price * 0.1, "atl_change_percentage": 900.0, "atl_date": "2023-01-01T00:00:00.000Z",
        "roi": None, "last_updated": "2026-01-01T00:00:00.000Z",
        "price_change_percentage_24h_in_currency": r24h,
        "price_change_percentage_7d_in_currency": r7d,
        "price_change_percentage_30d_in_currency": r30d,
    }
