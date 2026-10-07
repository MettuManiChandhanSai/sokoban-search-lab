"""
The algorithm ladder and the single entry point every caller uses.

    from solvers.solve import solve
    result = solve(level, state, "astar_matching")

Each rung adds exactly one idea to the rung below, so the difference
between two rows of a benchmark is the value of that idea:

    bfs               nothing: blind, level-by-level
    astar             + a heuristic (Manhattan distance)
    astar_deadlock    + knowledge (deadlock rules prune hopeless pushes)
    astar_matching    + a sharper heuristic (min-cost crate-goal matching)

`Search` is a pausable handle on one run: advance(seconds) works for at
most that long and returns. The browser uses it to keep animating while
a search runs and to race several algorithms against each other; solve()
just advances to the end.

A result is a plain dict:
    algorithm, label, status, solved, moves (LURD string or None),
    n_moves, n_pushes, expanded, generated, peak, pruned {rule: count}, time
status is one of: solved, unsolvable, node_limit, time_limit.
"""

from collections import Counter, namedtuple
from time import perf_counter

from engine.state import pushes_to_moves

from .astar import astar
from .bfs import bfs
from .deadlock import Deadlocks
from .heuristics import manhattan, matching

Algorithm = namedtuple("Algorithm", "label short idea")

ALGORITHMS = {
    "bfs": Algorithm(
        "BFS", "BFS",
        "Uninformed baseline. Tries every position, fewest pushes first."),
    "astar": Algorithm(
        "A*", "A*",
        "Adds a heuristic: Manhattan distance steers the search toward the goals."),
    "astar_deadlock": Algorithm(
        "A* + Deadlock", "A* + DL",
        "Adds knowledge: corner, wall-line, dead-square and freeze rules "
        "discard pushes that can never lead to a solution."),
    "astar_matching": Algorithm(
        "A* + Deadlock + Matching", "A* + DL + M",
        "Adds a sharper heuristic: true push distances and a one-to-one "
        "crate-to-goal assignment."),
}
BEST = "astar_matching"


def _start(level, state, algorithm, stats):
    if algorithm == "bfs":
        return bfs(level, state, stats)
    if algorithm == "astar":
        return astar(level, state, stats, manhattan(level))
    if algorithm == "astar_deadlock":
        return astar(level, state, stats, manhattan(level), Deadlocks(level))
    if algorithm == "astar_matching":
        return astar(level, state, stats, matching(level), Deadlocks(level))
    raise ValueError(f"Unknown algorithm: {algorithm}")


class Search:
    def __init__(self, level, state, algorithm=BEST,
                 node_limit=300_000, time_limit=60.0):
        self.level, self.start, self.algorithm = level, state, algorithm
        self.node_limit, self.time_limit = node_limit, time_limit
        self.stats = {"expanded": 0, "generated": 0, "frontier": 0, "peak": 0,
                      "depth": 0, "state": state, "pruned": Counter()}
        self.elapsed = 0.0          # time spent searching, pauses excluded
        self.result = None
        self._run = None

    def advance(self, seconds=None):
        """Search for at most `seconds` (None: until finished).
        Returns True once `self.result` is available."""
        if self.result:
            return True
        began = perf_counter()
        stats, status, pushes = self.stats, None, None
        try:
            if self._run is None:   # set-up (heuristic tables, dead squares) is timed too
                self._run = _start(self.level, self.start, self.algorithm, stats)
            while not status:
                next(self._run)
                stats["peak"] = max(stats["peak"], stats["frontier"])
                spent = perf_counter() - began
                if stats["expanded"] >= self.node_limit:
                    status = "node_limit"
                elif self.elapsed + spent >= self.time_limit:
                    status = "time_limit"
                elif seconds is not None and spent >= seconds:
                    break
        except StopIteration as finished:
            pushes = finished.value
            status = "unsolvable" if pushes is None else "solved"
        self.elapsed += perf_counter() - began
        if status:
            self._finish(status, pushes)
        return bool(self.result)

    def _finish(self, status, pushes):
        solved = pushes is not None
        moves = pushes_to_moves(self.level, self.start, pushes) if solved else None
        self._run = None
        self.result = {
            "algorithm": self.algorithm,
            "label": ALGORITHMS[self.algorithm].label,
            "status": status,
            "solved": solved,
            "moves": moves,
            "n_moves": len(moves) if solved else None,
            "n_pushes": len(pushes) if solved else None,
            "expanded": self.stats["expanded"],
            "generated": self.stats["generated"],
            "peak": self.stats["peak"],
            "pruned": dict(self.stats["pruned"]),
            "time": self.elapsed,
        }


def solve(level, state, algorithm=BEST, **limits):
    search = Search(level, state, algorithm, **limits)
    search.advance()
    return search.result
