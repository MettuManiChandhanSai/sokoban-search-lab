import json
import unittest

from interface.site import MODULES, SITE, WEB, sources
from puzzles.library import catalog


class Site(unittest.TestCase):
    def test_bundle_holds_every_module_and_every_level(self):
        bundle = sources()
        for module in MODULES:
            self.assertIn(f"{module}/__init__.py", bundle)
        for entry in catalog():
            self.assertEqual(bundle[f"puzzles/{entry['id']}.txt"], entry["text"])
        self.assertFalse(any(path.startswith("interface/web/") for path in bundle))

    def test_published_site_matches_the_sources(self):
        # docs/ is what gets hosted; if this fails, run: python run_game.py --build-only
        self.assertEqual(json.loads((SITE / "app.json").read_text(encoding="utf-8")), sources())
        for name in ("style.css", "render.js", "app.js"):
            self.assertEqual((SITE / name).read_bytes(), (WEB / name).read_bytes(), name)
        page = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn((WEB / "index.html").read_text(encoding="utf-8"), page)

    def test_python_runtime_is_vendored(self):
        for name in ("pyodide.js", "pyodide.asm.mjs", "pyodide.asm.wasm",
                     "pyodide-lock.json", "python_stdlib.json"):
            self.assertTrue((SITE / "pyodide" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
