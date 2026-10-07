"""
Procedural level generator: solvable by construction, graded by search.

Sokoban played backwards is easy: start from the *solved* position and
let the keeper *pull* crates away from the goals. Every pull is the
reverse of a legal push, so whatever position comes out can be solved
by pushing everything back.

Random pulling alone tends to make dull levels, so this is generate and
test: scramble several candidate rooms, let the solver find the optimal
solution of each, and keep the one that needs the most pushes.
"""

import random

from engine.level import Level, LevelError, format_level, parse_level
from engine.state import State, reachable
from solvers.solve import solve


def generate(seed=0, width=9, height=8, boxes=3, candidates=12):
    """XSB text of a random level; the same arguments always give the same level."""
    rng = random.Random(f"{seed}/{width}/{height}/{boxes}")
    best, best_pushes = None, 0
    tried = 0
    while tried < candidates or best is None:
        tried += 1
        if tried > 500:
            raise ValueError("That room is too small for that many crates.")
        position = _scramble(rng, width, height, boxes)
        if position is None:
            continue
        result = solve(*position, node_limit=5_000)
        if result["solved"] and result["n_pushes"] > best_pushes:
            best, best_pushes = position, result["n_pushes"]
    return f"; Generated #{seed}\n; Built by reverse play. " \
           f"Fewest pushes: {best_pushes}.\n{format_level(*best)}"


def _scramble(rng, width, height, n_boxes):
    """One candidate: a random room, goals, and a random walk of pulls."""
    inside = [y * width + x for y in range(1, height - 1) for x in range(1, width - 1)]
    pillars = set(rng.sample(inside, len(inside) // 6))
    free = [cell for cell in inside if cell not in pillars]
    if len(free) < 2 * n_boxes + 2:
        return None
    rng.shuffle(free)
    goals, keeper = set(free[:n_boxes]), free[n_boxes]

    rows = []
    for y in range(height):
        cells = range(y * width, (y + 1) * width)
        rows.append("".join("*" if c in goals else "@" if c == keeper
                            else " " if c in free else "#" for c in cells))
    try:
        level, state = parse_level("\n".join(rows))
    except LevelError:              # a pillar walled a goal off; try another room
        return None
    # floor the keeper can never reach becomes solid wall
    level = Level(width, height, set(range(width * height)) - level.floor,
                  level.goals, level.floor)

    boxes, player = set(state.boxes), state.player
    for _ in range(rng.randint(8 * n_boxes, 30 * n_boxes)):
        region = reachable(level, boxes, player)
        # to pull crate b one cell the keeper stands next to it and steps back
        pulls = [(b, step) for b in boxes for step in level.names
                 if b + step in region
                 and b + 2 * step in level.floor and b + 2 * step not in boxes]
        if not pulls:
            break
        box, step = rng.choice(pulls)
        boxes.remove(box)
        boxes.add(box + step)
        player = box + 2 * step
    if boxes & level.goals:         # every crate should need moving
        return None
    return level, State(player, frozenset(boxes))
