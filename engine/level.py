"""
Static level geometry: everything about a puzzle that never changes
while it is played or solved.

A cell is a plain int, ``cell = y * width + x``, so one step is one
addition (UP = -width, DOWN = +width, LEFT = -1, RIGHT = +1). Every
level must be enclosed by walls, which is what makes that arithmetic
safe: a floor cell always has four in-bounds neighbours.

Level text uses the standard XSB symbols:

    #  wall        $  crate            @  keeper
    .  goal        *  crate on goal    +  keeper on goal
    (space, - or _)  floor             ;  comment (the first one is the title)
"""

from .state import State

SYMBOLS = "# -_.$*@+"


class LevelError(ValueError):
    """The level text breaks a rule of Sokoban. The message is shown to players."""


class Level:
    def __init__(self, width, height, walls, goals, floor, title=""):
        self.width, self.height, self.title = width, height, title
        self.walls = frozenset(walls)
        self.goals = frozenset(goals)
        # floor = the cells the keeper could ever stand on (the enclosed interior)
        self.floor = frozenset(floor)
        self.steps = {"U": -width, "D": width, "L": -1, "R": 1}
        self.names = {step: name for name, step in self.steps.items()}
        self.neighbours = {cell: tuple(cell + step for step in self.names
                                       if cell + step in self.floor)
                           for cell in self.floor}

    def xy(self, cell):
        return cell % self.width, cell // self.width


def parse_level(text, title=""):
    """Turn XSB text into ``(Level, State)``, or raise LevelError saying why not."""
    rows = []
    for line in text.splitlines():
        if line.lstrip().startswith(";"):
            title = title or line.strip(" ;\t")
        elif line.strip():
            rows.append(line.rstrip())
    if not rows:
        raise LevelError("The level is empty.")

    width, height = max(map(len, rows)), len(rows)
    walls, goals, boxes, keepers = set(), set(), set(), []
    for y, row in enumerate(rows):
        for x, symbol in enumerate(row):
            cell = y * width + x
            if symbol not in SYMBOLS:
                raise LevelError(f"Unknown symbol {symbol!r} in row {y + 1}.")
            if symbol == "#":
                walls.add(cell)
            if symbol in ".*+":
                goals.add(cell)
            if symbol in "$*":
                boxes.add(cell)
            if symbol in "@+":
                keepers.append(cell)

    if len(keepers) != 1:
        raise LevelError(f"A level needs exactly one keeper, found {len(keepers)}.")
    if not boxes:
        raise LevelError("A level needs at least one crate.")
    if len(boxes) != len(goals):
        raise LevelError(f"{len(boxes)} crates but {len(goals)} goals: "
                         "the counts must match.")

    floor = _interior(keepers[0], walls, width, height)
    if not boxes <= floor:
        raise LevelError("A crate is walled off from the keeper.")
    if not goals <= floor:
        raise LevelError("A goal is walled off from the keeper.")

    return (Level(width, height, walls, goals, floor, title),
            State(keepers[0], frozenset(boxes)))


def _interior(start, walls, width, height):
    """Flood-fill from the keeper; leaking to the edge means a missing wall."""
    seen, stack = {start}, [start]
    while stack:
        cell = stack.pop()
        x, y = cell % width, cell // width
        if x in (0, width - 1) or y in (0, height - 1):
            raise LevelError("The level is not enclosed by walls.")
        for neighbour in (cell - width, cell + width, cell - 1, cell + 1):
            if neighbour not in seen and neighbour not in walls:
                seen.add(neighbour)
                stack.append(neighbour)
    return seen


def format_level(level, state):
    """The XSB text of a position: the inverse of parse_level."""
    rows = []
    for y in range(level.height):
        row = ""
        for cell in range(y * level.width, (y + 1) * level.width):
            goal = cell in level.goals
            if cell in level.walls:
                row += "#"
            elif cell in state.boxes:
                row += "*" if goal else "$"
            elif cell == state.player:
                row += "+" if goal else "@"
            else:
                row += "." if goal else " "
        rows.append(row.rstrip())
    return "\n".join(rows)
