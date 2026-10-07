"""
Breadth-first search: the uninformed baseline.

Explores positions in order of the number of pushes from the start, so
the first solution it meets uses the fewest pushes possible. It has no
idea which positions look promising and no idea which are hopeless;
that blindness is exactly what the other algorithms are measured
against.

Like every solver here it is a generator: it yields now and then so the
caller can pause it, draw its progress or run a rival for a while (see
solve.Search), and finally returns the push list, or None if the whole
space was exhausted without a solution.
"""

from collections import deque

from engine.state import arrivals, legal_pushes, push, reachable

REPORT_EVERY = 32       # expansions between two yields


def bfs(level, start, stats):
    if start.boxes == level.goals:
        return []
    parents = {start: (None, None)}     # expanded position -> (parent, push that led here)
    queued = {start}                    # every position ever put in the queue
    closed = set()                      # every way of arriving in an expanded state
    frontier = deque([(start, 0)])

    while frontier:
        position, depth = frontier.popleft()
        if position in closed:          # same crates, same keeper region: done before
            continue
        region = reachable(level, position.boxes, position.player)
        closed.update(arrivals(level, position.boxes, region))
        stats["expanded"] += 1

        for box, step in legal_pushes(level, position.boxes, region):
            child = push(position.boxes, box, step)
            if child in queued or child in closed:
                continue
            queued.add(child)
            parents[child] = (position, (box, step))
            stats["generated"] += 1
            if child.boxes == level.goals:          # goal test on generation
                return trace(parents, child)
            frontier.append((child, depth + 1))

        if not stats["expanded"] % REPORT_EVERY:
            stats.update(frontier=len(frontier), depth=depth, state=position)
            yield
    return None


def trace(parents, position):
    """Follow parent links back to the start: the pushes in playing order."""
    pushes = []
    while parents[position][0] is not None:
        position, via = parents[position]
        pushes.append(via)
    return pushes[::-1]
