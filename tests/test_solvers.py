import itertools
import random
import unittest

from engine.level import parse_level
from engine.state import State, is_goal, legal_pushes, push, reachable, replay
from solvers.compare import Race, compare_to_baseline, run_all
from solvers.deadlock import Deadlocks, corner_squares, wall_line_squares
from solvers.heuristics import manhattan, matching, min_assignment, push_distances
from solvers.solve import ALGORITHMS, Search, solve

ROOMS = [
    # two crates, open room
    "########\n#      #\n#  $ $ #\n#  .   #\n#     .#\n#  @   #\n########",
    # tight: corners and wall lines everywhere
    "#######\n#.  ###\n# $   #\n#  #$ #\n#@   .#\n#######",
    # three crates around a pillar, goals along the bottom wall
    "########\n#   #  #\n# $ $  #\n#  #$  #\n#@ ... #\n########",
    # goals tucked into a pocket below the room
    "#########\n#       #\n# $ $ @ #\n####  ###\n   #..#\n   ####",
]


def random_position(level, state, rng, pushes):
    """Play `pushes` random legal pushes from `state`."""
    for _ in range(pushes):
        region = reachable(level, state.boxes, state.player)
        options = legal_pushes(level, state.boxes, region)
        if not options:
            break
        state = push(state.boxes, *rng.choice(options))
    return state


class Assignment(unittest.TestCase):
    def test_matches_brute_force(self):
        rng = random.Random(1)
        for n in range(1, 6):
            for _ in range(40):
                cost = [[rng.randint(0, 20) for _ in range(n)] for _ in range(n)]
                best = min(sum(cost[i][p[i]] for i in range(n))
                           for p in itertools.permutations(range(n)))
                self.assertEqual(min_assignment(cost), best)


class Solving(unittest.TestCase):
    def test_every_algorithm_returns_a_playable_solution(self):
        level, state = parse_level(ROOMS[0])
        for key in ALGORITHMS:
            with self.subTest(key):
                result = solve(level, state, key)
                self.assertEqual(result["status"], "solved")
                self.assertTrue(is_goal(level, replay(level, state, result["moves"])))
                self.assertEqual(result["n_pushes"],
                                 sum(m.isupper() for m in result["moves"]))

    def test_all_algorithms_agree_on_the_fewest_pushes(self):
        # BFS is optimal by construction, so agreement proves that the
        # heuristics are admissible and the deadlock rules never prune a
        # position that could still be solved.
        rng = random.Random(7)
        for text in ROOMS:
            level, start = parse_level(text)
            positions = [start] + [random_position(level, start, rng, rng.randint(1, 6))
                                   for _ in range(25)]
            for state in positions:
                outcomes = {key: (r["status"], r["n_pushes"])
                            for key in ALGORITHMS
                            for r in [solve(level, state, key)]}
                self.assertEqual(len(set(outcomes.values())), 1, (text, state, outcomes))

    def test_a_solved_position_needs_no_pushes(self):
        level, state = parse_level("#####\n#@ *#\n#####")
        self.assertEqual(solve(level, state, "bfs")["moves"], "")
        self.assertEqual(solve(level, state, "astar")["moves"], "")

    def test_unsolvable_levels_are_reported_as_such(self):
        level, state = parse_level("#####\n#$ @#\n#  .#\n#####")   # crate starts in a corner
        self.assertEqual(solve(level, state, "bfs")["status"], "unsolvable")
        pruned = solve(level, state, "astar_deadlock")
        self.assertEqual(pruned["status"], "unsolvable")
        self.assertEqual(pruned["expanded"], 0)       # rejected before searching at all

    def test_informed_search_expands_fewer_nodes(self):
        level, state = parse_level(ROOMS[2])
        nodes = {key: solve(level, state, key)["expanded"] for key in ALGORITHMS}
        self.assertLess(nodes["astar"], nodes["bfs"])
        self.assertLessEqual(nodes["astar_deadlock"], nodes["astar"])
        self.assertLessEqual(nodes["astar_matching"], nodes["astar_deadlock"])

    def test_node_limit_stops_the_search(self):
        level, state = parse_level(ROOMS[2])
        result = solve(level, state, "bfs", node_limit=10)
        self.assertEqual(result["status"], "node_limit")
        self.assertFalse(result["solved"])

    def test_time_sliced_search_gives_the_same_answer(self):
        level, state = parse_level(ROOMS[2])
        search = Search(level, state, "bfs")
        slices = 0
        while not search.advance(0.0005):
            slices += 1
            self.assertGreater(search.stats["expanded"], 0)
        self.assertGreater(slices, 1)
        self.assertEqual(search.result["n_pushes"], solve(level, state, "bfs")["n_pushes"])


class Heuristics(unittest.TestCase):
    def test_push_distance_respects_walls(self):
        # goal in the top-left corner: a crate two cells to its right can
        # be pushed straight in, one below-right needs to go round.
        level, _ = parse_level("######\n#.   #\n#  $ #\n#   @#\n######")
        goal = next(iter(level.goals))
        dist = push_distances(level)[goal]
        self.assertEqual(dist[goal + 2], 2)
        self.assertNotIn(4 * level.width - 2, dist)     # bottom-right corner: stuck

    def test_heuristics_never_overestimate(self):
        rng = random.Random(3)
        for text in ROOMS:
            level, start = parse_level(text)
            estimates = [manhattan(level), matching(level)]
            for _ in range(20):
                state = random_position(level, start, rng, rng.randint(0, 5))
                best = solve(level, state, "bfs")
                if best["solved"]:
                    for h in estimates:
                        self.assertLessEqual(h(state.boxes), best["n_pushes"])

    def test_matching_is_at_least_as_informed_as_manhattan(self):
        for text in ROOMS:
            level, start = parse_level(text)
            self.assertGreaterEqual(matching(level)(start.boxes), manhattan(level)(start.boxes))


class DeadlockRules(unittest.TestCase):
    def test_corner_and_wall_line_squares(self):
        level, _ = parse_level("#######\n#     #\n#  $  #\n#    .#\n#@    #\n#######")
        w = level.width
        top_left, top_mid, right_mid = w + 1, w + 3, 3 * w + 5
        self.assertIn(top_left, corner_squares(level))
        self.assertIn(top_mid, wall_line_squares(level))        # top wall: no goal on it
        self.assertNotIn(right_mid, wall_line_squares(level))   # right wall holds the goal
        dead = Deadlocks(level).dead
        self.assertEqual(dead[top_left], "corner")
        self.assertEqual(dead[top_mid], "wall-line")
        self.assertNotIn(right_mid, dead)

    def test_hand_written_rules_agree_with_the_pull_analysis(self):
        for text in ROOMS:
            level, _ = parse_level(text)
            self.assertLessEqual(corner_squares(level) | wall_line_squares(level),
                                 set(Deadlocks(level).dead))

    def test_freeze_deadlock_two_crates_against_a_wall(self):
        level, state = parse_level("#######\n# $$  #\n#     #\n#@ .. #\n#######")
        rule, crates = Deadlocks(level).check_state(state.boxes)
        self.assertIn(rule, ("freeze", "wall-line"))
        level, state = parse_level("#######\n#     #\n# $$  #\n# $$  #\n#@....#\n#######")
        rule, crates = Deadlocks(level).check_state(state.boxes)
        self.assertEqual(rule, "freeze")                        # 2x2 block in open floor
        self.assertEqual(crates, state.boxes)

    def test_frozen_crates_on_goals_are_fine(self):
        level, state = parse_level("######\n#**  #\n#  $.#\n#@   #\n######")
        self.assertIsNone(Deadlocks(level).check_state(state.boxes))

    def test_flagged_positions_are_truly_unsolvable(self):
        rng = random.Random(11)
        flagged = 0
        for text in ROOMS:
            level, start = parse_level(text)
            rules = Deadlocks(level)
            for _ in range(150):
                state = random_position(level, start, rng, rng.randint(1, 8))
                if rules.check_state(state.boxes):
                    flagged += 1
                    self.assertEqual(solve(level, state, "bfs")["status"], "unsolvable",
                                     (text, state))
        self.assertGreater(flagged, 50)     # the fuzz actually exercises the rules


class Comparison(unittest.TestCase):
    def test_baseline_comparison(self):
        level, state = parse_level(ROOMS[2])
        results = compare_to_baseline(run_all(level, state))
        by_key = {r["algorithm"]: r for r in results}
        self.assertEqual(by_key["bfs"]["node_reduction"], 0.0)
        self.assertGreater(by_key["astar_matching"]["node_reduction"], 50.0)
        self.assertGreater(by_key["astar_matching"]["speedup"], 1.0)

    def test_race_interleaves_and_finishes_everyone(self):
        level, state = parse_level(ROOMS[2])
        race = Race(level, state)
        while not race.advance(0.002):
            pass
        self.assertEqual({r["status"] for r in race.results}, {"solved"})
        self.assertEqual(len({r["n_pushes"] for r in race.results}), 1)


if __name__ == "__main__":
    unittest.main()
