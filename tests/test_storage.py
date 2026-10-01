"""Regression test for a real bug found while testing: when two snapshots
share the same `generated_at` string (same wall-clock second), sorting
load_all_snapshots() by that field scrambles their order, since Python's
sort is stable but the *input* order from a plain filename sort was already
wrong relative to creation order once a collision suffix existed. The fix
was to make the filename itself the sole, zero-padded sort key.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestSnapshotOrderingUnderCollision(unittest.TestCase):
    def test_same_second_snapshots_preserve_creation_order(self):
        import importlib
        import rotation.storage as storage

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                importlib.reload(storage)
                same_ts = "2026-10-01T03:00:00Z"
                created_order = []
                for i in range(12):
                    snap = {"generated_at": same_ts, "sectors": {"ai": {"turnover": i}}}
                    storage.save_snapshot(snap)
                    created_order.append(i)

                loaded = storage.load_all_snapshots()
                self.assertEqual(len(loaded), 12)
                loaded_order = [s["sectors"]["ai"]["turnover"] for s in loaded]
                self.assertEqual(loaded_order, created_order,
                                  "snapshots sharing a timestamp must still load in creation order")
                # the one that matters most: "latest" must be the LAST one actually written
                self.assertEqual(loaded[-1]["sectors"]["ai"]["turnover"], 11)
            finally:
                os.chdir(old_cwd)
                importlib.reload(storage)

    def test_mixed_distinct_and_colliding_timestamps_stay_chronological(self):
        import importlib
        import rotation.storage as storage

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                importlib.reload(storage)
                storage.save_snapshot({"generated_at": "2026-10-01T03:00:00Z", "sectors": {"ai": {"turnover": 1}}})
                storage.save_snapshot({"generated_at": "2026-10-01T03:00:00Z", "sectors": {"ai": {"turnover": 2}}})
                storage.save_snapshot({"generated_at": "2026-10-01T04:00:00Z", "sectors": {"ai": {"turnover": 3}}})
                loaded = storage.load_all_snapshots()
                self.assertEqual([s["sectors"]["ai"]["turnover"] for s in loaded], [1, 2, 3])
            finally:
                os.chdir(old_cwd)
                importlib.reload(storage)


if __name__ == "__main__":
    unittest.main()
