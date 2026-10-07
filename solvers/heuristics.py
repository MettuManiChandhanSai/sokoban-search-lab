"""
Heuristics: lower bounds on the pushes still needed.

Each factory precomputes its tables once per level and returns
``h(boxes) -> int``, or None when the position provably has no solution.

manhattan(level)
    Sum over crates of the Manhattan distance to the *nearest* goal.
    Every push moves one crate one cell, so this never overestimates
    (admissible), and it changes by at most 1 per push (consistent).
    Its blind spots: it sees through walls, and it lets several crates
    aim for the same goal.

matching(level)
    Fixes both. Distances are true push distances (walls respected, and
    the keeper needs room to stand behind the crate), and every crate
    must take a *different* goal: the cheapest one-to-one assignment,
    found with the Hungarian algorithm. Still admissible and consistent,
    and never smaller than manhattan, so A* expands no more nodes.
"""

from collections import deque

UNREACHABLE = 10 ** 6


def push_distances(level):
    """``{goal: {cell: fewest pushes to bring a lone crate from cell to goal}}``.

    Computed backwards, by *pulling* a crate away from the goal. A cell
    missing from every table is a dead square: no crate standing there
    can ever reach a goal (solvers.deadlock builds on this).
    """
    floor, table = level.floor, {}
    for goal in level.goals:
        dist = {goal: 0}
        queue = deque([goal])
        while queue:
            cell = queue.popleft()
            for step in level.names:
                # a push origin -> cell needs the keeper one further back
                origin, keeper = cell - step, cell - 2 * step
                if origin in floor and keeper in floor and origin not in dist:
                    dist[origin] = dist[cell] + 1
                    queue.append(origin)
        table[goal] = dist
    return table


def manhattan(level):
    goals = [level.xy(goal) for goal in level.goals]
    nearest = {}
    for cell in level.floor:
        x, y = level.xy(cell)
        nearest[cell] = min(abs(x - gx) + abs(y - gy) for gx, gy in goals)
    return lambda boxes: sum(nearest[box] for box in boxes)


def matching(level):
    dist = push_distances(level)
    rows = {cell: [dist[goal].get(cell, UNREACHABLE) for goal in level.goals]
            for cell in level.floor}
    cache = {}

    def h(boxes):
        if boxes not in cache:
            cost = min_assignment([rows[box] for box in boxes])
            cache[boxes] = cost if cost < UNREACHABLE else None
        return cache[boxes]
    return h


def min_assignment(cost):
    """Cheapest way to give each row its own column (Hungarian algorithm,
    O(n^3)). `cost` is a square matrix; returns the total."""
    n = len(cost)
    u, v = [0] * (n + 1), [0] * (n + 1)      # row / column potentials
    match = [0] * (n + 1)                    # match[column] = row (1-based, 0 = free)
    way = [0] * (n + 1)
    for row in range(1, n + 1):
        match[0] = row
        col = 0
        slack = [float("inf")] * (n + 1)
        used = [False] * (n + 1)
        while True:                          # grow an augmenting path from `row`
            used[col] = True
            r, delta, nxt = match[col], float("inf"), 0
            for j in range(1, n + 1):
                if not used[j]:
                    reduced = cost[r - 1][j - 1] - u[r] - v[j]
                    if reduced < slack[j]:
                        slack[j], way[j] = reduced, col
                    if slack[j] < delta:
                        delta, nxt = slack[j], j
            for j in range(n + 1):
                if used[j]:
                    u[match[j]] += delta
                    v[j] -= delta
                else:
                    slack[j] -= delta
            col = nxt
            if match[col] == 0:
                break
        while col:                           # flip the path
            match[col] = match[way[col]]
            col = way[col]
    return -v[0]
