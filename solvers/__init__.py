"""
MODULE 2 · solvers — the AI: four search strategies of growing intelligence.

    bfs.py         uninformed baseline (breadth-first)
    astar.py       informed search, f(n) = g(n) + h(n), optional deadlock pruning
    heuristics.py  Manhattan distance · true push distance · min-cost matching
    deadlock.py    knowledge base: corner, wall-line, dead-square and freeze rules
    solve.py       the algorithm ladder + Search, a pausable handle on one run
    compare.py     run the ladder on one position and measure each rung vs BFS

Every algorithm searches the same push-level state space from
engine.state and minimises the same cost (pushes), so their node counts
are directly comparable.
"""
