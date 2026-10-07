# Sokoban Search Lab

**A Heuristic and Deadlock-Aware Search System for Sokoban Puzzle Solving**
CS23533 Foundations of Artificial Intelligence

A playable Sokoban with an AI that solves it four ways, each smarter than the
last, and shows you exactly what each idea buys:

| Rung | Algorithm | What it adds |
| --- | --- | --- |
| 1 | **BFS** | nothing: the uninformed baseline |
| 2 | **A\*** | a heuristic (Manhattan distance) |
| 3 | **A\* + Deadlock** | knowledge: rules that prove a push hopeless |
| 4 | **A\* + Deadlock + Matching** | a sharper heuristic (min-cost crate-to-goal assignment) |

Everything is plain Python (standard library only). The game runs in a web
browser, and the browser runs these same Python files, unchanged.

## Quick start

```bash
python run_game.py         # play at http://localhost:8000
python run_benchmark.py    # every algorithm on every level, table + CSV + Markdown
python -m unittest         # the test suite
```

Python 3.9 or newer. Nothing to install.

## What is in the app

- **Play** – 34 levels in four packs. Undo, redo, restart, timer, push and move
  counters, and the AI's optimum to beat. A deadlock coach names the rule you
  just broke ("Wall-line trap: ...") the moment a level becomes unwinnable.
- **Hint** – the best solver searches from where you stand and marks the next push.
- **Solve** – pick an algorithm and watch it search: the ghost position is the
  state being expanded, the orange tint is where it has tried crates. The answer
  lands on the timeline, where you can replay, step and scrub it.
- **Overlays** – dead squares (point at one to see which rule kills it), the
  search trace, and your path against the optimal one.
- **Race** – all four algorithms on the same level at the same time, with live
  node counts on a log scale, a one-sentence verdict, and three graphs
  afterwards: search steps, solution length and time.
- **Lab** – the benchmark, in the browser: a level-by-algorithm matrix that can
  show search steps, solution length, pushes or time; summary tiles; copy as
  CSV or Markdown.
- **Build** – a level editor with instant validation, and a generator that
  makes new solvable levels.
- **Guide** – how the game, the algorithms and the numbers work, in plain
  words. A first-visit card points new players to it, and every box in the
  app has its own "How this works" line explaining each button.

### The level packs

| Pack | Levels | What it is for |
| --- | ---: | --- |
| Training | 7 | One idea per level: pushing, corners, wall lines, freezes, order |
| Classic nine | 9 | The levels of the first review |
| Warehouse | 9 | Tight generated rooms where deadlock knowledge matters |
| Showdown | 9 | Hard rooms picked so that all four algorithms behave differently |

### Do the algorithms give different answers?

They all report the same number of **pushes**, on purpose: each is guaranteed
to find the fewest possible, which is what makes the comparison fair. What
differs is everything else:

- **search steps** (positions expanded) differ on every hard level, usually by
  a factor of five to ten from one rung to the next;
- **time** follows the search steps;
- **keeper moves** differ wherever several optimal solutions exist. BFS, A\*
  and the matching search usually walk different routes. A\* and
  A\* + Deadlock return the same route, because deadlock rules only remove
  dead ends: same answer, fewer steps to find it.

Keys: arrows or WASD move, `Z` undo, `Y` redo, `R` restart, `H` hint,
`Space` play/pause, `N`/`P` next/previous level.

## Project structure: five modules

```
sokoban_ai_solver/
├── engine/        MODULE 1 · the rules
│   ├── level.py       parse and validate a level (XSB text), floor geometry
│   └── state.py       keeper steps, pushes, the push-level state space, LURD paths
├── solvers/       MODULE 2 · the AI
│   ├── bfs.py         uninformed baseline
│   ├── astar.py       f = g + h, optional deadlock pruning
│   ├── heuristics.py  Manhattan · true push distance · Hungarian matching
│   ├── deadlock.py    corner, wall-line, dead-square and freeze rules
│   ├── solve.py       the algorithm ladder; Search, a pausable run
│   └── compare.py     run all, race, measure against BFS
├── interface/     MODULE 3 · what the player sees
│   ├── bridge.py      the browser's door into Python: session, timeline, jobs
│   ├── site.py        build the static site, serve it locally
│   └── web/           index.html, style.css, render.js, app.js
├── puzzles/       MODULE 4 · the levels
│   ├── library.py     the catalogue: one text file per level, one folder per pack
│   ├── generator.py   new levels by reverse play, graded by the solver
│   └── training/ classic/ warehouse/ showdown/
├── analytics/     MODULE 5 · the evidence
│   ├── benchmark.py   every algorithm on every level, pausable
│   └── report.py      table, CSV, Markdown, per-algorithm summary
├── tests/         unit tests and fuzz tests for all five modules
├── docs/          the built website (this folder is what gets hosted)
├── run_game.py    run_benchmark.py
└── README.md
```

Dependencies point one way: `engine` knows nothing else; `solvers` uses
`engine`; `puzzles` and `analytics` use both; `interface` sits on top.

## How the AI works

### Problem formulation

- **State** – where the crates are, and which region of floor the keeper can
  walk in. Walking changes nothing about the puzzle, so two positions with the
  same crates whose keepers can reach each other are *one* state.
- **Action** – a push: one crate, one cell. The walk needed to get behind the
  crate is found by a flood fill and costs nothing.
- **Goal test** – every crate on a goal.
- **Path cost** – the number of pushes. All four algorithms minimise it, so all
  four return solutions with the same, optimal push count. (Move counts can
  differ between them; the app reports both.)

### The ladder

**BFS** (`solvers/bfs.py`) expands states in order of pushes from the start.
Optimal, and blind.

**A\*** (`solvers/astar.py`) expands by `f = g + h`. `h` is the sum over crates
of the Manhattan distance to the nearest goal. Every push moves one crate one
cell, so `h` never overestimates (admissible) and changes by at most one per
push (consistent). That is what makes A\* optimal here. Ties on `f` go to the
smaller `h`.

**A\* + Deadlock** adds `solvers/deadlock.py`. Before a push enters the
frontier, four rules ask whether it has just lost the game:

| Rule | Fires when |
| --- | --- |
| Corner trap | the crate has a wall on one horizontal and one vertical side |
| Wall-line trap | the crate can only slide along a wall, and no goal lies on that stretch |
| Dead square | no sequence of pushes brings a crate from that square to any goal |
| Freeze deadlock | crates block each other so none can move again, and one is off-goal |

The first three depend only on the level, so they are computed once as a map of
dead squares by pulling a crate backwards from every goal: a square no pull
reaches is dead. The freeze rule is checked on the crate that just moved.

**A\* + Deadlock + Matching** replaces the heuristic. Manhattan distance has
two blind spots: it sees through walls, and it lets every crate aim at the same
goal. The matching heuristic uses true push distances and gives each crate its
own goal, choosing the cheapest assignment with the Hungarian algorithm. It is
still admissible and consistent, and never smaller than Manhattan, so it can
only expand fewer states. When no assignment exists the position is unsolvable,
which makes it a fifth deadlock test for free.

### Why you can trust the results

`tests/test_solvers.py` and `tests/test_puzzles.py` check this with fuzzing
rather than argument:

- on hundreds of random positions, all four algorithms report the same optimal
  push count, or all report "unsolvable";
- every position the deadlock rules flag is confirmed unsolvable by exhaustive
  BFS, so pruning never discards a solution;
- neither heuristic ever exceeds the true optimum;
- the Hungarian implementation matches brute force on random matrices.

## Results

Measured on this project's 34 levels with `python run_benchmark.py
--node-limit 200000 --time-limit 20` (Python 3.11, one laptop core).

**Totals over all 34 levels**

| Algorithm | Levels solved | Positions expanded | Time | Median saving vs BFS |
| --- | ---: | ---: | ---: | ---: |
| BFS | 27 / 34 | 1,585,175 | 193.9 s | baseline |
| A\* | 33 / 34 | 479,526 | 61.2 s | 84.1% fewer |
| A\* + Deadlock | 34 / 34 | 225,947 | 40.8 s | 92.6% fewer |
| A\* + Deadlock + Matching | 34 / 34 | 4,930 | 0.9 s | 99.5% fewer |

**Search steps: positions expanded** (selected levels, then the whole Showdown pack)

| Level | Crates | Optimal pushes | BFS | A\* | A\* + Deadlock | A\* + Deadlock + Matching |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dead-end Lane | 3 | 15 | 2,046 | 262 | 42 | 15 |
| Storeroom | 3 | 12 | 9,952 | 67 | 65 | 13 |
| Night Shift | 3 | 18 | 6,189 | 2,377 | 515 | 20 |
| Pallet Maze | 4 | 18 | 52,833 | 11,220 | 4,156 | 518 |
| Aisle Nine | 4 | 14 | 20,170 | 2,298 | 928 | 165 |
| Double Stack | 4 | 15 | 36,971 | 2,273 | 964 | 35 |
| Tight Turn | 4 | 15 | 38,746 | 3,822 | 1,340 | 31 |
| Long Haul | 4 | 19 | 39,882 | 8,952 | 5,350 | 130 |
| Bottleneck | 4 | 16 | 66,692 | 3,293 | 1,715 | 31 |
| Four-way Stop | 4 | 18 | 59,926 | 11,336 | 5,078 | 1,365 |
| Dead Stock | 4 | 21 | 77,568 | 23,707 | 2,969 | 79 |
| Backlog | 5 | 17 | gave up at 200,000 | 18,343 | 7,907 | 532 |
| Rush Hour | 6 | 21 | gave up at 188,064 | 107,759 | 38,453 | 344 |

**Solution length: keeper moves** (Showdown pack; the push count is the same in every finished cell of a row)

| Level | Pushes | BFS | A\* | A\* + Deadlock | A\* + Deadlock + Matching |
| --- | ---: | ---: | ---: | ---: | ---: |
| Aisle Nine | 14 | 40 | 61 | 61 | 37 |
| Double Stack | 15 | 75 | 54 | 54 | 77 |
| Tight Turn | 15 | 44 | 45 | 45 | 46 |
| Long Haul | 19 | 72 | 73 | 73 | 77 |
| Bottleneck | 16 | 73 | 68 | 68 | 71 |
| Four-way Stop | 18 | 45 | 63 | 63 | 35 |
| Dead Stock | 21 | 104 | 117 | 117 | 104 |
| Backlog | 17 | gave up | 88 | 88 | 93 |
| Rush Hour | 21 | gave up | 81 | 81 | 87 |

Where an algorithm gave up, its true cost is higher than shown, so the savings
above are lower bounds. Full table: `analytics/results/benchmark.md` after a run.

## What changed since Review 1

Reviewing the first version turned up eight problems. Each is fixed and tested.

| Found in the first version | Now |
| --- | --- |
| Positions with the same crates and a keeper standing in a different spot were treated as different states, so every search did several times the work. | States are identified by crates plus keeper region. Level 1 BFS went from 62,560 expanded nodes to 9,952, and A\* from 1,000 to 67. On the three large open levels A\* needed between 2,204 and 6,042 nodes; it now needs 12 to 14. |
| The search minimised pushes but the report called the *move* count optimal. On level 4 BFS returned 36 moves and A\* 31. | Pushes are the stated cost. Pushes and moves are reported separately, and a test checks that every algorithm agrees on pushes. |
| The Manhattan heuristic was described as "not strictly admissible". | It is admissible and consistent for push cost; the argument is above and a test backs it. |
| Deadlock rules were re-derived for every crate in every state, and on eight of nine levels they pruned nothing, so A\* + Deadlock was slower than A\*. | Rules are precomputed per level, a freeze rule was added, and the warehouse pack has rooms where pruning removes most of the search. |
| Speed-ups such as "39,121,151x faster" came from dividing by a timer that read zero. | High-resolution timing that includes each algorithm's set-up. |
| When BFS timed out its row was blank and the comparison was lost. | The saving is reported as a lower bound. |
| A level was accepted if crates and goals matched in number. | Levels must have one keeper, be enclosed, and have every crate and goal reachable; the editor shows the reason when one is not. |
| Desktop-only pygame window with a 5 MB music file. | A web app, as the zeroth review planned (Python solver, HTML/CSS/JS interface), with synthesised sound effects and no dependencies. |

## Novelty

What the reviews promised, and what now delivers it:

1. **Progressive search improvement** – a four-rung ladder in which each rung
   adds exactly one idea, so the gap between two rows of any table is the value
   of that idea. The fourth rung (matching) is new.
2. **Explainable deadlock knowledge** – every pruned push is attributed to the
   rule that proved it hopeless; the same rules drive the dead-square overlay
   and warn a human player in real time.
3. **Search made visible** – solvers are pausable generators, so the page can
   draw the state under examination while the search runs, and interleave four
   searches into a live race.
4. **Human versus AI** – your pushes, moves and time against the optimum, and
   your route drawn over the optimal one.
5. **Custom and generated levels** – an editor, plus a generator that plays the
   game backwards from the solved position (so every level is solvable) and
   uses the solver to keep the hardest candidate.
6. **One implementation everywhere** – the command line, the tests and the
   browser run the same Python files. The browser does it through Pyodide
   (CPython compiled to WebAssembly); there is no server and no second copy of
   the algorithms in JavaScript.

## Hosting

`docs/` is a complete static website. Any static host works.

**GitHub Pages**

1. Push this repository to GitHub.
2. Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder `/docs`.
3. The site appears at `https://<user>.github.io/<repository>/`.

**Netlify** – drag the `docs` folder onto <https://app.netlify.com/drop>.

After changing any Python or web file, run `python run_game.py --build-only`
so `docs/` matches the sources (a test fails if you forget).

### The Python runtime in the browser

`docs/pyodide/` holds Pyodide 314.0.7 (Python 3.14.2), unmodified, from the
official npm package; Pyodide is licensed under the MPL-2.0. Its standard
library is stored as plain text (`python_stdlib.json`) and packed into the
archive Pyodide expects when the page starts, because some hosts will not serve
`.zip` files. To install a different release:

```bash
npm pack pyodide@314.0.7
tar -xzf pyodide-314.0.7.tgz
python run_game.py --vendor package --build-only
```

## Adding a level

Create `puzzles/<pack>/<nn_name>.txt`:

```
; Title
; A note shown to the player.
#####
#@$.#
#####
```

`#` wall, `$` crate, `.` goal, `@` keeper, `*` crate on goal, `+` keeper on
goal. It shows up in the game, the benchmark and the tests automatically.

## References

1. P. E. Hart, N. J. Nilsson, B. Raphael, "A Formal Basis for the Heuristic Determination of Minimum Cost Paths", IEEE Trans. Systems Science and Cybernetics 4(2), 1968.
2. J. C. Culberson, "Sokoban is PSPACE-complete", University of Alberta TR97-02, 1997.
3. A. Junghanns, J. Schaeffer, "Sokoban: Enhancing General Single-Agent Search Methods Using Domain Knowledge", Artificial Intelligence 129, 2001.
4. A. Botea, M. Müller, J. Schaeffer, "Using Abstraction for Planning in Sokoban", Computers and Games, 2002.
5. H. W. Kuhn, "The Hungarian Method for the Assignment Problem", Naval Research Logistics Quarterly 2, 1955.
