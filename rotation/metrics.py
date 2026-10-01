"""Rotation metrics. Every value produced here is COMPUTED by this repo from
raw CoinGecko API fields; none of it is an official CoinGecko classification.

Raw inputs (from /coins/markets):
  price_change_percentage_{24h,7d,30d}_in_currency, market_cap, total_volume
Derived outputs (ours):
  sector returns, excess vs ETH, breadth, turnover, volume surge,
  quadrant, rotation score.
"""
from __future__ import annotations

from statistics import median

HORIZONS = ("24h", "7d", "30d")

QUADRANTS = {
    (True, True): "Leading",
    (True, False): "Weakening",
    (False, False): "Lagging",
    (False, True): "Improving",
}


def _num(v):
    try:
        if v is None:
            return None
        f = float(v)
        if f != f:  # NaN
            return None
        return f
    except (TypeError, ValueError):
        return None


def normalize_market_row(row: dict) -> dict:
    """Keep only the raw CoinGecko fields we use, as floats."""
    return {
        "id": row.get("id"),
        "symbol": (row.get("symbol") or "").upper(),
        "name": row.get("name"),
        "image": row.get("image"),
        "market_cap": _num(row.get("market_cap")),
        "volume": _num(row.get("total_volume")),
        "price": _num(row.get("current_price")),
        "r24h": _num(row.get("price_change_percentage_24h_in_currency",
                             row.get("price_change_percentage_24h"))),
        "r7d": _num(row.get("price_change_percentage_7d_in_currency")),
        "r30d": _num(row.get("price_change_percentage_30d_in_currency")),
    }


def filter_universe(tokens: list[dict], excluded_ids: set[str], min_mcap: float, min_vol: float) -> list[dict]:
    out = []
    seen = set()
    for t in tokens:
        if not t["id"] or t["id"] in excluded_ids or t["id"] in seen:
            continue
        if (t["market_cap"] or 0) < min_mcap or (t["volume"] or 0) < min_vol:
            continue
        if t["r7d"] is None or t["r24h"] is None:
            continue
        seen.add(t["id"])
        out.append(t)
    return out


def cap_weighted(tokens: list[dict], key: str):
    pairs = [(t[key], t["market_cap"]) for t in tokens if t[key] is not None and t["market_cap"]]
    total = sum(w for _, w in pairs)
    if not pairs or total <= 0:
        return None
    return sum(v * w for v, w in pairs) / total


def median_of(tokens: list[dict], key: str):
    vals = [t[key] for t in tokens if t[key] is not None]
    return median(vals) if vals else None


def breadth(tokens: list[dict], key: str, benchmark_return):
    """Share (0-100) of tokens whose return beats the benchmark over the same horizon."""
    if benchmark_return is None:
        return None
    vals = [t[key] for t in tokens if t[key] is not None]
    if not vals:
        return None
    return 100.0 * sum(1 for v in vals if v > benchmark_return) / len(vals)


def turnover(tokens: list[dict]):
    vol = sum(t["volume"] or 0 for t in tokens)
    mcap = sum(t["market_cap"] or 0 for t in tokens)
    return (vol / mcap) if mcap > 0 else None


def quadrant(trend, momentum):
    if trend is None or momentum is None:
        return None
    return QUADRANTS[(trend >= 0, momentum >= 0)]


def sector_metrics(tokens: list[dict], bench: dict, past_turnovers: list[float] | None = None) -> dict:
    """Compute one sector's metrics. `bench` holds benchmark returns: {'r24h','r7d','r30d'}."""
    m = {"n_tokens": len(tokens)}
    for h in HORIZONS:
        key = "r" + h
        med = median_of(tokens, key)
        m[f"ret_{h}_median"] = med
        m[f"ret_{h}_capw"] = cap_weighted(tokens, key)
        b = bench.get(key)
        m[f"excess_{h}"] = (med - b) if (med is not None and b is not None) else None
        m[f"breadth_{h}"] = breadth(tokens, key, b)
    m["market_cap"] = sum(t["market_cap"] or 0 for t in tokens)
    m["volume_24h"] = sum(t["volume"] or 0 for t in tokens)
    m["turnover"] = turnover(tokens)
    past = [v for v in (past_turnovers or []) if v]
    if m["turnover"] is not None and len(past) >= 3:
        m["volume_surge"] = m["turnover"] / (sum(past) / len(past))
    else:
        m["volume_surge"] = None
    m["trend"] = m["excess_30d"]
    m["momentum"] = m["excess_7d"]
    m["quadrant"] = quadrant(m["trend"], m["momentum"])
    movers = sorted([t for t in tokens if t["r7d"] is not None], key=lambda t: t["r7d"], reverse=True)
    m["top_movers"] = [
        {k: t[k] for k in ("id", "symbol", "name", "image", "r24h", "r7d", "r30d", "market_cap", "volume")}
        for t in movers[:5]
    ]
    m["laggards"] = [
        {k: t[k] for k in ("id", "symbol", "name", "r7d")} for t in movers[-3:][::-1]
    ] if len(movers) > 5 else []
    return m


def percentile_ranks(values: dict[str, float | None]) -> dict[str, float | None]:
    """Cross-sectional rank (0..1) of each sector's value; None stays None."""
    present = sorted((v, k) for k, v in values.items() if v is not None)
    n = len(present)
    out = {k: None for k in values}
    if n == 0:
        return out
    if n == 1:
        out[present[0][1]] = 0.5
        return out
    # average rank for ties
    i = 0
    while i < n:
        j = i
        while j + 1 < n and present[j + 1][0] == present[i][0]:
            j += 1
        r = ((i + j) / 2) / (n - 1)
        for k in range(i, j + 1):
            out[present[k][1]] = r
        i = j + 1
    return out


SCORE_COMPONENTS = {
    "momentum_7d": lambda s: s.get("excess_7d"),
    "breadth_7d": lambda s: s.get("breadth_7d"),
    "excess_24h": lambda s: s.get("excess_24h"),
    "volume_surge": lambda s: s.get("volume_surge"),
    "dex_buy_share": lambda s: (s.get("onchain") or {}).get("buy_share"),
    "holder_growth": lambda s: (s.get("onchain") or {}).get("holder_growth_7d"),
}


def rotation_scores(sectors: dict[str, dict], weights: dict[str, float]) -> None:
    """Add 'score' (0-100) and 'score_parts' to each sector in place.

    The score is a weighted average of cross-sectional percentile ranks, so it
    says how a sector compares with the OTHER tracked sectors right now. Missing
    components are skipped and the remaining weights re-normalised.
    """
    ranks = {}
    for comp, getter in SCORE_COMPONENTS.items():
        if weights.get(comp, 0) <= 0:
            continue
        ranks[comp] = percentile_ranks({k: getter(s) for k, s in sectors.items()})
    for key, s in sectors.items():
        total_w, acc, parts = 0.0, 0.0, {}
        for comp, r in ranks.items():
            if r.get(key) is None:
                continue
            w = weights[comp]
            total_w += w
            acc += w * r[key]
            parts[comp] = round(100 * r[key], 1)
        s["score"] = round(100 * acc / total_w, 1) if total_w > 0 else None
        s["score_parts"] = parts
