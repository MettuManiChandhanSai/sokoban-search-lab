"""
MODULE 3 · interface — what the player sees and touches.

    bridge.py   the one door between the browser and Python: a Game
                session (level, timeline, running searches) with a
                JSON-in / JSON-out call()
    site.py     builds the static site into docs/ and serves it locally
    web/        the page itself: index.html, style.css, render.js, app.js

The browser runs this very package, unchanged, inside Pyodide (CPython
compiled to WebAssembly). The JavaScript only draws and forwards input;
every rule, search and number comes from the Python modules.
"""
