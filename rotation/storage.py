"""Append-only snapshot storage. Each run writes one JSON file under
data/snapshots/, and data/latest.json + data/history.json are rebuilt from
that folder. This is what lets GitHub Actions accumulate hourly history
without a database.
"""
from __future__ import annotations

import json
from pathlib import Path

# Lives under docs/ so GitHub Pages (serving the docs/ folder) can read these
# JSON files directly with no separate publish/copy step.
DATA_DIR = Path("docs") / "data"
SNAP_DIR = DATA_DIR / "snapshots"


def save_snapshot(snapshot: dict) -> Path:
    """Filenames are `<timestamp>-<seq>.json` with a zero-padded sequence, so
    that plain alphabetical sort == chronological order EVEN when two runs
    land in the same wall-clock second (e.g. back-to-back demo runs, or a
    manual re-run). Never sort snapshots by the `generated_at` field alone:
    it's identical for same-second collisions, which would otherwise scramble
    "latest" between them (a real bug we hit and fixed while testing this)."""
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    ts = snapshot["generated_at"].replace(":", "").replace("-", "")
    n = 0
    while True:
        path = SNAP_DIR / f"{ts}-{n:03d}.json"
        if not path.exists():
            break
        n += 1
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_all_snapshots() -> list[dict]:
    """Returns snapshots oldest-first. Ordering is by FILENAME (which sorts
    chronologically by construction, including same-second collisions via
    the zero-padded sequence) — never by the `generated_at` field, which is
    not unique enough to sort on."""
    if not SNAP_DIR.exists():
        return []
    out = []
    for f in sorted(SNAP_DIR.glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def prune_old_snapshots(keep_days: int) -> None:
    import datetime as dt
    if not SNAP_DIR.exists():
        return
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=keep_days)
    for f in SNAP_DIR.glob("*.json"):
        try:
            snap = json.loads(f.read_text(encoding="utf-8"))
            ts = dt.datetime.fromisoformat(snap["generated_at"].replace("Z", "+00:00")).replace(tzinfo=None)
            if ts < cutoff:
                f.unlink()
        except (json.JSONDecodeError, KeyError, ValueError):
            continue


def past_turnovers(history: list[dict], sector_key: str, n: int = 24) -> list[float]:
    vals = []
    for snap in history[-n:]:
        s = snap.get("sectors", {}).get(sector_key)
        if s and s.get("turnover") is not None:
            vals.append(s["turnover"])
    return vals


def build_trails(history: list[dict], sector_keys: list[str], points: int = 12) -> dict[str, list[dict]]:
    """Last N (trend, momentum, score) points per sector for the quadrant trail."""
    trails = {k: [] for k in sector_keys}
    for snap in history[-points:]:
        for k in sector_keys:
            s = snap.get("sectors", {}).get(k)
            if s and s.get("trend") is not None and s.get("momentum") is not None:
                trails[k].append({
                    "t": snap.get("generated_at"),
                    "trend": s["trend"],
                    "momentum": s["momentum"],
                    "score": s.get("score"),
                })
    return trails


def write_alert_log(history: list[dict], max_items: int = 200) -> None:
    """data/alerts.json: every alert ever fired, across all snapshots, newest first.
    This is what lets the dashboard show a rotation log, not just this run's alerts."""
    items = []
    for snap in history:
        for a in snap.get("alerts", []) or []:
            items.append({**a, "at": snap["generated_at"]})
    items.sort(key=lambda a: a["at"], reverse=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "alerts.json").write_text(json.dumps(items[:max_items], indent=2), encoding="utf-8")


def write_latest_and_history(history: list[dict], max_history_points: int = 24 * 30) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if history:
        (DATA_DIR / "latest.json").write_text(
            json.dumps(history[-1], indent=2, sort_keys=True), encoding="utf-8")
    trimmed = history[-max_history_points:]
    compact = [
        {
            "generated_at": s["generated_at"],
            "sectors": {
                k: {"score": v.get("score"), "trend": v.get("trend"),
                    "momentum": v.get("momentum"), "quadrant": v.get("quadrant")}
                for k, v in s.get("sectors", {}).items()
            },
        }
        for s in trimmed
    ]
    (DATA_DIR / "history.json").write_text(json.dumps(compact, indent=2), encoding="utf-8")
