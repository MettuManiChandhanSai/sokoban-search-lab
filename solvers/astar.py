"""
A* search: informed, and optionally deadlock-aware.

Positions are expanded in order of f(n) = g(n) + h(n):

    g(n)  pushes made so far
    h(n)  a lower bound on the pushes still needed (solvers.heuristics)

Because every heuristic used here is consistent, the first time a state
is expanded its g is already minimal, so the solution returned uses the
fewest pushes possible, the same optimum BFS finds. Ties on f go to the
position with the smaller h, i.e. the one closer to the goal.

The same function is "A*" and "A* + Deadlock": pass a
solvers.deadlock.Deadlocks object and every push that breaks a deadlock
rule is discarded before it ever reaches the frontier. Pruning is a
layer on top of A*, not a different search.
"""

from heapq import heappop, heappush
from itertools import count

from engine.state import State, legal_pushes, push, reachable

from .bfs import REPORT_EVERY, trace


def astar(level, start, stats, heuristic, deadlocks=None):
    pruned = stats["pruned"]
    h = heuristic(start.boxes)
    if h is None:
        pruned["matching"] += 1
        return None
    if deadlocks and deadlocks.check_state(start.boxes):
        pruned[deadlocks.check_state(start.boxes)[0]] += 1
        return None

    parents = {}                    # expanded state -> (parent state, push that led here)
    best_g = {start: 0}             # cheapest known way to reach each position
    order = count()                 # tie-breaker: the heap never compares states
    frontier = [(h, h, next(order), 0, start, None, None)]

    while frontier:
        _, h, _, g, position, parent, via = heappop(frontier)

        region = reachable(level, position.boxes, position.player)
        state = State(min(region), position.boxes)
        if state in parents:        # already expanded via a path at least as short
            continue
        parents[state] = (parent, via)
        if state.boxes == level.goals:              # goal test on expansion: optimal
            return trace(parents, state)
        stats["expanded"] += 1

        for box, step in legal_pushes(level, state.boxes, region):
            child = push(state.boxes, box, step)
            if best_g.get(child, g + 2) <= g + 1:
                continue
            if deadlocks:
                rule = deadlocks.after_push(child.boxes, box + step)
                if rule:
                    pruned[rule] += 1
                    continue
            child_h = heuristic(child.boxes)
            if child_h is None:
                pruned["matching"] += 1
                continue
            best_g[child] = g + 1
            stats["generated"] += 1
            heappush(frontier, (g + 1 + child_h, child_h, next(order),
                                g + 1, child, state, (box, step)))

        if not stats["expanded"] % REPORT_EVERY:
            stats.update(frontier=len(frontier), depth=g, state=state)
            yield
    return None
