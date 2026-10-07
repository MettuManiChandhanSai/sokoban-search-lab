"""
Build the static website and serve it locally.

    python run_game.py               build, serve on http://localhost:8000, open the browser
    python run_game.py --no-browser  the same without opening a browser
    python run_game.py --build-only  just refresh docs/

The site in docs/ is self-contained and needs no server-side code, so
it can be hosted anywhere static files can (GitHub Pages serves a
folder called docs/ out of the box):

    docs/index.html, style.css, render.js, app.js   the page (from interface/web/)
    docs/app.zip      the five Python modules, exactly as in this repository
    docs/pyodide/     the Python runtime for browsers (vendored, see README)
"""

import argparse
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
    for name in ("style.css", "render.js", "app.js"):
        shutil.copyfile(WEB / name, SITE / name)
    content = (WEB / "index.html").read_text(encoding="utf-8")
    (SITE / "index.html").write_text(PAGE.format(content=content),
                                     encoding="utf-8", newline="\n")
    with zipfile.ZipFile(SITE / "app.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
        for module in MODULES:
            for path in sorted((ROOT / module).rglob("*")):
                if path.suffix in (".py", ".txt") and WEB not in path.parents:
                    bundle.write(path, path.relative_to(ROOT).as_posix())
    return SITE


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
    args = parser.parse_args(argv)

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
