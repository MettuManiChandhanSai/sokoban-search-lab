"""
The benchmark: every algorithm, every level, identical conditions.

Each level is solved from its start position by the whole ladder
(solvers.compare.Race), and every result becomes one row tagged with
the level it came from and its saving against the BFS baseline.

Benchmark is pausable like a Search: advance(seconds) does a slice of
work and returns, `rows` grows as levels finish.

Command line:
    python run_benchmark.py                     all levels
    python run_benchmark.py --pack warehouse    one pack
    python run_benchmark.py --node-limit 50000 --time-limit 20
"""

import argparse
from pathlib import Path

from engine.level import parse_level
from puzzles.library import PACKS, catalog
from solvers.compare import Race, compare_to_baseline
from solvers.solve import ALGORITHMS

from .report import summary_table, table, to_csv, to_markdown

RESULTS = Path(__file__).parent / "results"


class Benchmark:
    def __init__(self, levels=None, algorithms=ALGORITHMS, **limits):
        self.pending = list(levels if levels is not None else catalog())[::-1]
        self.total = len(self.pending)
        self.algorithms, self.limits = algorithms, limits
        self.rows = []
        self.entry = self.race = None

    def advance(self, seconds):
        """Work for about `seconds`. Returns True when every level is done."""
        if self.race is None:
            if not self.pending:
                return True
            self.entry = self.pending.pop()
            level, state = parse_level(self.entry["text"])
            self.crates = len(state.boxes)
            self.race = Race(level, state, self.algorithms, **self.limits)
        if self.race.advance(seconds):
            for result in compare_to_baseline(self.race.results):
                self.rows.append({"level": self.entry["id"], "title": self.entry["title"],
                                  "crates": self.crates, **result})
            self.race = None
        return self.race is None and not self.pending


def main(argv=None):
    parser = argparse.ArgumentParser(description="Benchmark the Sokoban solvers.")
    parser.add_argument("--pack", choices=PACKS, help="only this pack")
    parser.add_argument("--node-limit", type=int, default=300_000)
    parser.add_argument("--time-limit", type=float, default=60.0)
    args = parser.parse_args(argv)

    levels = [e for e in catalog() if args.pack in (None, e["pack"])]
    bench = Benchmark(levels, node_limit=args.node_limit, time_limit=args.time_limit)
    printed = 0
    print(table([]))
    while not bench.advance(0.5) or printed < len(bench.rows):
        for line in table(bench.rows).splitlines()[2 + printed:]:
            print(line, flush=True)
        printed = len(bench.rows)

    print("\n" + summary_table(bench.rows))
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "benchmark.csv").write_text(to_csv(bench.rows), encoding="utf-8")
    (RESULTS / "benchmark.md").write_text(to_markdown(bench.rows), encoding="utf-8")
    print(f"\nSaved {RESULTS / 'benchmark.csv'} and benchmark.md")
