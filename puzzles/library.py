"""
The level catalogue.

A level is a text file ``puzzles/<pack>/<nn_name>.txt``:

    ; Title of the level
    ; Optional note shown to the player (what this level teaches).
    #####
    #@$.#
    #####

Drop a new file into a pack folder and it appears in the game, the
benchmark and the tests; nothing else needs editing.
"""

from pathlib import Path

from engine.level import parse_level

ROOT = Path(__file__).parent
PACKS = {                       # folder -> display name, in playing order
    "training": "Training",
    "classic": "Classic nine",
    "warehouse": "Warehouse",
    "showdown": "Showdown",
}


def catalog():
    """Every level, in playing order: ``{id, pack, title, note, text}``."""
    levels = []
    for pack in PACKS:
        for path in sorted((ROOT / pack).glob("*.txt")):
            text = path.read_text(encoding="utf-8")
            comments = [line.strip(" ;\t") for line in text.splitlines()
                        if line.lstrip().startswith(";")]
            levels.append({
                "id": f"{pack}/{path.stem}",
                "pack": pack,
                "title": comments[0] if comments else path.stem,
                "note": " ".join(comments[1:]),
                "text": text,
            })
    return levels


def load(level_id):
    """``(Level, State)`` for a catalogue id such as ``training/01_first_push``."""
    return parse_level((ROOT / f"{level_id}.txt").read_text(encoding="utf-8"))
