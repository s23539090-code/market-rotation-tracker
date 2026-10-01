"""Quadrant-change and breadth/volume-surge alerts, computed by comparing the
newest snapshot's sectors against the previous one. These are OUR rules, not
CoinGecko signals.
"""
from __future__ import annotations


def detect_alerts(prev: dict | None, curr: dict, cfg: dict) -> list[dict]:
    alerts = []
    curr_sectors = curr.get("sectors", {})
    prev_sectors = (prev or {}).get("sectors", {})
    for key, s in curr_sectors.items():
        label = s.get("label", key)
        p = prev_sectors.get(key)
        if p and p.get("quadrant") and s.get("quadrant") and p["quadrant"] != s["quadrant"]:
            alerts.append({
                "type": "quadrant_change",
                "sector": key,
                "label": label,
                "message": f"{label}: {p['quadrant']} → {s['quadrant']}",
                "from": p["quadrant"],
                "to": s["quadrant"],
            })
        if p and p.get("breadth_7d") is not None and s.get("breadth_7d") is not None:
            jump = s["breadth_7d"] - p["breadth_7d"]
            if abs(jump) >= cfg.get("breadth_jump_pts", 25):
                direction = "jumped" if jump > 0 else "dropped"
                alerts.append({
                    "type": "breadth_jump",
                    "sector": key,
                    "label": label,
                    "message": f"{label}: breadth {direction} {abs(jump):.0f} pts "
                               f"({p['breadth_7d']:.0f}% → {s['breadth_7d']:.0f}%)",
                    "delta": round(jump, 1),
                })
        surge = s.get("volume_surge")
        if surge is not None and surge >= cfg.get("volume_surge_ratio", 1.5):
            alerts.append({
                "type": "volume_surge",
                "sector": key,
                "label": label,
                "message": f"{label}: turnover {surge:.1f}x its recent average",
                "ratio": round(surge, 2),
            })
    return alerts
