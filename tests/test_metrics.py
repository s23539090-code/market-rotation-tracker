import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rotation.metrics import (breadth, cap_weighted, filter_universe, median_of,
                               percentile_ranks, quadrant, rotation_scores,
                               sector_metrics, turnover)


def tok(id_, r24h, r7d, r30d, mcap=1_000_000, vol=100_000):
    return {"id": id_, "symbol": id_.upper(), "name": id_, "image": "",
            "market_cap": mcap, "volume": vol, "price": 1,
            "r24h": r24h, "r7d": r7d, "r30d": r30d}


class TestBasics(unittest.TestCase):
    def test_median_and_capweighted(self):
        tokens = [tok("a", 0, 10, 0, mcap=100), tok("b", 0, 20, 0, mcap=100), tok("c", 0, 30, 0, mcap=800)]
        self.assertEqual(median_of(tokens, "r7d"), 20)
        # cap-weighted should be pulled toward the heavy 'c' token (30)
        cw = cap_weighted(tokens, "r7d")
        self.assertGreater(cw, 25)

    def test_breadth_counts_tokens_beating_benchmark(self):
        tokens = [tok("a", 0, 5, 0), tok("b", 0, 15, 0), tok("c", 0, -5, 0), tok("d", 0, 20, 0)]
        b = breadth(tokens, "r7d", benchmark_return=10)
        self.assertAlmostEqual(b, 50.0)  # b and d beat 10%, a and c don't

    def test_breadth_none_without_benchmark(self):
        self.assertIsNone(breadth([tok("a", 0, 5, 0)], "r7d", None))

    def test_turnover_is_volume_over_mcap(self):
        tokens = [tok("a", 0, 0, 0, mcap=1000, vol=200)]
        self.assertAlmostEqual(turnover(tokens), 0.2)

    def test_quadrant_mapping(self):
        self.assertEqual(quadrant(1, 1), "Leading")
        self.assertEqual(quadrant(1, -1), "Weakening")
        self.assertEqual(quadrant(-1, -1), "Lagging")
        self.assertEqual(quadrant(-1, 1), "Improving")
        self.assertIsNone(quadrant(None, 1))

    def test_filter_universe_excludes_stablecoins_and_thin_tokens(self):
        tokens = [
            tok("usdc", 0, 0.01, 0, mcap=5e10, vol=1e9),
            tok("thin", 1, 1, 1, mcap=1000, vol=10),  # below thresholds
            tok("ok", 1, 2, 3, mcap=1e8, vol=1e6),
        ]
        out = filter_universe(tokens, excluded_ids={"usdc"}, min_mcap=1e7, min_vol=1e5)
        self.assertEqual([t["id"] for t in out], ["ok"])

    def test_filter_universe_dedupes(self):
        tokens = [tok("ok", 1, 2, 3, mcap=1e8, vol=1e6), tok("ok", 1, 2, 3, mcap=1e8, vol=1e6)]
        out = filter_universe(tokens, set(), 0, 0)
        self.assertEqual(len(out), 1)


class TestSectorMetrics(unittest.TestCase):
    def test_sector_metrics_excess_and_breadth(self):
        tokens = [tok("a", 1, 10, 20), tok("b", 2, -5, -10), tok("c", 0, 15, 25)]
        bench = {"r24h": 1.0, "r7d": 5.0, "r30d": 10.0}
        m = sector_metrics(tokens, bench)
        self.assertEqual(m["n_tokens"], 3)
        # median r7d = 10, excess_7d = 10 - 5 = 5
        self.assertAlmostEqual(m["ret_7d_median"], 10)
        self.assertAlmostEqual(m["excess_7d"], 5)
        # a (10%) and c (15%) beat bench 5%, b (-5%) doesn't -> 2/3
        self.assertAlmostEqual(m["breadth_7d"], 200 / 3)
        self.assertIn(m["quadrant"], ("Leading", "Weakening", "Lagging", "Improving"))
        self.assertEqual(len(m["top_movers"]) <= 5, True)

    def test_sector_metrics_handles_missing_benchmark(self):
        tokens = [tok("a", 1, 10, 20)]
        m = sector_metrics(tokens, {})
        self.assertIsNone(m["excess_7d"])
        self.assertIsNone(m["breadth_7d"])

    def test_volume_surge_requires_history(self):
        tokens = [tok("a", 1, 1, 1, mcap=1000, vol=500)]
        m = sector_metrics(tokens, {}, past_turnovers=[0.1, 0.1])  # only 2 points, need >=3
        self.assertIsNone(m["volume_surge"])
        m2 = sector_metrics(tokens, {}, past_turnovers=[0.1, 0.1, 0.1])
        self.assertIsNotNone(m2["volume_surge"])
        self.assertAlmostEqual(m2["volume_surge"], 0.5 / 0.1)


class TestPercentileAndScore(unittest.TestCase):
    def test_percentile_ranks_simple(self):
        ranks = percentile_ranks({"a": 1, "b": 2, "c": 3})
        self.assertEqual(ranks["a"], 0.0)
        self.assertEqual(ranks["c"], 1.0)
        self.assertEqual(ranks["b"], 0.5)

    def test_percentile_ranks_ties_get_average_rank(self):
        ranks = percentile_ranks({"a": 1, "b": 1, "c": 2})
        self.assertEqual(ranks["a"], ranks["b"])

    def test_percentile_ranks_skips_none(self):
        ranks = percentile_ranks({"a": 1, "b": None})
        self.assertIsNone(ranks["b"])
        self.assertIsNotNone(ranks["a"])

    def test_rotation_scores_orders_sectors_by_strength(self):
        sectors = {
            "strong": {"excess_7d": 20, "breadth_7d": 90, "excess_24h": 5, "volume_surge": 2.0, "onchain": None},
            "weak": {"excess_7d": -10, "breadth_7d": 10, "excess_24h": -5, "volume_surge": 0.5, "onchain": None},
        }
        weights = {"momentum_7d": 0.4, "breadth_7d": 0.3, "excess_24h": 0.1,
                   "volume_surge": 0.2, "dex_buy_share": 0.0, "holder_growth": 0.0}
        rotation_scores(sectors, weights)
        self.assertGreater(sectors["strong"]["score"], sectors["weak"]["score"])
        self.assertEqual(sectors["strong"]["score"], 100.0)
        self.assertEqual(sectors["weak"]["score"], 0.0)

    def test_rotation_scores_renormalizes_when_component_missing(self):
        sectors = {
            "a": {"excess_7d": 10, "breadth_7d": None, "excess_24h": 1, "volume_surge": None, "onchain": None},
            "b": {"excess_7d": 5, "breadth_7d": None, "excess_24h": 2, "volume_surge": None, "onchain": None},
        }
        weights = {"momentum_7d": 0.5, "breadth_7d": 0.3, "excess_24h": 0.2,
                   "volume_surge": 0.0, "dex_buy_share": 0.0, "holder_growth": 0.0}
        rotation_scores(sectors, weights)
        self.assertIsNotNone(sectors["a"]["score"])
        self.assertIsNotNone(sectors["b"]["score"])


if __name__ == "__main__":
    unittest.main()
