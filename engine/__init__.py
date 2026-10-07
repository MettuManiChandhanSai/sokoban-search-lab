"""
MODULE 1 · engine — the rules of Sokoban.

    level.py   static geometry: parse and validate a level, know the floor
    state.py   dynamic state: keeper steps, pushes, the push-level state space

Pure standard-library Python. Nothing in here knows that search
algorithms, a browser or a benchmark exist; every other module builds
on these few functions.
"""
