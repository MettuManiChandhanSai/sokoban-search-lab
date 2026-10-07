import json
import unittest

from interface.bridge import Game, call

LANE = "training/07_dead_end_lane"


def finish(game, name):
    """Tick until job `name` reports done; return its last report."""
    for _ in range(100_000):
        report = game.tick(5)["jobs"].get(name)
        if report and report["done"]:
            return report
    raise AssertionError(f"job {name} never finished")


class Playing(unittest.TestCase):
    def setUp(self):
        self.game = Game()

    def test_boot_lists_algorithms_packs_and_levels(self):
        boot = self.game.boot()
        self.assertEqual([a["key"] for a in boot["algorithms"]],
                         ["bfs", "astar", "astar_deadlock", "astar_matching"])
        self.assertEqual([p["key"] for p in boot["packs"]], ["training", "classic", "warehouse"])
        self.assertEqual(len(boot["levels"]), 25)
        self.assertIn("corner", boot["rules"])

    def test_open_describes_the_level_and_the_position(self):
        view = self.game.open(id="training/01_first_push")
        level = view["level"]
        self.assertEqual((level["title"], level["width"], level["height"]), ("First Push", 8, 5))
        self.assertEqual(len(level["goals"]), 1)
        self.assertTrue(level["dead"])                       # dead-square map for the overlay
        self.assertEqual((view["cursor"], view["pushes"], view["solved"]), (0, 0, False))

    def test_moves_undo_redo_and_winning(self):
        game = self.game
        game.open(id="training/01_first_push")
        self.assertEqual(game.move("U")["cursor"], 1)
        self.assertEqual(game.move("U")["cursor"], 1)        # wall: nothing happens
        game.undo()
        game.move("R")
        view = game.move("R")
        self.assertEqual((view["cursor"], view["pushes"], view["last"]), (2, 1, "R"))
        self.assertFalse(view["solved"])
        self.assertTrue(game.move("R")["solved"])
        self.assertEqual(game.undo()["pushes"], 1)
        self.assertTrue(game.redo()["solved"])
        self.assertEqual(game.reset()["cursor"], 0)

    def test_a_new_move_discards_the_redo_branch(self):
        game = self.game
        game.open(id="training/01_first_push")
        game.move("R"), game.move("R"), game.undo()
        view = game.move("D")
        self.assertEqual((view["cursor"], view["length"]), (2, 2))

    def test_deadlock_coach_names_the_rule(self):
        game = self.game
        game.open(id="training/03_corner_trap")              # crate at (3,3), keeper at (5,4)
        for move in "luulD":                                 # walk above the crate, push it to the bottom wall
            view = game.move(move)
        self.assertEqual(view["deadlock"]["rule"], "wall-line")
        self.assertIn("slide", view["deadlock"]["why"])
        self.assertIsNone(game.undo()["deadlock"])

    def test_custom_level_text_and_validation_errors(self):
        view = self.game.open(text="#####\n#@$.#\n#####", title="Mine")
        self.assertEqual(view["level"]["title"], "Mine")
        bad = json.loads(call("open", json.dumps({"text": "#####\n# $.#\n#####"})))
        self.assertIn("keeper", bad["error"])


class Jobs(unittest.TestCase):
    def setUp(self):
        self.game = Game()
        self.game.open(id=LANE)

    def test_opening_a_level_computes_the_ai_optimum(self):
        par = finish(self.game, "par")
        self.assertEqual(par["result"]["n_pushes"], 15)

    def test_solve_appends_the_solution_to_the_timeline(self):
        game = self.game
        game.move("D")
        game.solve(algorithm="astar")
        report = finish(game, "solve")
        self.assertEqual(report["result"]["status"], "solved")
        view = report["view"]
        self.assertEqual((view["cursor"], view["ai_from"]), (1, 1))
        self.assertEqual(view["length"], 1 + report["result"]["n_moves"])
        self.assertTrue(game.seek(view["length"])["solved"])

    def test_search_progress_is_reported_while_running(self):
        self.game.solve(algorithm="bfs")
        report = self.game.tick(2)["jobs"]["solve"]
        self.assertFalse(report["done"])
        self.assertGreater(report["stats"]["expanded"], 0)
        self.assertEqual(len(report["stats"]["boxes"]), 3)
        self.game.cancel("solve")
        self.assertNotIn("solve", self.game.tick(2)["jobs"])

    def test_hint_gives_the_next_push(self):
        self.game.hint()
        hint = finish(self.game, "hint")
        self.assertTrue(hint["hint"]["moves"][-1].isupper())
        self.assertTrue(hint["hint"]["moves"][:-1].islower())
        self.assertEqual(hint["hint"]["path"][0], self.game.view()["player"])

    def test_race_runs_all_algorithms_and_compares_to_bfs(self):
        self.game.race()
        report = finish(self.game, "race")
        lanes = {lane["algorithm"]: lane for lane in report["lanes"]}
        self.assertEqual(len(lanes), 4)
        self.assertEqual({lane["result"]["n_pushes"] for lane in lanes.values()}, {15})
        self.assertGreater(lanes["astar_matching"]["result"]["node_reduction"], 90)

    def test_benchmark_streams_rows_and_ends_with_a_summary(self):
        self.game.benchmark(pack="training", seconds=5)
        rows, report = [], {"done": False}
        while not report["done"]:
            report = self.game.tick(20)["jobs"]["bench"]
            rows += report["rows"]
        self.assertEqual(len(rows), 7 * 4)
        self.assertEqual(len(report["summary"]), 4)
        self.assertIn("First Push", self.game.report(format="csv"))
        self.assertTrue(self.game.report(format="markdown").startswith("| Level"))

    def test_opening_a_level_stops_its_searches_but_not_the_benchmark(self):
        self.game.race()
        self.game.benchmark(pack="training", seconds=1)
        self.game.open(id="training/01_first_push")
        self.assertEqual(set(self.game.jobs), {"bench", "par"})

    def test_a_move_cancels_a_running_solve(self):
        self.game.solve(algorithm="bfs")
        self.game.move("D")
        self.assertNotIn("solve", self.game.tick(2)["jobs"])

    def test_trails_for_the_human_vs_ai_overlay(self):
        finish(self.game, "par")
        self.game.move("D")
        trails = self.game.trails()
        self.assertEqual(len(trails["you"]), 2)
        self.assertGreater(len(trails["ai"]), 15)


class Editor(unittest.TestCase):
    def test_generate_returns_a_playable_level(self):
        game = Game()
        text = game.generate(seed=3, width=8, height=7, boxes=2)["text"]
        self.assertNotIn("error", game.open(text=text))

    def test_generate_clamps_silly_sizes(self):
        level = Game().open(text=Game().generate(seed=1, width=99, height=2, boxes=40)["text"])["level"]
        self.assertLessEqual(level["width"], 12)
        self.assertGreaterEqual(level["height"], 6)


class JsonDoor(unittest.TestCase):
    def test_call_speaks_json_both_ways(self):
        boot = json.loads(call("boot", "{}"))
        self.assertIn("levels", boot)
        view = json.loads(call("open", json.dumps({"id": LANE})))
        self.assertEqual(view["level"]["crates"], 3)

    def test_call_reports_bad_requests_instead_of_raising(self):
        self.assertIn("error", json.loads(call("_secret", "{}")))
        self.assertIn("error", json.loads(call("open", json.dumps({"id": "nope/missing"}))))


if __name__ == "__main__":
    unittest.main()
