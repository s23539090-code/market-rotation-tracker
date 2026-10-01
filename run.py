"""Entry point.

Usage:
  python run.py collect      # one real collection run (needs COINGECKO_API_KEY)
  python run.py demo         # run the whole pipeline on bundled mock data, no network/key needed
  python run.py check        # validate config + .env without calling the API
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from rotation.alerts import detect_alerts
from rotation.client import CoinGeckoClient, load_dotenv
from rotation.collector import run_collection
from rotation.storage import (build_trails, load_all_snapshots, past_turnovers,
                               prune_old_snapshots, save_snapshot, write_alert_log,
                               write_latest_and_history)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("run")


def load_config() -> dict:
    return json.loads((Path(__file__).parent / "config" / "sectors.json").read_text(encoding="utf-8"))


def build_snapshot(cfg: dict, client: CoinGeckoClient) -> dict:
    history = load_all_snapshots()
    turnovers = {sec["key"]: past_turnovers(history, sec["key"]) for sec in cfg["sectors"]}
    return run_collection(cfg, client, turnovers)


def finish_run(cfg: dict, snapshot: dict) -> list[dict]:
    history = load_all_snapshots()
    prev = history[-1] if history else None
    alerts = detect_alerts(prev, snapshot, cfg["alerts"])
    snapshot["alerts"] = alerts
    save_snapshot(snapshot)
    prune_old_snapshots(cfg.get("history_days", 30))
    history = load_all_snapshots()
    write_latest_and_history(history)
    write_alert_log(history)
    trails = build_trails(history, [s["key"] for s in cfg["sectors"]])
    data_dir = Path("docs") / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "trails.json").write_text(json.dumps(trails, indent=2), encoding="utf-8")
    return alerts


def cmd_collect(_args) -> int:
    load_dotenv()
    cfg = load_config()
    client = CoinGeckoClient()
    if not client.has_key:
        log.error("COINGECKO_API_KEY is not set. Put it in a local .env file "
                   "(see .env.example) or, for GitHub Actions, add it as a repo secret.")
        return 1
    log.info("Collecting with environment=%s", client.environment)
    snapshot = build_snapshot(cfg, client)
    alerts = finish_run(cfg, snapshot)
    log.info("Done. %d sectors, %d API calls, %d alert(s).",
              len(snapshot["sectors"]), snapshot["credits_used"], len(alerts))
    for a in alerts:
        log.info("ALERT: %s", a["message"])
    return 0


def cmd_demo(_args) -> int:
    from rotation.mock_client import MockCoinGeckoClient
    cfg = load_config()
    client = MockCoinGeckoClient(cfg)
    log.info("Running DEMO pipeline on simulated data (no network, no key).")
    snapshot = build_snapshot(cfg, client)
    snapshot["source"] = "demo"
    alerts = finish_run(cfg, snapshot)
    log.info("Done. %d sectors, %d simulated calls, %d alert(s).",
              len(snapshot["sectors"]), snapshot["credits_used"], len(alerts))
    return 0


def cmd_check(_args) -> int:
    load_dotenv()
    cfg = load_config()
    problems = []
    if not cfg.get("sectors"):
        problems.append("config/sectors.json has no sectors")
    import os
    key = os.environ.get("COINGECKO_API_KEY", "")
    env = os.environ.get("COINGECKO_ENVIRONMENT", "pro")
    if not key:
        problems.append("COINGECKO_API_KEY is not set (ok for demo/check, required for collect)")
    if env not in ("pro", "demo"):
        problems.append("COINGECKO_ENVIRONMENT must be 'pro' or 'demo'")
    print(f"Sectors configured: {len(cfg.get('sectors', []))}")
    print(f"COINGECKO_ENVIRONMENT: {env}")
    print(f"COINGECKO_API_KEY set: {'yes' if key else 'no'}")
    if problems:
        print("\nIssues:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nConfig looks OK.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Market Rotation Tracker")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("collect").set_defaults(func=cmd_collect)
    sub.add_parser("demo").set_defaults(func=cmd_demo)
    sub.add_parser("check").set_defaults(func=cmd_check)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
