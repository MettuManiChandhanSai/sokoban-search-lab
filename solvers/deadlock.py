"""
Deadlock detection: the knowledge-based layer.

A deadlock is a position from which the puzzle can never be solved,
whatever happens next. Each rule below is a logical rule of the form
"IF <pattern around a crate> THEN <unsolvable>". All of them are
*sound*: they only fire on positions that are truly lost, so pruning
with them can never throw away a solution (tests/test_solvers.py checks
this against exhaustive search).

Static rules (depend only on the level, precomputed once as a map of
"dead squares" a crate must never be pushed onto):

    corner      a wall on one horizontal AND one vertical side
    wall-line   the crate can only slide along a wall, and that whole
                stretch of wall holds no goal
    no-path     the general case: no sequence of pushes brings a crate
                from here to any goal (found by pulling crates backwards
                from the goals, see heuristics.push_distances)

Dynamic rule (depends on the other crates, checked after every push):

    freeze      crates that block each other so that none can ever move
                again, with at least one of them off-goal

"matching" is listed for completeness: it is detected by the matching
heuristic, not here.
"""

from .heuristics import push_distances

RULES = {
    "corner": ("Corner trap",
               "A crate wedged into a corner can never be pushed again."),
    "wall-line": ("Wall-line trap",
                  "Against this wall the crate can only slide sideways, "
                  "and no goal lies anywhere along it."),
    "no-path": ("Dead square",
                "No sequence of pushes can bring a crate from this square to any goal."),
    "freeze": ("Freeze deadlock",
               "These crates block each other. None of them can ever move again."),
    "matching": ("No assignment",
                 "The crates cannot each reach a goal of their own."),
}


def corner_squares(level):
    floor, w = level.floor, level.width
    return {c for c in floor - level.goals
            if (c - w not in floor or c + w not in floor)
            and (c - 1 not in floor or c + 1 not in floor)}


def wall_line_squares(level):
    """Cells on a straight run of floor that is closed at both ends, has a
    wall beside every cell (so a crate can never leave the line) and
    contains no goal."""
    floor, dead = level.floor, set()
    for along, across in ((1, level.width), (level.width, 1)):
        for start in floor:
            if start - along in floor:
                continue                        # not the first cell of its run
            run = [start]
            while run[-1] + along in floor:
                run.append(run[-1] + along)
            pinned = all(c - across not in floor or c + across not in floor for c in run)
            if pinned and not level.goals.intersection(run):
                dead.update(run)
    return dead


class Deadlocks:
    """The rules, precomputed for one level."""

    def __init__(self, level):
        self.level = level
        alive = set().union(*push_distances(level).values())
        corners, lines = corner_squares(level), wall_line_squares(level)
        # dead square -> the most specific rule that explains it
        self.dead = {cell: "corner" if cell in corners
                     else "wall-line" if cell in lines else "no-path"
                     for cell in level.floor - alive}

    def after_push(self, boxes, box):
        """The rule broken by the crate just pushed onto `box`, or None.
        Assumes the position before the push was not already deadlocked."""
        if box in self.dead:
            return self.dead[box]
        cluster = self.frozen(boxes, box)
        if cluster and not cluster <= self.level.goals:
            return "freeze"
        return None

    def check_state(self, boxes):
        """``(rule, crates involved)`` for a whole position, or None."""
        for box in boxes:
            if box in self.dead:
                return self.dead[box], frozenset({box})
        for box in boxes:
            cluster = self.frozen(boxes, box)
            if cluster and not cluster <= self.level.goals:
                return "freeze", frozenset(cluster)
        return None

    def frozen(self, boxes, box, assumed=None):
        """The set of crates proven immovable together with `box`, or None
        if `box` can still move.

        A crate is frozen when it is blocked along both axes. An axis is
        blocked by a wall on either side, by dead squares on both sides,
        or by a neighbouring crate that is itself frozen. Crates already
        on the current chain of reasoning (`assumed`) count as walls;
        that is what lets a ring of crates that hold each other in place
        be recognised.
        """
        floor = self.level.floor
        assumed = (assumed or frozenset()) | {box}
        cluster = {box}
        for axis in (1, self.level.width):
            a, b = box - axis, box + axis
            if a not in floor or b not in floor:
                continue                                    # wall
            if a in self.dead and b in self.dead:
                continue                                    # nowhere safe to go
            for neighbour in (a, b):
                if neighbour in boxes:
                    held = (set() if neighbour in assumed
                            else self.frozen(boxes, neighbour, assumed))
                    if held is not None:
                        cluster |= held
                        break
            else:
                return None                                 # this axis is free
        return cluster
