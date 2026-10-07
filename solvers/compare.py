"""
Head-to-head comparison: every algorithm on the *same* position.

run_all()              run the ladder one after another, return the results
Race                   run them interleaved in small time slices, so a UI
                       can show all of them progressing at once
compare_to_baseline()  annotate each result with what it saved versus BFS

Both the command-line benchmark (analytics) and the browser's race view
use these, so the numbers in the report and on screen come from one place.
"""

from .solve import ALGORITHMS, Search


def run_all(level, state, algorithms=ALGORITHMS, **limits):
    race = Race(level, state, algorithms, **limits)
    for search in race.searches:
        search.advance()
    return race.results


class Race:
    def __init__(self, level, state, algorithms=ALGORITHMS, **limits):
        self.searches = [Search(level, state, key, **limits) for key in algorithms]

    def advance(self, seconds):
        """Give every unfinished search an equal share of `seconds`.
        Returns True once all have finished."""
        running = [s for s in self.searches if not s.result]
        for search in running:
            search.advance(seconds / len(running))
        return all(s.result for s in self.searches)

    @property
    def results(self):
        return [s.result for s in self.searches]


def compare_to_baseline(results, baseline="bfs"):
    """Add ``node_reduction`` (% fewer nodes expanded) and ``speedup``
    (times faster) to every result, measured against `baseline`.

    If the baseline hit a limit before finishing, its true cost is even
    higher, so the figures are lower bounds; ``baseline_finished`` says
    which case applies.
    """
    base = next((r for r in results if r["algorithm"] == baseline), None)
    for r in results:
        r["node_reduction"] = r["speedup"] = None
        if base and base["expanded"]:
            r["node_reduction"] = 100.0 * (1 - r["expanded"] / base["expanded"])
            r["speedup"] = base["time"] / max(r["time"], 1e-9)
            r["baseline_finished"] = base["status"] in ("solved", "unsolvable")
    return results
