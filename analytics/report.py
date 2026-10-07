"""
Report rendering: the same benchmark rows as a text table, CSV,
Markdown, or a per-algorithm summary.

A row is a solver result (see solvers.solve) plus level, title, crates,
node_reduction and speedup.
"""

import csv
import io
from statistics import median

STATUS = {"solved": "solved", "unsolvable": "no solution",
          "node_limit": "node limit", "time_limit": "time limit"}

# (heading, how to read the cell from a row)
COLUMNS = [
    ("Level", lambda r: r["title"]),
    ("Crates", lambda r: r["crates"]),
    ("Algorithm", lambda r: r["label"]),
    ("Result", lambda r: STATUS[r["status"]]),
    ("Pushes", lambda r: _dash(r["n_pushes"])),
    ("Moves", lambda r: _dash(r["n_moves"])),
    ("Expanded", lambda r: r["expanded"]),
    ("Generated", lambda r: r["generated"]),
    ("Pruned", lambda r: sum(r["pruned"].values())),
    ("Time (ms)", lambda r: f"{r['time'] * 1000:.1f}"),
    ("Fewer nodes than BFS", lambda r: _versus(r, "node_reduction", "{:.1f}%", 99.9)),
    ("Speed-up vs BFS", lambda r: _versus(r, "speedup", "{:.1f}x")),
]


def _dash(value):
    return "-" if value is None else value


def _versus(row, key, fmt, cap=float("inf")):
    if row["algorithm"] == "bfs" or row.get(key) is None:
        return "-"
    # if BFS gave up early its true cost is higher: the figure is a lower bound
    return ("" if row["baseline_finished"] else ">") + fmt.format(min(row[key], cap))


def cells(rows):
    """Header row followed by one list of strings per row."""
    return [[name for name, _ in COLUMNS]] + [[str(read(r)) for _, read in COLUMNS]
                                             for r in rows]


def table(rows):
    """Fixed-width text for the terminal."""
    grid = cells(rows)
    widths = [max(len(line[i]) for line in grid) for i in range(len(COLUMNS))]
    lines = ["  ".join(cell.ljust(w) for cell, w in zip(line, widths)) for line in grid]
    return "\n".join([lines[0], "  ".join("-" * w for w in widths)] + lines[1:])


def to_csv(rows):
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(cells(rows))
    return out.getvalue()


def to_markdown(rows):
    grid = cells(rows)
    lines = ["| " + " | ".join(line) + " |" for line in grid]
    return "\n".join([lines[0], "|" + " --- |" * len(COLUMNS)] + lines[1:]) + "\n"


def summary(rows):
    """One dict per algorithm, in ladder order: levels solved, total
    nodes and time, and the median saving against BFS."""
    out = []
    for key in dict.fromkeys(r["algorithm"] for r in rows):
        mine = [r for r in rows if r["algorithm"] == key]
        saved = [r["node_reduction"] for r in mine if r["node_reduction"] is not None]
        out.append({
            "algorithm": key,
            "label": mine[0]["label"],
            "levels": len(mine),
            "solved": sum(r["solved"] for r in mine),
            "expanded": sum(r["expanded"] for r in mine),
            "time": sum(r["time"] for r in mine),
            "median_node_reduction": median(saved) if saved else None,
        })
    return out


def summary_table(rows):
    lines = [f"{'Algorithm':26}  {'Solved':>7}  {'Nodes expanded':>14}  "
             f"{'Time (s)':>8}  {'Median fewer nodes':>18}"]
    for s in summary(rows):
        saved = "-" if s["algorithm"] == "bfs" else f"{min(s['median_node_reduction'], 99.9):.1f}%"
        lines.append(f"{s['label']:26}  {s['solved']:>3}/{s['levels']:<3}  "
                     f"{s['expanded']:>14,}  {s['time']:>8.2f}  {saved:>18}")
    return "\n".join(lines)
