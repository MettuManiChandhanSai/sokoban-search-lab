import unittest

from analytics.benchmark import Benchmark
from analytics.report import summary, table, to_csv, to_markdown
from puzzles.library import catalog

LEVELS = [e for e in catalog() if e["id"] in ("classic/02_warm_up", "classic/09_round_the_pillar")]


class BenchmarkRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bench = Benchmark(LEVELS)
        slices = 0
        while not bench.advance(0.01):
            slices += 1
        cls.rows, cls.slices = bench.rows, slices

    def test_one_row_per_level_and_algorithm(self):
        self.assertEqual(len(self.rows), 2 * 4)
        self.assertEqual({r["level"] for r in self.rows}, {e["id"] for e in LEVELS})
        self.assertTrue(all(r["status"] == "solved" for r in self.rows))

    def test_rows_carry_the_comparison_against_bfs(self):
        best = next(r for r in self.rows if r["algorithm"] == "astar_matching")
        self.assertGreater(best["node_reduction"], 0)

    def test_reports_render_every_row(self):
        for render in (table, to_csv, to_markdown):
            text = render(self.rows)
            self.assertEqual(text.count("Warm-up"), 4, render.__name__)
            self.assertIn("A* + Deadlock + Matching", text)
        self.assertEqual(len(to_csv(self.rows).splitlines()), 1 + len(self.rows))

    def test_summary_has_one_line_per_algorithm(self):
        lines = summary(self.rows)
        self.assertEqual([s["algorithm"] for s in lines],
                         ["bfs", "astar", "astar_deadlock", "astar_matching"])
        self.assertEqual(lines[0]["solved"], 2)
        self.assertLess(lines[-1]["expanded"], lines[0]["expanded"])


if __name__ == "__main__":
    unittest.main()
