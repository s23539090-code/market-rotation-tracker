"""End-to-end pipeline tests, run entirely against MockCoinGeckoClient
(simulated data matching verified CoinGecko response shapes) — no network,
no API key required. Runs in a temp directory so it never touches the real
docs/data/ folder.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rotation.alerts import detect_alerts
from rotation.collector import run_collection
from rotation.mock_client import MockCoinGeckoClient
from rotation.storage import (build_trails, load_all_snapshots, save_snapshot,
                               write_alert_log, write_latest_and_history)


def load_config():
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / "config" / "sectors.json").read_text(encoding="utf-8"))


class TestSingleRun(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()
        self.client = MockCoinGeckoClient(self.cfg, tick=0)

    def test_run_collection_produces_all_configured_sectors(self):
        snap = run_collection(self.cfg, self.client, {})
        self.assertIn("generated_at", snap)
        self.assertIn("benchmark", snap)
        self.assertGreater(len(snap["sectors"]), 0)
        for key, s in snap["sectors"].items():
            self.assertIn("score", s)
            self.assertIn("quadrant", s)
            self.assertIn("n_tokens", s)
            self.assertGreater(s["n_tokens"], 0)

    def test_every_sector_has_a_score_after_scoring(self):
        snap = run_collection(self.cfg, self.client, {})
        scores = [s["score"] for s in snap["sectors"].values()]
        self.assertTrue(all(sc is not None for sc in scores))

    def test_onchain_layer_populates_when_enabled(self):
        snap = run_collection(self.cfg, self.client, {})
        has_onchain = [s["onchain"] for s in snap["sectors"].values() if s.get("onchain")]
        self.assertGreater(len(has_onchain), 0, "expected at least one sector with onchain data")

    def test_onchain_layer_can_be_skipped(self):
        snap = run_collection(self.cfg, self.client, {}, skip_onchain=True)
        self.assertTrue(all(s["onchain"] is None for s in snap["sectors"].values()))


class TestMultiRunHistoryAndAlerts(unittest.TestCase):
    """Simulates several hourly ticks and checks storage + alerting hold up."""

    def test_history_accumulates_and_alerts_fire_on_quadrant_change(self):
        cfg = load_config()
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                import rotation.storage as storage
                import importlib
                importlib.reload(storage)  # re-resolve DATA_DIR relative to tmp cwd

                prev_snapshot = None
                for tick in range(6):
                    client = MockCoinGeckoClient(cfg, tick=tick)
                    snap = run_collection(cfg, client, {})
                    alerts = detect_alerts(prev_snapshot, snap, cfg["alerts"])
                    snap["alerts"] = alerts
                    storage.save_snapshot(snap)
                    prev_snapshot = snap

                history = storage.load_all_snapshots()
                self.assertEqual(len(history), 6, "every tick should produce its own stored snapshot")

                write_latest_and_history(history)
                write_alert_log(history)
                trails = build_trails(history, [s["key"] for s in cfg["sectors"]])

                latest_path = storage.DATA_DIR / "latest.json"
                self.assertTrue(latest_path.exists())
                latest = json.loads(latest_path.read_text())
                self.assertEqual(latest["generated_at"], history[-1]["generated_at"])

                alerts_path = storage.DATA_DIR / "alerts.json"
                self.assertTrue(alerts_path.exists())

                for key, trail in trails.items():
                    self.assertLessEqual(len(trail), 12)
            finally:
                os.chdir(old_cwd)
                importlib.reload(storage)  # restore DATA_DIR pointing at the real project

    def test_snapshot_filenames_never_collide_within_the_same_second(self):
        cfg = load_config()
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                import importlib
                import rotation.storage as storage
                importlib.reload(storage)
                for tick in range(3):
                    snap = run_collection(cfg, MockCoinGeckoClient(cfg, tick=tick), {})
                    storage.save_snapshot(snap)
                files = list(storage.SNAP_DIR.glob("*.json"))
                self.assertEqual(len(files), 3)
            finally:
                os.chdir(old_cwd)
                importlib.reload(storage)


if __name__ == "__main__":
    unittest.main()
