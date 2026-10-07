"""
Dynamic state and the transition model.

A State is ``(player, boxes)``: the keeper's cell and a frozenset of
crate cells. It is immutable and hashable, so it drops straight into a
set or dict for visited-state tracking.

Two views of the same game live here:

*   **Steps** (apply_move) — what a human does: one cell at a time.
*   **Pushes** (reachable + legal_pushes) — what the solvers search.
    Walking never changes the puzzle, only pushes do, so a search node
    is "which crates are where, and which region can the keeper walk
    in". One flood fill finds that region; every crate the keeper can
    get behind is one action. This shrinks the state space enormously
    compared with searching single steps.

Solutions are written in standard LURD notation: lower case = walk,
UPPER CASE = push (e.g. ``rrdL``).
"""

from collections import deque, namedtuple

State = namedtuple("State", "player boxes")


def is_goal(level, state):
    """Goal test: every crate rests on a goal."""
    return state.boxes == level.goals


def apply_move(level, state, move):
    """One keeper step in direction U/D/L/R (any case).

    Returns ``(new_state, pushed)``, or None when a wall or a second
    crate is in the way.
    """
    step = level.steps[move.upper()]
    to = state.player + step
    if to not in level.floor:
        return None
    if to not in state.boxes:
        return State(to, state.boxes), False
    beyond = to + step
    if beyond not in level.floor or beyond in state.boxes:
        return None
    return State(to, state.boxes - {to} | {beyond}), True


def replay(level, state, moves):
    """Apply a whole LURD string; raises ValueError on an illegal move."""
    for i, move in enumerate(moves):
        result = apply_move(level, state, move)
        if result is None:
            raise ValueError(f"Move {i + 1} ({move}) is blocked.")
        state = result[0]
    return state


def reachable(level, boxes, start):
    """Every cell the keeper can walk to from `start` without pushing."""
    neighbours = level.neighbours
    seen, stack = {start}, [start]
    while stack:
        for cell in neighbours[stack.pop()]:
            if cell not in seen and cell not in boxes:
                seen.add(cell)
                stack.append(cell)
    return seen


def legal_pushes(level, boxes, region):
    """``(box, step)`` for every push available to a keeper in `region`:
    the keeper must be able to stand behind the crate, and the cell
    beyond it must be free floor."""
    floor = level.floor
    return [(box, step)
            for box in boxes
            for step in level.names
            if box - step in region
            and box + step in floor and box + step not in boxes]


def push(boxes, box, step):
    """The state right after pushing `box` one cell: the keeper ends up
    where the crate was."""
    return State(box, boxes - {box} | {box + step})


def walk(level, boxes, start, target):
    """Shortest keeper walk from `start` to `target` as a lower-case move
    string (breadth-first, so it is the fewest steps), or None."""
    came = {start: None}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        if cell == target:
            path = []
            while came[cell] is not None:
                cell, name = came[cell]
                path.append(name)
            return "".join(reversed(path)).lower()
        for step, name in level.names.items():
            nxt = cell + step
            if nxt in level.floor and nxt not in boxes and nxt not in came:
                came[nxt] = (cell, name)
                queue.append(nxt)
    return None


def pushes_to_moves(level, state, pushes):
    """Expand a push sequence ``[(box, step), ...]`` into the full LURD
    move string a keeper would actually play."""
    moves = ""
    for box, step in pushes:
        moves += walk(level, state.boxes, state.player, box - step)
        moves += level.names[step]
        state = push(state.boxes, box, step)
    return moves
