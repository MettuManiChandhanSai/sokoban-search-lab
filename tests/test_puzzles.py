import unittest

from engine.level import parse_level
from engine.state import is_goal, replay
from puzzles.generator import generate
from puzzles.library import PACKS, catalog, load
from solvers.solve import ALGORITHMS, solve


class Library(unittest.TestCase):
    def test_every_pack_has_levels(self):
        packs = {entry["pack"] for entry in catalog()}
        self.assertEqual(packs, set(PACKS))

    def test_every_level_is_valid_and_solvable(self):
        for entry in catalog():
            with self.subTest(entry["id"]):
                self.assertTrue(entry["title"])
                level, state = load(entry["id"])
                self.assertFalse(is_goal(level, state))
                result = solve(level, state)
                self.assertEqual(result["status"], "solved")
                self.assertTrue(is_goal(level, replay(level, state, result["moves"])))


class Generator(unittest.TestCase):
    def test_same_seed_same_level(self):
        self.assertEqual(generate(seed=5), generate(seed=5))
        self.assertNotEqual(generate(seed=5), generate(seed=6))

    def test_generated_levels_are_solvable_and_all_algorithms_agree(self):
        for seed in range(12):
            level, state = parse_level(generate(seed=seed, width=7, height=7, boxes=2))
            pushes = {solve(level, state, key)["n_pushes"] for key in ALGORITHMS}
            self.assertEqual(len(pushes), 1, seed)
            self.assertNotIn(None, pushes, seed)

    def test_respects_the_requested_shape(self):
        level, state = parse_level(generate(seed=1, width=10, height=8, boxes=4))
        self.assertEqual((level.width, level.height, len(state.boxes)), (10, 8, 4))


if __name__ == "__main__":
    unittest.main()
