import unittest

from engine.level import LevelError, format_level, parse_level
from engine.state import (State, apply_move, is_goal, legal_pushes,
                          pushes_to_moves, reachable, replay)

CORRIDOR = """
#####
#@$.#
#####
"""

# The keeper starts on the wrong side of the crate and has to walk round.
DETOUR = """
; Detour
#######
#     #
# .$@ #
#     #
#######
"""


class ParseLevel(unittest.TestCase):
    def test_reads_walls_goals_crates_and_keeper(self):
        level, state = parse_level(CORRIDOR)
        self.assertEqual((level.width, level.height), (5, 3))
        self.assertEqual(state, State(player=6, boxes=frozenset({7})))
        self.assertEqual(level.goals, {8})
        self.assertEqual(level.floor, {6, 7, 8})

    def test_first_comment_line_is_the_title(self):
        level, _ = parse_level(DETOUR)
        self.assertEqual(level.title, "Detour")

    def test_format_is_the_inverse_of_parse(self):
        level, state = parse_level(CORRIDOR)
        self.assertEqual(format_level(level, state), CORRIDOR.strip())

    def test_rejects_levels_that_break_the_rules(self):
        broken = {
            "no keeper": "#####\n# $.#\n#####",
            "two keepers": "######\n#@$.@#\n######",
            "no crates": "####\n#@ #\n####",
            "crate/goal mismatch": "######\n#@$$.#\n######",
            "not enclosed": "#####\n#@$. \n#####",
            "crate walled off": "#######\n#@$.#$#\n#####.#\n    ###",
            "unknown symbol": "#####\n#@$x#\n#####",
        }
        for name, text in broken.items():
            with self.subTest(name), self.assertRaises(LevelError):
                parse_level(text)


class Moves(unittest.TestCase):
    def test_pushing_moves_the_crate_one_cell(self):
        level, state = parse_level(CORRIDOR)
        after, pushed = apply_move(level, state, "R")
        self.assertTrue(pushed)
        self.assertEqual(after, State(7, frozenset({8})))
        self.assertTrue(is_goal(level, after))

    def test_walls_and_double_crates_block(self):
        level, state = parse_level("######\n#@$$ #\n#  ..#\n######")
        self.assertIsNone(apply_move(level, state, "U"))   # wall
        self.assertIsNone(apply_move(level, state, "R"))   # two crates in a row

    def test_keeper_cannot_walk_through_crates(self):
        level, state = parse_level(CORRIDOR)
        self.assertEqual(reachable(level, state.boxes, state.player), {6})

    def test_a_push_needs_the_keeper_behind_the_crate(self):
        # A wall sits left of the crate: nowhere to stand to push it right,
        # nowhere for it to go when pushed left.
        level, state = parse_level("######\n#    #\n##$  #\n#  @.#\n######")
        region = reachable(level, state.boxes, state.player)
        up, down = -level.width, level.width
        box = next(iter(state.boxes))
        self.assertEqual(set(legal_pushes(level, state.boxes, region)),
                         {(box, up), (box, down)})

    def test_pushes_expand_to_a_playable_move_string(self):
        level, state = parse_level("#######\n#     #\n# .$  #\n#@    #\n#######")
        box = next(iter(state.boxes))
        moves = pushes_to_moves(level, state, [(box, -1)])
        self.assertEqual(moves[-1], "L")                    # upper case = push
        self.assertTrue(moves[:-1].islower())               # lower case = walk
        self.assertTrue(is_goal(level, replay(level, state, moves)))

    def test_replay_refuses_illegal_moves(self):
        level, state = parse_level(CORRIDOR)
        with self.assertRaises(ValueError):
            replay(level, state, "U")


if __name__ == "__main__":
    unittest.main()
