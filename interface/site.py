"""
Build the static website and serve it locally.

    python run_game.py               build, serve on http://localhost:8000, open the browser
    python run_game.py --no-browser  the same without opening a browser
    python run_game.py --build-only  just refresh docs/
    python run_game.py --vendor DIR  install a Pyodide release into docs/pyodide/ (see README)

The site in docs/ is self-contained and needs no server-side code, so
it can be hosted anywhere static files can (GitHub Pages serves a
folder called docs/ out of the box):

    docs/index.html, style.css, render.js, app.js   the page (from interface/web/)
    docs/app.json     the five Python modules and the levels, as {path: text}
    docs/pyodide/     the Python runtime for browsers (vendored, see README)

Everything Python is shipped as plain text rather than archives because
some static hosts refuse to serve .zip files; the page packs what the
runtime needs in memory.
"""

import argparse
import json
import shutil
import webbrowser
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "interface" / "web"
SITE = ROOT / "docs"
MODULES = ("engine", "solvers", "puzzles", "analytics", "interface")

# interface/web/index.html holds only the page content; this is the frame.
PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
</head>
<body>
{content}</body>
</html>
"""


def build():
    """Refresh docs/ from the sources. Returns the site folder."""
    SITE.mkdir(exist_ok=True)
    (SITE / ".nojekyll").touch()        # GitHub Pages: serve the files as they are
    for name in ("style.css", "render.js", "app.js"):
        shutil.copyfile(WEB / name, SITE / name)
    content = (WEB / "index.html").read_text(encoding="utf-8")
    (SITE / "index.html").write_bytes(PAGE.format(content=content).encode("utf-8"))
    (SITE / "app.json").write_text(json.dumps(sources()), encoding="utf-8")
    return SITE


def sources():
    """The Python modules and level files the browser needs: ``{path: text}``."""
    return {path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
            for module in MODULES for path in sorted((ROOT / module).rglob("*"))
            if path.suffix in (".py", ".txt") and WEB not in path.parents}


def vendor(package):
    """Install a Pyodide release into docs/pyodide/. `package` is the folder
    you get from unpacking `npm pack pyodide`."""
    package, target = Path(package), SITE / "pyodide"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("pyodide.js", "pyodide.asm.mjs", "pyodide.asm.wasm", "pyodide-lock.json"):
        shutil.copyfile(package / name, target / name)
    with zipfile.ZipFile(package / "python_stdlib.zip") as stdlib:
        files = {item.filename: stdlib.read(item).decode("utf-8")
                 for item in stdlib.infolist() if not item.is_dir()}
    (target / "python_stdlib.json").write_text(json.dumps(files), encoding="utf-8")
    return target


class Handler(SimpleHTTPRequestHandler):
    # Windows often maps these to text/plain, which browsers refuse to run.
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".mjs": "text/javascript",
                      ".wasm": "application/wasm"}

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")   # always the fresh build
        super().end_headers()

    def log_message(self, *args):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sokoban Search Lab")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--vendor", metavar="DIR", help="unpacked pyodide npm package to install")
    args = parser.parse_args(argv)

    if args.vendor:
        print(f"Installed the Python runtime into {vendor(args.vendor)}")
    site = build()
    print(f"Built {site}")
    if args.build_only:
        return
    server = ThreadingHTTPServer(("127.0.0.1", args.port),
                                 partial(Handler, directory=str(site)))
    url = f"http://localhost:{args.port}/"
    print(f"Serving {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
