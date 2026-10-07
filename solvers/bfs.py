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

from engine.state import State, legal_pushes, push, reachable

REPORT_EVERY = 32       # expansions between two yields


def bfs(level, start, stats):
    if start.boxes == level.goals:
        return []
    parents = {}                    # expanded state -> (parent state, push that led here)
    queued = {start}                # every position ever put in the queue
    frontier = deque([(start, None, None, 0)])

    while frontier:
        position, parent, via, depth = frontier.popleft()

        # Normalise: two positions with the same crates whose keepers can
        # walk to each other are the same search state.
        region = reachable(level, position.boxes, position.player)
        state = State(min(region), position.boxes)
        if state in parents:
            continue
        parents[state] = (parent, via)
        stats["expanded"] += 1

        for box, step in legal_pushes(level, state.boxes, region):
            child = push(state.boxes, box, step)
            if child in queued:
                continue
            queued.add(child)
            stats["generated"] += 1
            if child.boxes == level.goals:          # goal test on generation
                return trace(parents, state) + [(box, step)]
            frontier.append((child, state, (box, step), depth + 1))

        if not stats["expanded"] % REPORT_EVERY:
            stats.update(frontier=len(frontier), depth=depth, state=state)
            yield
    return None


def trace(parents, state):
    """Follow parent links back to the start: the pushes in playing order."""
    pushes = []
    while parents[state][0] is not None:
        state, via = parents[state]
        pushes.append(via)
    return pushes[::-1]
