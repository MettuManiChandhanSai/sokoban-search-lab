"use strict";
/* Sokoban Search Lab: page logic.

   This file draws and forwards input, nothing more. Rules, searches and
   numbers all come from the project's Python modules, loaded into the page
   with Pyodide; `call(method, args)` is the only way in (interface/bridge.py). */

const $ = id => document.getElementById(id);
const num = n => Number(n).toLocaleString("en-US");
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const secs = s => s < 1 ? Math.round(s * 1000) + " ms" : s.toFixed(1) + " s";
const store = {
  get(key, fallback) { try { const v = localStorage.getItem("ssl." + key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem("ssl." + key, JSON.stringify(value)); } catch { /* private mode: fine */ } },
};

let call;                                   // call(method, args) -> object, set by boot()
const S = {
  boot: null, level: null, view: null, mode: "play",
  algo: null, solving: null,                // chosen algorithm; the one a running solve uses
  pending: new Set(),                       // Python jobs still running
  playing: false, script: "", nextStep: 0,  // timeline playback; moves queued by a hint
  clock: { t0: 0, total: 0 },
  par: null, hint: null, notice: null, solvedBy: null,
  raceFor: null, labRan: false, sound: store.get("sound", true), raf: 0,
};
const board = new Render.Board($("board"));
const editor = new Render.Board($("editor"));
const lanes = {};                           // algorithm key -> {root, board, bar, status, nums}
const STATUS = { solved: "Solved", unsolvable: "No solution", node_limit: "Out of budget", time_limit: "Out of time" };

/* ------------------------------------------------------------------ boot */

async function boot() {
  const say = (text, pct) => { $("boot-text").textContent = text; $("boot-bar").style.width = pct + "%"; };
  try {
    say("Loading the Python runtime…", 20);
    const py = await loadPyodide({ indexURL: new URL("pyodide/", document.baseURI).href });
    say("Unpacking the solver modules…", 75);
    const bundle = await fetch("app.zip");
    if (!bundle.ok) throw new Error("app.zip: HTTP " + bundle.status);
    py.unpackArchive(await bundle.arrayBuffer(), "zip", { extractDir: "/app" });
    py.runPython("import sys; sys.path.insert(0, '/app')");
    const bridge = py.pyimport("interface.bridge");
    call = (method, args = {}) => JSON.parse(bridge.call(method, JSON.stringify(args)));
    say("Opening the warehouse…", 95);
    S.boot = call("boot");
    buildUi();
    const last = store.get("level", "");
    openLevel(S.boot.levels.some(l => l.id === last) ? last : S.boot.levels[0].id);
    $("boot").hidden = true;
  } catch (err) {
    console.error(err);
    $("boot").classList.add("failed");
    say("The Python runtime could not start.", 100);
    $("boot").querySelector(".fine").textContent = String(err.message || err);
  }
}

function buildUi() {
  const { levels, packs, algorithms } = S.boot;
  // level picker, grouped by pack; codes like T-03 = pack initial + position
  const counts = {};
  for (const level of levels) {
    counts[level.pack] = (counts[level.pack] || 0) + 1;
    level.code = level.pack[0].toUpperCase() + "-" + String(counts[level.pack]).padStart(2, "0");
  }
  $("level").innerHTML = packs.map(pack => `<optgroup label="${esc(pack.name)}">` + levels.filter(l => l.pack === pack.key)
    .map(l => `<option value="${esc(l.id)}">${esc(l.title)}</option>`).join("") + "</optgroup>").join("");
  $("lab-pack").innerHTML = '<option value="">All packs</option>' + packs.map(p => `<option value="${p.key}">${esc(p.name)}</option>`).join("");
  $("lab-pack").value = "training";

  $("algos").innerHTML = algorithms.map((a, i) => `<label style="--swatch: var(--s${i + 1})">
    <input type="radio" name="algo" value="${a.key}"><span>${esc(a.short)}</span></label>`).join("");
  pickAlgo(store.get("algo", S.boot.best));

  $("lanes").innerHTML = algorithms.map((a, i) => `<article class="lane" style="--swatch: var(--s${i + 1})">
      <canvas></canvas>
      <div class="lane-body">
        <div class="lane-top"><span class="lane-name">${esc(a.label)}</span><span class="lane-status">Ready</span></div>
        <p class="lane-idea">${esc(a.idea)}</p>
        <div class="track"><i style="width:0"></i></div>
        <div class="scale" aria-hidden="true"><span>1</span><span>10</span><span>100</span><span>1k</span><span>10k</span><span>100k</span></div>
        <p class="lane-nums">&nbsp;</p>
      </div></article>`).join("");
  [...$("lanes").children].forEach((root, i) => {
    lanes[algorithms[i].key] = { root, board: new Render.Board(root.querySelector("canvas"), { mini: true }),
      bar: root.querySelector(".track i"), status: root.querySelector(".lane-status"), nums: root.querySelector(".lane-nums") };
  });
  $("matrix").tHead.innerHTML = "<tr><th>Level</th>" + algorithms.map((a, i) =>
    `<th style="--swatch: var(--s${i + 1})"><i></i>${esc(a.label)}</th>`).join("") + "</tr>";

  wire();
  themeChanged();
  $("sound").textContent = S.sound ? "Sound on" : "Sound off";
  $("sound").setAttribute("aria-pressed", S.sound);
}

/* ----------------------------------------------------------------- level */

function openLevel(target) {
  const view = call("open", typeof target === "string" ? { id: target } : target);
  if (view.error) return view.error;
  const known = S.boot.levels.find(l => l.id === view.level.id);
  Object.assign(S, { level: view.level, view: null, par: null, hint: null, notice: null, solvedBy: null,
    playing: false, script: "", solving: null, raceFor: null, pending: new Set(["par"]) });
  S.clock = { t0: 0, total: 0 };
  board.setLevel(view.level);
  Object.assign(board, { heat: new Map(), ghost: null, hint: null, trails: null });
  for (const lane of Object.values(lanes)) resetLane(lane);
  $("verdict").textContent = "";

  $("bay-code").textContent = known ? known.code : "MY";
  let custom = $("level").querySelector("option[data-custom]");
  if (!known && !custom) {
    custom = new Option("", "");
    custom.dataset.custom = "1";
    $("level").prepend(custom);
  }
  if (custom) custom.textContent = known ? "My level" : view.level.title;
  $("level").value = known ? known.id : "";
  $("note").textContent = view.level.note || (known ? "" : "Your own level. The AI best box tells you whether it can be solved.");
  $("s-par").textContent = "…";
  $("readout").textContent = "Pick an algorithm and press Solve. The answer is added to the timeline below.";
  if (known) store.set("level", known.id);

  apply(view, false);
  if (S.mode === "race") enterRace();
  return null;
}

function stepLevel(by) {
  const ids = S.boot.levels.map(l => l.id);
  const at = ids.indexOf(S.level.id);
  openLevel(ids[(at + by + ids.length) % ids.length]);
}

/* Every new position from Python goes through here. `animate` is false, true
   or a slide time in ms. */
function apply(view, animate = true) {
  const before = S.view;
  S.view = view;
  board.flagged = view.deadlock ? view.deadlock.crates : [];
  board.hint = S.hint = null;
  board.setState(view, animate);

  const now = performance.now(), running = view.cursor > 0 && !view.solved;
  if (view.cursor === 0) S.clock = { t0: 0, total: 0 };
  if (running && !S.clock.t0) S.clock.t0 = now;
  if (!running && S.clock.t0) { S.clock.total += now - S.clock.t0; S.clock.t0 = 0; }

  if (before && view.cursor > before.cursor) {
    const home = v => v.boxes.filter(b => S.level.goals.includes(b)).length;
    const quiet = S.playing && +$("speed").value >= 20;
    if (view.solved && !before.solved) [523, 659, 784, 1047].forEach((f, i) => beep(f, 220, "triangle", .06, i * .09));
    else if (quiet) { /* too fast to hear */ }
    else if (view.deadlock && !before.deadlock) beep(92, 320, "sawtooth", .05);
    else if (home(view) > home(before)) { beep(660, 110, "sine", .06); beep(880, 170, "sine", .05, .08); }
    else if (view.pushes > before.pushes) beep(118, 80, "triangle", .09);
  }
  if ($("o-paths").checked) board.trails = call("trails");
  if (!view.solved || !before || !before.solved) S.notice = null;
  paintPanel();
  kick();
}

function paintPanel() {
  const v = S.view;
  if (!v) return;
  $("s-pushes").textContent = v.pushes;
  $("s-moves").textContent = v.cursor;
  $("undo").disabled = $("t-back").disabled = $("t-start").disabled = v.cursor === 0;
  $("redo").disabled = $("t-fwd").disabled = v.cursor === v.length;
  $("t-play").disabled = v.cursor === v.length && !S.playing;
  $("t-play").textContent = S.playing ? "Pause" : "Play";
  $("hint").disabled = v.solved;
  $("scrub").max = v.length;
  $("scrub").value = v.cursor;
  const ai = v.ai_from === null ? v.length : v.ai_from;
  $("lurd").innerHTML = v.length
    ? `<b>${esc(v.moves.slice(0, v.cursor))}</b>${esc(v.moves.slice(v.cursor))}` +
      (ai < v.length ? ` <span>(${ai} yours, ${v.length - ai} from the solver)</span>` : "")
    : "Moves appear here: lower case walks, UPPER CASE pushes.";

  const banner = v.deadlock && !v.solved
    ? { title: v.deadlock.name, text: v.deadlock.why + " Undo (Z) to step back." } : S.notice;
  $("banner").hidden = !banner;
  if (banner) { $("banner-title").textContent = banner.title; $("banner-text").textContent = banner.text; }

  $("result").hidden = !v.solved;
  if (v.solved) $("result").textContent = verdictOnRun(v);

  const bits = [];
  if ($("o-dead").checked) bits.push("Hatched: a crate pushed there can never reach a goal. Point at one to see why.");
  if ($("o-trace").checked) bits.push("Orange tint: squares where the search has tried a crate.");
  if ($("o-paths").checked) bits.push('<i class="key" style="background:var(--you)"></i>you &nbsp; <i class="key" style="background:var(--ai)"></i>the optimal route');
  $("legend").innerHTML = bits.join("<br>");
}

function verdictOnRun(v) {
  if (v.ai_from !== null && v.cursor > v.ai_from)
    return `Solved by ${S.solvedBy || "the solver"}: ${v.pushes} pushes, ${v.cursor} moves` + (v.ai_from ? `, taking over after your ${v.ai_from} moves.` : ".");
  let text = `Solved in ${v.pushes} pushes and ${v.cursor} moves (${clockText()}).`;
  if (S.par && S.par.solved) {
    const over = v.pushes - S.par.n_pushes;
    text += over > 0 ? ` The optimum is ${S.par.n_pushes} pushes, so ${over} could be saved.` : " That is optimal: no solution uses fewer pushes.";
  }
  if (v.hints) text += ` Hints used: ${v.hints}.`;
  if (S.level.id && !v.hints) {
    const best = store.get("best", {});
    if (!(best[S.level.id] <= v.pushes)) { best[S.level.id] = v.pushes; store.set("best", best); }
    else if (best[S.level.id] < v.pushes) text += ` Your best: ${best[S.level.id]}.`;
  }
  return text;
}

function clockText() {
  const ms = S.clock.total + (S.clock.t0 ? performance.now() - S.clock.t0 : 0);
  const s = Math.floor(ms / 1000);
  return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0");
}

/* ----------------------------------------------------------- player input */

function move(direction) {
  if (!S.view || S.view.solved && S.view.cursor === S.view.length) return;
  stopPlayback();
  board.heat = new Map();
  apply(call("move", { direction }));
}

function stopPlayback() { S.playing = false; S.script = ""; }

function seek(cursor) { stopPlayback(); apply(call("seek", { cursor }), false); }

function togglePlay() {
  S.playing = !S.playing && S.view.cursor < S.view.length;
  S.nextStep = 0;
  paintPanel();
  kick();
}

function hint() {
  if (S.hint) { S.script = S.hint.moves; board.hint = S.hint = null; S.nextStep = 0; return kick(); }
  stopPlayback();
  call("hint");
  S.pending.add("hint");
  $("readout").textContent = "Thinking about the next push…";
  kick();
}

function solve() {
  stopPlayback();
  board.heat = new Map();
  S.solving = S.boot.algorithms.find(a => a.key === S.algo);
  call("solve", { algorithm: S.algo });
  S.pending.add("solve");
  $("stop").hidden = false;
  $("solve").disabled = true;
  kick();
}

function pickAlgo(key) {
  S.algo = S.boot.algorithms.some(a => a.key === key) ? key : S.boot.best;
  const input = $("algos").querySelector(`input[value="${S.algo}"]`);
  input.checked = true;
  $("algo-idea").textContent = S.boot.algorithms.find(a => a.key === S.algo).idea;
  store.set("algo", S.algo);
}

/* ------------------------------------------------------------ Python jobs */

const onJob = {
  par(r) {
    if (!r.done) return;
    S.par = r.result;
    $("s-par").textContent = r.result.solved ? r.result.n_pushes : r.result.status === "unsolvable" ? "none" : "?";
    $("s-par").title = r.result.solved ? `Fewest pushes possible (${r.result.n_moves} moves), found by the solver`
      : r.result.status === "unsolvable" ? "The solver proved this level has no solution" : "The solver ran out of budget";
    if ($("o-paths").checked) board.trails = call("trails");
    paintPanel();
  },

  solve(r) {
    const s = r.stats, label = S.solving.label;
    if ($("o-trace").checked) {
      board.ghost = r.done ? null : s;
      for (const box of s.boxes) board.heat.set(box, (board.heat.get(box) || 0) + 1);
    }
    if (!r.done) {
      $("readout").textContent = `${label} is searching… ${num(s.expanded)} positions expanded, ` +
        `${num(s.frontier)} waiting, ${s.depth} pushes deep, ${secs(s.time)}`;
      return;
    }
    board.ghost = null;
    $("stop").hidden = true;
    $("solve").disabled = false;
    $("readout").textContent = describe(r.result);
    if (r.result.solved) {
      S.solvedBy = label;
      apply(r.view, false);
      S.playing = r.view.cursor < r.view.length;
      S.nextStep = performance.now() + 350;
      paintPanel();
    } else if (r.result.status === "unsolvable") {
      S.notice = { title: "No way out", text: "The search proved there is no solution from this position. Undo and try another way." };
      paintPanel();
    }
  },

  hint(r) {
    if (!r.done) return;
    if (r.hint) {
      board.hint = S.hint = r.hint;
      const way = { U: "up", D: "down", L: "left", R: "right" }[r.hint.moves.slice(-1)];
      $("readout").textContent = `Hint: push the marked crate ${way}. Press Hint (H) again and the keeper does it.`;
    } else {
      const dead = r.result.status === "unsolvable";
      S.notice = dead ? { title: "No way out", text: "There is no solution from this position. Undo and try another way." }
        : { title: "No hint", text: "The solver ran out of budget before finding a solution from here." };
      $("readout").textContent = S.notice.text;
      paintPanel();
    }
  },

  race(r) {
    for (const lane of r.lanes) paintLane(lanes[lane.algorithm], lane);
    if (!r.done) return;
    $("race-go").hidden = false;
    $("race-stop").hidden = true;
    $("verdict").textContent = verdictOnRace(r.lanes.map(l => l.result));
  },

  bench(r) {
    for (const row of r.rows) addBenchRow(row);
    $("lab-status").textContent = r.done ? `Finished: ${r.total} levels, ${r.total * S.boot.algorithms.length} searches.`
      : `${r.finished} of ${r.total} levels done. Now solving ${r.current}…`;
    if (!r.done) return;
    $("lab-go").hidden = false;
    $("lab-stop").hidden = true;
    $("tiles").innerHTML = r.summary.map((s, i) => `<div class="tile" style="--swatch: var(--s${i + 1})">
      <strong>${esc(s.label)}</strong>
      <span class="big">${num(s.expanded)}</span>
      <span class="fine">positions expanded in total</span>
      <span>Solved ${s.solved} of ${s.levels} levels in ${secs(s.time)}</span>
      <span class="fine">${s.algorithm === "bfs" ? "The baseline" : "Median saving vs BFS: " + Math.min(s.median_node_reduction, 99.9).toFixed(1) + "% fewer positions"}</span>
    </div>`).join("");
  },
};

function pump() {
  const reports = call("tick", { ms: 14 }).jobs;
  for (const name of [...S.pending]) {
    const report = reports[name];
    if (!report || report.done) S.pending.delete(name);
    if (report) onJob[name](report);
  }
}

function describe(result) {
  const cost = `${num(result.expanded)} positions expanded, ${num(result.generated)} generated, ${secs(result.time)}`;
  const pruned = Object.entries(result.pruned).map(([rule, n]) => `${S.boot.rules[rule].name.toLowerCase()} ${num(n)}`).join(", ");
  const tail = pruned ? `. Pushes discarded as hopeless: ${pruned}.` : ".";
  if (result.solved) return `${result.label}: solved in ${result.n_pushes} pushes (${result.n_moves} moves). ${cost}${tail}`;
  if (result.status === "unsolvable") return `${result.label}: no solution exists from this position. ${cost}${tail}`;
  return `${result.label}: gave up, out of ${result.status === "node_limit" ? "node budget" : "time"}. ${cost}${tail}`;
}

/* ------------------------------------------------------------------ race */

const logWidth = n => Math.min(100, Math.log10(Math.max(1, n)) / 6 * 100) + "%";   // 1 .. 1,000,000

function resetLane(lane) {
  lane.bar.style.width = "0";
  lane.status.textContent = "Ready";
  lane.status.dataset.s = "";
  lane.nums.innerHTML = "&nbsp;";
  if (S.level) { lane.board.setLevel(S.level); lane.board.setState(S.view || { player: -1, boxes: [] }, false); lane.board.draw(); }
}

function paintLane(lane, report) {
  const s = report.stats, r = report.result;
  lane.bar.style.width = logWidth(s.expanded);
  lane.board.ghost = null;
  lane.board.setState({ player: s.player, boxes: s.boxes }, false);
  lane.board.draw();
  if (!r) {
    lane.status.textContent = "Searching";
    lane.nums.textContent = `${num(s.expanded)} expanded · ${num(s.frontier)} waiting · ${s.depth} pushes deep · ${secs(s.time)}`;
    return;
  }
  lane.status.textContent = STATUS[r.status];
  lane.status.dataset.s = r.status;
  let text = `${num(r.expanded)} expanded · ${secs(r.time)}`;
  if (r.solved) text += ` · ${r.n_pushes} pushes, ${r.n_moves} moves`;
  const pruned = Object.values(r.pruned).reduce((a, b) => a + b, 0);
  if (pruned) text += ` · ${num(pruned)} pushes pruned`;
  if (r.algorithm !== "bfs" && r.node_reduction != null)
    text += ` · ${r.baseline_finished ? "" : "at least "}${Math.min(r.node_reduction, 99.9).toFixed(1)}% fewer positions than BFS`;
  lane.nums.textContent = text;
}

function verdictOnRace(results) {
  const bfs = results[0], best = results[results.length - 1];
  if (!best.solved) return best.status === "unsolvable" ? "This level has no solution, and every algorithm that finished agrees."
    : "None of the algorithms finished within the budget.";
  const pruned = Object.entries(results[2].pruned).map(([rule, n]) => `${S.boot.rules[rule].name.toLowerCase()} ${num(n)}`).join(", ");
  const knowledge = pruned ? ` The deadlock rules discarded ${pruned}.` : "";
  if (!bfs.solved) return `BFS ran out of budget after ${num(bfs.expanded)} positions. ${best.label} solved the level after ${num(best.expanded)}.${knowledge}`;
  return `All four found a ${best.n_pushes}-push solution, the fewest possible. BFS expanded ${num(bfs.expanded)} positions to get there; ` +
    `${best.label} expanded ${num(best.expanded)}, about ${Math.round(bfs.expanded / Math.max(1, best.expanded))} times less work.${knowledge}`;
}

function startRace() {
  for (const lane of Object.values(lanes)) resetLane(lane);
  $("verdict").textContent = "";
  call("race");
  S.pending.add("race");
  S.raceFor = S.level.text;
  $("race-go").hidden = true;
  $("race-stop").hidden = false;
  kick();
}

function enterRace() {
  for (const lane of Object.values(lanes)) { lane.board.resize(); lane.board.draw(); }
  if (S.level && S.raceFor !== S.level.text) startRace();
}

/* ------------------------------------------------------------------- lab */

function startLab() {
  $("matrix").tBodies[0].innerHTML = "";
  $("tiles").innerHTML = "";
  call("benchmark", { pack: $("lab-pack").value || null, seconds: +$("lab-budget").value });
  S.pending.add("bench");
  S.labRan = true;
  $("lab-go").hidden = true;
  $("lab-stop").hidden = false;
  $("lab-status").textContent = "Starting…";
  kick();
}

function addBenchRow(row) {
  const body = $("matrix").tBodies[0], known = S.boot.levels.find(l => l.id === row.level);
  let tr = body.querySelector(`tr[data-level="${row.level}"]`);
  if (!tr) {
    if (!body.querySelector(`tr[data-pack="${known.pack}"]`)) {
      const head = body.insertRow();
      head.className = "pack-row";
      head.dataset.pack = known.pack;
      head.innerHTML = `<th colspan="5">${esc(S.boot.packs.find(p => p.key === known.pack).name)}</th>`;
    }
    tr = body.insertRow();
    tr.dataset.level = row.level;
    tr.innerHTML = `<th scope="row">${esc(row.title)}<small>${known.code} · ${row.crates} crate${row.crates > 1 ? "s" : ""}</small></th>`;
  }
  const i = S.boot.algorithms.findIndex(a => a.key === row.algorithm);
  const gaveUp = !row.solved && row.status !== "unsolvable";
  const td = tr.insertCell();
  td.style.setProperty("--swatch", `var(--s${i + 1})`);
  td.title = `${row.label} on ${row.title}: ${STATUS[row.status].toLowerCase()}` +
    (row.solved ? `, ${row.n_pushes} pushes, ${row.n_moves} moves` : "") +
    `. ${num(row.expanded)} expanded, ${num(row.generated)} generated, ${secs(row.time)}.`;
  td.innerHTML = `<div class="cell${gaveUp ? " gave-up" : ""}"><div class="bar"><i style="width:${logWidth(row.expanded)}"></i></div>
    <span>${gaveUp ? "&gt;" : ""}${num(row.expanded)}</span></div>`;
}

async function copyReport(format) {
  const text = call("report", { format });
  const out = $("export");
  try {
    await navigator.clipboard.writeText(text);
    $("copy-status").textContent = `Copied ${text.trim().split("\n").length - 1} rows.`;
    out.hidden = true;
  } catch {
    out.hidden = false;
    out.value = text;
    out.select();
    $("copy-status").textContent = "Select the text below and copy it.";
  }
}

/* ---------------------------------------------------------------- editor */

const ED = { w: 9, h: 8, grid: [], timer: 0 };

function edRoom(w, h) {
  ED.w = w; ED.h = h;
  ED.grid = Array.from({ length: w * h }, (_, c) => c % w === 0 || c % w === w - 1 || c < w || c >= w * (h - 1) ? "#" : " ");
}

function edFromText(text) {
  const rows = text.split("\n").filter(r => r.trim() && !r.trim().startsWith(";")).map(r => r.replace(/\s+$/, "").replace(/[-_]/g, " "));
  if (!rows.length) return;
  ED.w = Math.min(20, Math.max(...rows.map(r => r.length)));
  ED.h = Math.min(16, rows.length);
  ED.grid = [];
  for (let y = 0; y < ED.h; y++) for (let x = 0; x < ED.w; x++) ED.grid.push("#$.*@+ ".includes(rows[y][x]) ? rows[y][x] : " ");
}

const edText = () => Array.from({ length: ED.h }, (_, y) => ED.grid.slice(y * ED.w, (y + 1) * ED.w).join("").replace(/\s+$/, "")).join("\n");

function edPaint(cell, tool) {
  const g = ED.grid, was = g[cell], goal = ".*+".includes(was);
  if (tool === "#" || tool === " ") g[cell] = tool;
  else if (tool === "$") g[cell] = goal ? "*" : "$";
  else if (tool === ".") g[cell] = was === "$" ? "*" : was === "@" ? "+" : ".";
  else {
    for (let c = 0; c < g.length; c++) if (g[c] === "@") g[c] = " "; else if (g[c] === "+") g[c] = ".";
    g[cell] = goal ? "+" : "@";
  }
}

function edRefresh(fromText = false) {
  const cells = sym => ED.grid.flatMap((ch, c) => sym.includes(ch) ? [c] : []);
  editor.setLevel({ width: ED.w, height: ED.h, walls: cells("#"), goals: cells(".*+"), floor: cells(" $.*@+"), dead: {} }, { allWalls: true });
  editor.setState({ player: ED.grid.findIndex(ch => "@+".includes(ch)), boxes: cells("$*") }, false);
  editor.draw();
  if (!fromText) $("ed-text").value = edText();
  $("ed-w").value = ED.w; $("ed-h").value = ED.h;
  clearTimeout(ED.timer);
  ED.timer = setTimeout(() => {
    if (!call) return;
    const check = call("check", { text: edText() });
    $("ed-status").textContent = check.error ? "Not playable yet: " + check.error
      : `Looks good: ${check.crates} crate${check.crates > 1 ? "s" : ""}. Press Play to find out whether it can be solved.`;
    $("ed-play").disabled = !!check.error;
  }, 150);
}

/* ------------------------------------------------------------- the frame */

function frame(now) {
  S.raf = 0;
  if ((S.playing || S.script) && !board.animating && now >= S.nextStep) {
    const gap = 1000 / +$("speed").value, slide = Math.min(110, gap * 0.9);
    if (S.script) { const d = S.script[0]; S.script = S.script.slice(1); apply(call("move", { direction: d }), slide); }
    else if (S.view.cursor < S.view.length) apply(call("redo"), slide);
    if (S.playing && S.view.cursor >= S.view.length) { S.playing = false; paintPanel(); }
    S.nextStep = now + gap;
  }
  if (S.pending.size) pump();
  if (S.mode === "play") board.draw(now);
  if (board.animating || S.playing || S.script || S.pending.size) kick();
}

function kick() { if (!S.raf) S.raf = requestAnimationFrame(frame); }

/* ------------------------------------------------------------ odds & ends */

let audio;
function beep(freq, ms, type, volume, delay = 0) {
  if (!S.sound) return;
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    const osc = audio.createOscillator(), gain = audio.createGain(), t = audio.currentTime + delay;
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(volume, t);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + ms / 1000);
    osc.connect(gain).connect(audio.destination);
    osc.start(t);
    osc.stop(t + ms / 1000);
  } catch { /* no audio device: play silently */ }
}

const isDark = () => (document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark";

function themeChanged() {
  Render.readPalette();
  $("theme").textContent = isDark() ? "Day shift" : "Night shift";
  board.draw();
  editor.draw();
  for (const lane of Object.values(lanes)) lane.board.draw();
}

function setMode(mode) {
  S.mode = mode;
  $("app").dataset.mode = mode;
  for (const button of document.querySelectorAll(".modes button"))
    button.toggleAttribute("aria-current", button.dataset.mode === mode);
  for (const name of ["play", "race", "lab", "build"]) $("view-" + name).hidden = name !== mode;
  if (mode === "play") { board.resize(); kick(); }
  if (mode === "race") enterRace();
  if (mode === "lab" && !S.labRan) startLab();
  if (mode === "build") { if (!ED.grid.length) edFromText(S.level.text); edRefresh(); }
}

function wire() {
  for (const button of document.querySelectorAll(".modes button")) button.onclick = () => setMode(button.dataset.mode);
  $("level").onchange = e => e.target.value && openLevel(e.target.value);
  $("prev").onclick = () => stepLevel(-1);
  $("next").onclick = () => stepLevel(1);
  $("undo").onclick = $("t-back").onclick = () => seek(S.view.cursor - 1);
  $("redo").onclick = $("t-fwd").onclick = () => seek(S.view.cursor + 1);
  $("restart").onclick = () => { stopPlayback(); board.heat = new Map(); apply(call("reset"), false); };
  $("t-start").onclick = () => seek(0);
  $("t-play").onclick = togglePlay;
  $("scrub").oninput = e => seek(+e.target.value);
  $("hint").onclick = hint;
  $("solve").onclick = solve;
  $("stop").onclick = () => { call("cancel", { job: "solve" }); board.ghost = null; $("stop").hidden = true; $("solve").disabled = false; $("readout").textContent = "Stopped."; };
  $("algos").onchange = e => pickAlgo(e.target.value);
  for (const button of document.querySelectorAll("[data-move]")) button.onclick = () => move(button.dataset.move);
  $("o-dead").onchange = e => { board.showDead = e.target.checked; paintPanel(); kick(); };
  $("o-trace").onchange = e => { if (!e.target.checked) { board.heat = new Map(); board.ghost = null; } paintPanel(); kick(); };
  $("o-paths").onchange = e => { board.trails = e.target.checked ? call("trails") : null; paintPanel(); kick(); };

  $("race-go").onclick = startRace;
  $("race-stop").onclick = () => { call("cancel", { job: "race" }); $("race-go").hidden = false; $("race-stop").hidden = true; };
  $("lab-go").onclick = startLab;
  $("lab-stop").onclick = () => { call("cancel", { job: "bench" }); $("lab-go").hidden = false; $("lab-stop").hidden = true; $("lab-status").textContent = "Stopped."; };
  $("copy-csv").onclick = () => copyReport("csv");
  $("copy-md").onclick = () => copyReport("markdown");

  $("sound").onclick = () => {
    S.sound = !S.sound;
    store.set("sound", S.sound);
    $("sound").textContent = S.sound ? "Sound on" : "Sound off";
    $("sound").setAttribute("aria-pressed", S.sound);
  };
  $("theme").onclick = () => { document.documentElement.dataset.theme = isDark() ? "light" : "dark"; };
  new MutationObserver(themeChanged).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", themeChanged);
  addEventListener("resize", () => { board.resize(); editor.resize(); editor.draw(); for (const lane of Object.values(lanes)) { lane.board.resize(); lane.board.draw(); } kick(); });

  // keyboard: arrows or WASD move; Z undo, Y redo, R restart, H hint, space play/pause
  const keys = { ArrowUp: "U", ArrowDown: "D", ArrowLeft: "L", ArrowRight: "R", w: "U", s: "D", a: "L", d: "R" };
  addEventListener("keydown", e => {
    if (S.mode !== "play" || !S.view || e.ctrlKey || e.metaKey || e.altKey) return;
    const on = selector => e.target instanceof Element && e.target.matches(selector);
    if (on("input:not([type=checkbox]):not([type=radio]), select, textarea")) return;
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    if (keys[key]) move(keys[key]);
    else if (key === "z" || key === "u") seek(S.view.cursor - 1);
    else if (key === "y") seek(S.view.cursor + 1);
    else if (key === "r") $("restart").click();
    else if (key === "h") hint();
    else if (key === " " && !on("button")) togglePlay();
    else if (key === "n") stepLevel(1);
    else if (key === "p") stepLevel(-1);
    else return;
    e.preventDefault();
  });

  // swipe on the board; pointing at a hatched square explains it
  let down = null;
  $("board").onpointerdown = e => { down = [e.clientX, e.clientY]; };
  $("board").onpointerup = e => {
    if (!down) return;
    const dx = e.clientX - down[0], dy = e.clientY - down[1];
    down = null;
    if (Math.max(Math.abs(dx), Math.abs(dy)) < 24) return;
    move(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "R" : "L") : (dy > 0 ? "D" : "U"));
  };
  $("board").onpointermove = e => {
    const rule = board.showDead && S.level && S.level.dead[board.cellAt(e.clientX, e.clientY)];
    $("tip").hidden = !rule;
    if (!rule) return;
    const box = $("floor").getBoundingClientRect();
    $("tip").textContent = S.boot.rules[rule].name + ". " + S.boot.rules[rule].why;
    $("tip").style.left = Math.min(e.clientX - box.left + 14, box.width - 250) + "px";
    $("tip").style.top = e.clientY - box.top + 14 + "px";
  };
  $("board").onpointerleave = () => { $("tip").hidden = true; };

  // editor
  let painting = false;
  const paint = e => {
    const cell = editor.cellAt(e.clientX, e.clientY);
    if (cell < 0) return;
    edPaint(cell, document.querySelector("input[name=tool]:checked").value);
    edRefresh();
  };
  $("editor").onpointerdown = e => { painting = true; paint(e); };
  $("editor").onpointermove = e => { if (painting && document.querySelector("input[name=tool]:checked").value !== "@") paint(e); };
  addEventListener("pointerup", () => { painting = false; });
  $("ed-text").oninput = e => { edFromText(e.target.value); edRefresh(true); };
  const resizeRoom = () => {
    const w = Math.max(5, Math.min(14, +$("ed-w").value || 9)), h = Math.max(5, Math.min(11, +$("ed-h").value || 8));
    const old = { ...ED, grid: ED.grid.slice() };
    edRoom(w, h);
    for (let y = 1; y < Math.min(h, old.h) - 1; y++) for (let x = 1; x < Math.min(w, old.w) - 1; x++) ED.grid[y * w + x] = old.grid[y * old.w + x];
    edRefresh();
  };
  $("ed-w").onchange = $("ed-h").onchange = resizeRoom;
  $("ed-clear").onclick = () => { edRoom(ED.w, ED.h); edRefresh(); };
  $("gen-go").onclick = () => {
    const [width, height, boxes] = $("gen-size").value.split(",").map(Number);
    const made = call("generate", { seed: +$("gen-seed").value || 0, width, height, boxes });
    edFromText(made.text);
    edRefresh();
    $("gen-seed").value = (+$("gen-seed").value || 0) + 1;
  };
  $("ed-play").onclick = () => {
    const problem = openLevel({ text: edText(), title: "My level" });
    if (problem) $("ed-status").textContent = "Not playable yet: " + problem;
    else setMode("play");
  };

  setInterval(() => { if (S.view) $("s-time").textContent = clockText(); }, 250);
}

boot();
