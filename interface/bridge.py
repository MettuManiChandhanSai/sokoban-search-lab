"""
The bridge: everything the browser can ask Python to do.

    call("move", '{"direction": "L"}')  ->  '{"player": 17, "boxes": [...], ...}'

A Game holds one play session:

*   the level and a **timeline** of positions. Your moves and the AI's
    solution live on the same line, so undo, redo, replay and scrubbing
    are all just "move the cursor";
*   **jobs**: searches that run a few milliseconds at a time whenever
    the page calls tick(), so the board keeps animating while BFS
    grinds and several algorithms can race each other.

Nothing here touches the browser; tests drive it directly.
"""

import json

from analytics.benchmark import Benchmark
from analytics.report import summary, to_csv, to_markdown
from engine.level import LevelError, format_level, parse_level
from engine.state import apply_move, is_goal
from puzzles.generator import generate
from puzzles.library import PACKS, catalog
from solvers.compare import Race, compare_to_baseline
from solvers.deadlock import RULES, Deadlocks
from solvers.solve import ALGORITHMS, BEST, Search

# Budget per search in the browser, where Python runs a few times slower.
NODE_LIMIT, TIME_LIMIT = 200_000, 15.0


class Game:
    def __init__(self):
        self.levels = {entry["id"]: entry for entry in catalog()}
        self.jobs = {}
        self.rows = []              # benchmark rows of the last run
        self.level = None

    # ------------------------------------------------------------ catalogue

    def boot(self):
        return {
            "algorithms": [{"key": key, **algo._asdict()} for key, algo in ALGORITHMS.items()],
            "packs": [{"key": key, "name": name} for key, name in PACKS.items()],
            "levels": [{k: e[k] for k in ("id", "pack", "title", "note")}
                       for e in self.levels.values()],
            "rules": {key: {"name": name, "why": why} for key, (name, why) in RULES.items()},
            "best": BEST,
        }

    # -------------------------------------------------------------- playing

    def open(self, id=None, text=None, title="Custom level"):
        """Start a level from the catalogue (`id`) or from XSB `text`."""
        entry = self.levels[id] if id else {"id": None, "pack": None, "note": "", "title": title}
        self.level, start = parse_level(entry.get("text", text), "" if id else title)
        self.entry = entry
        self.rules = Deadlocks(self.level)
        self.states, self.moves, self.cursor = [start], "", 0
        self.ai_from = None         # timeline index where the AI's moves begin
        self.hints = 0
        self.par = None             # the AI's optimum from the start position
        self.jobs = {"par": Search(self.level, start, BEST, NODE_LIMIT, 5.0)}
        level = self.level
        return {**self.view(), "level": {
            "id": entry["id"], "pack": entry["pack"], "note": entry["note"],
            "title": level.title or entry["title"],
            "width": level.width, "height": level.height, "crates": len(start.boxes),
            "walls": sorted(level.walls), "goals": sorted(level.goals),
            "floor": sorted(level.floor), "dead": self.rules.dead,
            "text": format_level(level, start),
        }}

    def view(self):
        """The current position and everything the sidebar shows about it."""
        state = self.states[self.cursor]
        played = self.moves[:self.cursor]
        deadlock = self.rules.check_state(state.boxes)
        if deadlock:
            rule, crates = deadlock
            name, why = RULES[rule]
            deadlock = {"rule": rule, "name": name, "why": why, "crates": sorted(crates)}
        return {
            "player": state.player, "boxes": sorted(state.boxes),
            "cursor": self.cursor, "length": len(self.moves), "moves": self.moves,
            "pushes": sum(move.isupper() for move in played),
            "last": played[-1:], "solved": is_goal(self.level, state),
            "ai_from": self.ai_from, "hints": self.hints, "deadlock": deadlock,
        }

    def move(self, direction):
        """One keeper step. A blocked step changes nothing."""
        result = apply_move(self.level, self.states[self.cursor], direction)
        if result:
            state, pushed = result
            self._extend(direction.upper() if pushed else direction.lower(), [state])
            self.cursor += 1
        return self.view()

    def _extend(self, moves, states):
        """Replace everything after the cursor with `moves`."""
        del self.states[self.cursor + 1:]
        self.moves = self.moves[:self.cursor] + moves
        self.states += states
        if self.ai_from is not None and self.ai_from > self.cursor:
            self.ai_from = None
        self.jobs.pop("solve", None)
        self.jobs.pop("hint", None)

    def seek(self, cursor):
        self.cursor = max(0, min(int(cursor), len(self.moves)))
        return self.view()

    def undo(self):
        return self.seek(self.cursor - 1)

    def redo(self):
        return self.seek(self.cursor + 1)

    def reset(self):
        self.hints = 0
        return self.seek(0)

    def trails(self):
        """Cells walked by you so far, and by the AI's optimal solution."""
        ai, state = [], self.states[0]
        if self.par and self.par["solved"]:
            ai = [state.player]
            for move in self.par["moves"]:
                state = apply_move(self.level, state, move)[0]
                ai.append(state.player)
        return {"you": [s.player for s in self.states[:self.cursor + 1]], "ai": ai}

    # ------------------------------------------------------------------- AI

    def solve(self, algorithm=BEST):
        """Search from the current position; the solution joins the timeline."""
        self.jobs["solve"] = Search(self.level, self.states[self.cursor], algorithm,
                                    NODE_LIMIT, TIME_LIMIT)
        return {"started": "solve"}

    def hint(self):
        """Find the best next push from the current position."""
        self.hints += 1
        self.jobs["hint"] = Search(self.level, self.states[self.cursor], BEST, NODE_LIMIT, 8.0)
        return {"started": "hint"}

    def race(self):
        """All algorithms from the level's start position, side by side."""
        self.jobs["race"] = Race(self.level, self.states[0],
                                 node_limit=NODE_LIMIT, time_limit=TIME_LIMIT)
        return {"started": "race"}

    def benchmark(self, pack=None, seconds=3.0):
        """Every algorithm on every level of `pack` (all packs if None),
        each search limited to `seconds`."""
        levels = [e for e in self.levels.values() if pack in (None, e["pack"])]
        self.rows = []
        self.jobs["bench"] = Benchmark(levels, node_limit=NODE_LIMIT,
                                       time_limit=min(float(seconds), 30.0))
        return {"started": "bench", "total": len(levels)}

    def report(self, format="csv"):
        return (to_markdown if format == "markdown" else to_csv)(self.rows)

    def cancel(self, job):
        self.jobs.pop(job, None)
        return {"cancelled": job}

    def tick(self, ms=10):
        """Share `ms` milliseconds between the running jobs and report on each.
        A finished job is reported once, then forgotten."""
        reports = {}
        share = ms / 1000 / max(len(self.jobs), 1)
        for name, job in list(self.jobs.items()):
            done = job.advance(share)
            if name not in self.jobs:
                continue                    # replaced or cancelled meanwhile
            reports[name] = getattr(self, f"_report_{name}")(job, done)
            reports[name]["done"] = done
            if done:
                self.jobs.pop(name, None)
        return {"jobs": reports}

    def _report_par(self, search, done):
        if done:
            self.par = search.result
        return _progress(search)

    def _report_solve(self, search, done):
        report = _progress(search)
        if done and search.result["solved"]:
            moves, state, states = search.result["moves"], self.states[self.cursor], []
            for move in moves:
                state = apply_move(self.level, state, move)[0]
                states.append(state)
            self._extend(moves, states)
            self.ai_from = self.cursor
        if done:
            report["view"] = self.view()
        return report

    def _report_hint(self, search, done):
        report = _progress(search)
        if done and search.result["solved"] and search.result["moves"]:
            moves = search.result["moves"]
            first_push = next(i for i, move in enumerate(moves) if move.isupper())
            state = self.states[self.cursor]
            path = [state.player]
            for move in moves[:first_push]:
                state = apply_move(self.level, state, move)[0]
                path.append(state.player)
            step = self.level.steps[moves[first_push]]
            report["hint"] = {"moves": moves[:first_push + 1], "path": path,
                              "box": state.player + step, "to": state.player + 2 * step}
        return report

    def _report_race(self, race, done):
        if done:
            compare_to_baseline(race.results)
        return {"lanes": [_progress(search) for search in race.searches]}

    def _report_bench(self, bench, done):
        fresh = bench.rows[len(self.rows):]
        self.rows = list(bench.rows)
        report = {"rows": [_without_moves(row) for row in fresh],
                  "finished": bench.total - len(bench.pending) - (bench.race is not None),
                  "total": bench.total,
                  "current": bench.entry["title"] if bench.entry else ""}
        if done:
            report["summary"] = summary(self.rows)
        return report

    # --------------------------------------------------------------- editor

    def check(self, text):
        """Validate level text without starting it (LevelError says what is wrong)."""
        level, state = parse_level(text)
        return {"crates": len(state.boxes), "width": level.width, "height": level.height}

    def generate(self, seed=0, width=9, height=8, boxes=3):
        width, height = _clamp(width, 6, 12), _clamp(height, 6, 10)
        boxes = _clamp(boxes, 1, min(5, (width - 2) * (height - 2) // 6))
        return {"text": generate(int(seed), width, height, boxes)}


def _clamp(value, low, high):
    return max(low, min(int(value), high))


def _without_moves(result):
    return {key: value for key, value in result.items() if key != "moves"}


def _progress(search):
    """A search's live counters, plus its result once it has one."""
    stats = search.stats
    state = stats["state"]
    report = {
        "algorithm": search.algorithm,
        "label": ALGORITHMS[search.algorithm].label,
        "stats": {
            "expanded": stats["expanded"], "generated": stats["generated"],
            "frontier": stats["frontier"], "depth": stats["depth"],
            "pruned": sum(stats["pruned"].values()), "time": search.elapsed,
            "player": state.player, "boxes": sorted(state.boxes),
        },
    }
    if search.result:
        report["result"] = search.result
    return report


GAME = Game()


def call(method, payload="{}"):
    """JSON door used by the page: ``call(name, json_arguments) -> json``.
    Problems come back as ``{"error": message}`` instead of exceptions."""
    try:
        if method.startswith("_") or not callable(getattr(Game, method, None)):
            raise LevelError(f"Unknown request: {method}")
        return json.dumps(getattr(GAME, method)(**json.loads(payload)))
    except LevelError as problem:
        return json.dumps({"error": str(problem)})
    except KeyError as missing:
        return json.dumps({"error": f"Unknown level: {missing}"})
