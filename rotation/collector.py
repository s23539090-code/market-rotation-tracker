"""Orchestrates one collection run: pull markets per sector + benchmarks,
compute metrics, optionally layer onchain flow, score sectors, detect alerts,
and return a snapshot dict ready to save.
"""
from __future__ import annotations

import datetime as dt
import logging

from .client import ApiError, CoinGeckoClient
from .metrics import filter_universe, normalize_market_row, rotation_scores, sector_metrics
from .onchain import sector_onchain

log = logging.getLogger("rotation.collector")


def fetch_sector_tokens(client: CoinGeckoClient, category: str, per_page: int) -> list[dict]:
    raw = client.get("/coins/markets", params={
        "vs_currency": "usd",
        "category": category,
        "order": "volume_desc",
        "per_page": min(per_page, 250),
        "page": 1,
        "price_change_percentage": "24h,7d,30d",
        "sparkline": False,
    })
    return [normalize_market_row(r) for r in (raw or [])]


def fetch_benchmarks(client: CoinGeckoClient, ids: list[str]) -> dict[str, dict]:
    raw = client.get("/coins/markets", params={
        "vs_currency": "usd",
        "ids": ",".join(ids),
        "price_change_percentage": "24h,7d,30d",
        "sparkline": False,
    })
    out = {}
    for r in raw or []:
        row = normalize_market_row(r)
        out[row["id"]] = {"r24h": row["r24h"], "r7d": row["r7d"], "r30d": row["r30d"]}
    return out


def fetch_platforms(client: CoinGeckoClient, ids: list[str]) -> dict[str, dict]:
    """Map coin id -> {platform_id: contract_address} for onchain lookups."""
    if not ids:
        return {}
    try:
        raw = client.get("/coins/list", params={"include_platform": True})
    except ApiError as e:
        log.warning("coins/list failed (%s); onchain layer will be skipped", e)
        return {}
    wanted = set(ids)
    return {row["id"]: (row.get("platforms") or {}) for row in raw or [] if row.get("id") in wanted}


def run_collection(cfg: dict, client: CoinGeckoClient, past_turnovers_by_key: dict[str, list[float]],
                    skip_onchain: bool = False) -> dict:
    uni = cfg["universe"]
    excluded = set(uni.get("exclude_ids", []))
    bench_ids = [cfg["benchmarks"]["primary"], cfg["benchmarks"]["secondary"]]
    bench_map = fetch_benchmarks(client, bench_ids)
    primary_bench = bench_map.get(cfg["benchmarks"]["primary"], {})

    sectors_out: dict[str, dict] = {}
    all_top_ids: list[str] = []
    per_sector_top_tokens: dict[str, list[dict]] = {}

    for sec in cfg["sectors"]:
        key = sec["key"]
        try:
            tokens = fetch_sector_tokens(client, sec["category"], uni["tokens_per_sector"])
        except ApiError as e:
            log.warning("skipping sector %s: %s", key, e)
            continue
        tokens = filter_universe(tokens, excluded, uni["min_market_cap_usd"], uni["min_volume_24h_usd"])
        if not tokens:
            continue
        m = sector_metrics(tokens, primary_bench, past_turnovers_by_key.get(key))
        m["key"] = key
        m["label"] = sec["label"]
        m["category"] = sec["category"]
        sectors_out[key] = m
        top5 = sorted(tokens, key=lambda t: t["r7d"] or 0, reverse=True)[:cfg["onchain"]["tokens_per_sector"]]
        per_sector_top_tokens[key] = top5
        all_top_ids.extend(t["id"] for t in top5)

    if cfg["onchain"].get("enabled") and not skip_onchain and sectors_out:
        platforms = fetch_platforms(client, all_top_ids)
        for key, top_tokens in per_sector_top_tokens.items():
            try:
                sectors_out[key]["onchain"] = sector_onchain(client, top_tokens, platforms, cfg["onchain"])
            except ApiError as e:
                log.warning("onchain layer failed for %s: %s", key, e)
                sectors_out[key]["onchain"] = None
    else:
        for s in sectors_out.values():
            s["onchain"] = None

    rotation_scores(sectors_out, cfg["score_weights"])

    return {
        "generated_at": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmark": {"primary": cfg["benchmarks"]["primary"], **primary_bench},
        "sectors": sectors_out,
        "credits_used": client.calls,
    }
