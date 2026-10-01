"""Onchain verification layer (Layer 3): DEX buy/sell flow and holder growth
for a handful of top movers per sector, using the token's primary EVM/Solana
platform from /coins/list?include_platform=true.

This exists specifically because 24h trading volume on its own does NOT prove
net inflow (see the brief's own caveat). Buy/sell USD flow on the token's
most active pool is a closer proxy for actual accumulation.
"""
from __future__ import annotations

from .client import ApiError


def pick_network(platforms: dict, mapping: dict[str, str]) -> tuple[str, str] | None:
    """Return (network_id, contract_address) for the first supported platform."""
    if not platforms:
        return None
    for platform_id, address in platforms.items():
        if platform_id in mapping and address:
            return mapping[platform_id], address
    return None


def token_onchain_flow(client, network: str, address: str, min_trade_usd: float) -> dict | None:
    """Top pool buy/sell USD over 24h for one token. Returns None if no onchain data."""
    try:
        resp = client.get(f"/onchain/networks/{network}/tokens/{address}/pools",
                           params={"page": 1, "sort": "h24_volume_usd_liquidity_desc"})
    except ApiError:
        return None
    pools = (resp or {}).get("data") or []
    if not pools:
        return None
    pool = pools[0]["attributes"]
    tx = pool.get("transactions", {}).get("h24", {}) or {}
    vol = pool.get("volume_usd", {}).get("h24")
    try:
        vol_h24 = float(vol) if vol is not None else None
    except (TypeError, ValueError):
        vol_h24 = None
    buys, sells = tx.get("buys") or 0, tx.get("sells") or 0
    total_tx = buys + sells
    if total_tx == 0 or vol_h24 is None:
        return None
    # Approximate buy-side USD share from buy/sell transaction counts, since
    # the pools endpoint gives counts, not a buy/sell USD split directly.
    buy_share = buys / total_tx
    return {
        "pool_name": pool.get("name"),
        "pool_volume_24h_usd": vol_h24,
        "buys_24h": buys,
        "sells_24h": sells,
        "buy_share": round(100 * buy_share, 1),
        "reserve_usd": _f(pool.get("reserve_in_usd")),
    }


def token_holder_growth(client, network: str, address: str) -> dict | None:
    try:
        resp = client.get(f"/onchain/networks/{network}/tokens/{address}/holders_chart",
                           params={"days": "7"})
    except ApiError:
        return None
    series = ((resp or {}).get("data") or {}).get("attributes", {}).get("token_holders_list") or []
    if len(series) < 2:
        return None
    first, last = series[0][1], series[-1][1]
    if not first:
        return None
    return {"holders_now": last, "holders_7d_ago": first,
            "holder_growth_7d": round(100 * (last - first) / first, 2)}


def _f(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def sector_onchain(client, top_tokens: list[dict], platforms_by_id: dict[str, dict],
                    cfg: dict) -> dict:
    """Aggregate a buy_share and holder_growth_7d across a sector's top movers."""
    mapping = cfg["platform_to_network"]
    flows, growths = [], []
    details = []
    for t in top_tokens[: cfg.get("tokens_per_sector", 3)]:
        plat = platforms_by_id.get(t["id"]) or {}
        picked = pick_network(plat, mapping)
        if not picked:
            continue
        network, address = picked
        flow = token_onchain_flow(client, network, address, cfg.get("min_trade_usd", 500))
        entry = {"id": t["id"], "symbol": t["symbol"], "network": network}
        if flow:
            flows.append(flow["buy_share"])
            entry.update(flow)
        if cfg.get("holders") and network in cfg.get("holders_networks", []):
            hg = token_holder_growth(client, network, address)
            if hg:
                growths.append(hg["holder_growth_7d"])
                entry.update(hg)
        details.append(entry)
    return {
        "buy_share": round(sum(flows) / len(flows), 1) if flows else None,
        "holder_growth_7d": round(sum(growths) / len(growths), 2) if growths else None,
        "tokens": details,
    }
