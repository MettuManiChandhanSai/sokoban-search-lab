"use strict";
/* Draws a Sokoban position on a canvas: floor, walls with a little height,
   crates, the keeper, and the teaching overlays. It knows nothing about the
   rules; app.js hands it a level and a position that came from Python. */

const Render = (() => {
  const P = {};   // colours, read from the CSS custom properties so themes just work

  function readPalette() {
    const css = getComputedStyle(document.documentElement);
    for (const name of ["floor", "floor-2", "seam", "wall", "wall-side", "wall-edge", "crate",
      "crate-side", "crate-line", "crate-ok", "crate-ok-side", "crate-ok-line", "goal", "hat",
      "body", "shadow", "dead", "trace"]) P[name] = css.getPropertyValue("--b-" + name).trim();
    for (const name of ["ink", "surface", "critical", "you", "ai"]) P[name] = css.getPropertyValue("--" + name).trim();
  }

  const ease = t => 1 - Math.pow(1 - t, 3);
  const TURN = { U: -Math.PI / 2, D: Math.PI / 2, L: Math.PI, R: 0 };

  class Board {
    constructor(canvas, { mini = false } = {}) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.mini = mini;
      this.level = null;
      this.state = null;
      this.anim = null;
      this.facing = "D";
      // overlays, set directly by app.js
      this.showDead = false;
      this.heat = null;        // Map cell -> how often the search touched it
      this.ghost = null;       // {player, boxes}: the position a search is examining
      this.hint = null;        // {path, box, to}
      this.trails = null;      // {you: [cells], ai: [cells]}
      this.flagged = [];       // crates in a deadlock
    }

    setLevel(level, { allWalls = false } = {}) {
      const w = level.width;
      this.level = level;
      this.walls = new Set(level.walls);
      this.floor = new Set(level.floor);
      this.goals = new Set(level.goals);
      // only walls that touch the floor are drawn, so the room keeps its outline
      this.shown = allWalls ? this.walls : new Set(level.walls.filter(c =>
        [-w - 1, -w, -w + 1, -1, 1, w - 1, w, w + 1].some(d => this.floor.has(c + d))));
      this.state = null;
      this.anim = null;
      this.resize();
    }

    setState(state, animate = true) {
      const before = this.state;
      this.state = state;
      if ("UDLR".includes((state.last || "").toUpperCase()) && state.last) this.facing = state.last.toUpperCase();
      this.anim = null;
      if (before && animate && before.player !== state.player) {
        const gone = before.boxes.find(b => !state.boxes.includes(b));
        const came = state.boxes.find(b => !before.boxes.includes(b));
        this.anim = { t0: performance.now(), ms: animate === true ? 110 : animate,
          from: before.player, to: state.player, boxFrom: gone, boxTo: came };
      }
    }

    get animating() { return !!this.anim && performance.now() - this.anim.t0 < this.anim.ms; }

    resize() {
      const { canvas, level } = this;
      const box = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      if (!box.width || !level) return;
      canvas.width = Math.round(box.width * dpr);
      canvas.height = Math.round(box.height * dpr);
      const pad = this.mini ? 4 : 14;
      const lift = this.mini ? 0 : 0.22;
      this.T = Math.max(4, Math.min(this.mini ? 16 : 76, Math.floor(Math.min(
        (box.width - 2 * pad) / level.width, (box.height - 2 * pad) / (level.height + lift)))));
      this.L = Math.round(this.T * lift);
      this.ox = Math.round((box.width - level.width * this.T) / 2);
      this.oy = Math.round((box.height - level.height * this.T - this.L) / 2) + this.L;
      this.dpr = dpr;
    }

    xy(cell) {     // top-left pixel of a cell (fractional cells allowed)
      const w = this.level.width;
      return [this.ox + (cell % w) * this.T, this.oy + Math.floor(cell / w) * this.T];
    }

    cellAt(clientX, clientY) {
      const box = this.canvas.getBoundingClientRect();
      const x = Math.floor((clientX - box.left - this.ox) / this.T);
      const y = Math.floor((clientY - box.top - this.oy) / this.T);
      const { width, height } = this.level;
      return x < 0 || y < 0 || x >= width || y >= height ? -1 : y * width + x;
    }

    draw(now = performance.now()) {
      const { ctx, level, state, T, L } = this;
      if (!level || !T) return;
      ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      const w = level.width;

      // where things are right now (mid-slide positions are fractional)
      let t = 1;
      if (this.anim) {
        t = Math.min(1, (now - this.anim.t0) / this.anim.ms);
        if (t >= 1) this.anim = null;
      }
      const slide = (from, to) => {
        const [ax, ay] = this.xy(from), [bx, by] = this.xy(to), e = ease(t);
        return [ax + (bx - ax) * e, ay + (by - ay) * e];
      };
      const a = this.anim;
      const things = [];   // {y, draw}
      if (state) {
        for (const box of state.boxes) {
          const [x, y] = a && box === a.boxTo ? slide(a.boxFrom, a.boxTo) : this.xy(box);
          things.push({ y, draw: () => this.crate(x, y, this.goals.has(box) && !(a && box === a.boxTo), this.flagged.includes(box)) });
        }
        if (state.player >= 0) {
          const [x, y] = a ? slide(a.from, a.to) : this.xy(state.player);
          things.push({ y: y + 1, draw: () => this.keeper(x, y) });
        }
      }
      things.sort((p, q) => p.y - q.y);

      // floor
      for (const cell of this.floor) {
        const [x, y] = this.xy(cell);
        ctx.fillStyle = ((cell % w) + Math.floor(cell / w)) % 2 ? P.floor : P["floor-2"];
        ctx.fillRect(x, y, T, T);
        if (!this.mini) { ctx.strokeStyle = P.seam; ctx.lineWidth = 1; ctx.strokeRect(x + .5, y + .5, T - 1, T - 1); }
      }
      if (this.heat && this.heat.size) {
        const top = Math.max(...this.heat.values());
        ctx.fillStyle = P.trace;
        for (const [cell, n] of this.heat) {
          const [x, y] = this.xy(cell);
          ctx.globalAlpha = 0.08 + 0.42 * Math.sqrt(n / top);
          ctx.fillRect(x, y, T, T);
        }
        ctx.globalAlpha = 1;
      }
      if (this.showDead) for (const cell of Object.keys(level.dead || {})) this.hatch(+cell);
      for (const cell of this.goals) this.goal(cell);

      // walls and things, back row first so nearer rows overlap farther ones
      let next = 0;
      for (let row = 0; row < level.height; row++) {
        for (let col = 0; col < w; col++) if (this.shown.has(row * w + col)) this.wall(row * w + col);
        const limit = this.oy + (row + 0.5) * T;
        while (next < things.length && things[next].y <= limit) things[next++].draw();
      }
      while (next < things.length) things[next++].draw();

      if (this.ghost) this.drawGhost(this.ghost);
      if (this.trails) { this.trail(this.trails.ai, P.ai, 3, [6, 5]); this.trail(this.trails.you, P.you, -3, []); }
      if (this.hint) this.drawHint(this.hint);
    }

    wall(cell) {
      const { ctx, T, L } = this, [x, y] = this.xy(cell);
      if (this.mini) { ctx.fillStyle = P.wall; ctx.fillRect(x, y, T, T); return; }
      if (!this.shown.has(cell + this.level.width)) { ctx.fillStyle = P["wall-side"]; ctx.fillRect(x, y + T - L, T, L); }
      ctx.fillStyle = P.wall;
      ctx.fillRect(x, y - L, T, T);
      ctx.fillStyle = P["wall-edge"];
      ctx.fillRect(x, y - L, T, Math.max(1, T * 0.05));
      ctx.strokeStyle = P["wall-side"]; ctx.lineWidth = 1; ctx.globalAlpha = .35;
      ctx.strokeRect(x + .5, y - L + .5, T - 1, T - 1);
      ctx.globalAlpha = 1;
    }

    goal(cell) {
      const { ctx, T } = this, [x, y] = this.xy(cell);
      ctx.fillStyle = ctx.strokeStyle = P.goal;
      if (this.mini) { ctx.fillRect(x + T * .3, y + T * .3, T * .4, T * .4); return; }
      // floor tape: four corner brackets and a centre mark
      const m = T * 0.14, k = T * 0.2;
      ctx.lineWidth = Math.max(2, T * 0.07);
      ctx.beginPath();
      for (const [cx, cy, dx, dy] of [[x + m, y + m, 1, 1], [x + T - m, y + m, -1, 1], [x + m, y + T - m, 1, -1], [x + T - m, y + T - m, -1, -1]]) {
        ctx.moveTo(cx + dx * k, cy); ctx.lineTo(cx, cy); ctx.lineTo(cx, cy + dy * k);
      }
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x + T / 2, y + T * .38); ctx.lineTo(x + T * .62, y + T / 2);
      ctx.lineTo(x + T / 2, y + T * .62); ctx.lineTo(x + T * .38, y + T / 2);
      ctx.fill();
    }

    hatch(cell) {
      const { ctx, T } = this, [x, y] = this.xy(cell);
      ctx.save();
      ctx.beginPath(); ctx.rect(x, y, T, T); ctx.clip();
      ctx.strokeStyle = P.dead; ctx.lineWidth = Math.max(1.5, T * 0.05);
      ctx.beginPath();
      for (let d = -T; d < T; d += T / 4) { ctx.moveTo(x + d, y + T); ctx.lineTo(x + d + T, y); }
      ctx.stroke();
      ctx.restore();
    }

    crate(x, y, home, flagged) {
      const { ctx, T } = this;
      const ok = home ? "-ok" : "";
      if (this.mini) { ctx.fillStyle = P["crate" + ok]; ctx.fillRect(x + 1, y + 1, T - 2, T - 2); return; }
      const m = T * 0.07, s = T - 2 * m, lift = T * 0.13, top = y + m - lift;
      ctx.fillStyle = P.shadow;
      ctx.fillRect(x + m + 2, y + m + 3, s, s);
      ctx.fillStyle = P["crate" + ok + "-side"];
      ctx.fillRect(x + m, y + m, s, s);
      ctx.fillStyle = P["crate" + ok];
      ctx.fillRect(x + m, top, s, s);
      // lid: frame, two planks, one diagonal brace
      ctx.strokeStyle = P["crate" + ok + "-line"]; ctx.lineWidth = Math.max(1.5, T * 0.045);
      const i = s * 0.14;
      ctx.strokeRect(x + m + i, top + i, s - 2 * i, s - 2 * i);
      ctx.beginPath();
      ctx.moveTo(x + m + i, top + s - i); ctx.lineTo(x + m + s - i, top + i);
      ctx.stroke();
      if (flagged) {
        ctx.strokeStyle = P.critical; ctx.lineWidth = Math.max(3, T * 0.08);
        ctx.strokeRect(x + m, top, s, s);
      }
    }

    keeper(x, y) {
      const { ctx, T } = this, cx = x + T / 2, cy = y + T / 2;
      if (this.mini) { ctx.fillStyle = P.body; ctx.beginPath(); ctx.arc(cx, cy, T * .32, 0, 7); ctx.fill(); return; }
      ctx.fillStyle = P.shadow;
      ctx.beginPath(); ctx.ellipse(cx + 1, cy + T * .16, T * .3, T * .2, 0, 0, 7); ctx.fill();
      ctx.save();
      ctx.translate(cx, cy - T * .06);
      ctx.rotate(TURN[this.facing] + Math.PI / 2);          // drawn facing up
      ctx.fillStyle = P.body;                               // shoulders
      ctx.beginPath(); ctx.ellipse(0, T * .03, T * .33, T * .19, 0, 0, 7); ctx.fill();
      ctx.fillStyle = P.hat;                                // hard hat, brim forward
      ctx.beginPath(); ctx.ellipse(0, -T * .08, T * .2, T * .1, 0, 0, 7); ctx.fill();
      ctx.beginPath(); ctx.arc(0, 0, T * .19, 0, 7); ctx.fill();
      ctx.strokeStyle = P["crate-line"]; ctx.lineWidth = Math.max(1, T * .03);
      ctx.beginPath(); ctx.moveTo(0, -T * .17); ctx.lineTo(0, T * .17); ctx.stroke();
      ctx.restore();
    }

    centre(cell) { const [x, y] = this.xy(cell); return [x + this.T / 2, y + this.T / 2]; }

    drawGhost({ player, boxes }) {
      const { ctx, T } = this;
      ctx.strokeStyle = P.trace; ctx.lineWidth = this.mini ? 1 : 2.5;
      if (!this.mini) ctx.setLineDash([5, 4]);
      for (const box of boxes) { const [x, y] = this.xy(box); ctx.strokeRect(x + T * .14, y + T * .14, T * .72, T * .72); }
      ctx.setLineDash([]);
      const [cx, cy] = this.centre(player);
      ctx.beginPath(); ctx.arc(cx, cy, T * .16, 0, 7); ctx.stroke();
    }

    trail(cells, colour, offset, dash) {
      if (!cells || cells.length < 2) return;
      const { ctx } = this;
      ctx.strokeStyle = colour; ctx.lineWidth = Math.max(2.5, this.T * .07); ctx.lineJoin = ctx.lineCap = "round";
      ctx.globalAlpha = .85; ctx.setLineDash(dash);
      ctx.beginPath();
      cells.forEach((cell, i) => { const [x, y] = this.centre(cell); ctx[i ? "lineTo" : "moveTo"](x + offset, y + offset); });
      ctx.stroke();
      ctx.setLineDash([]); ctx.globalAlpha = 1;
    }

    drawHint({ path, box, to }) {
      const { ctx, T } = this;
      this.trail(path, P.ink, 0, [2, 7]);
      const [ax, ay] = this.centre(box), [bx, by] = this.centre(to);
      const ang = Math.atan2(by - ay, bx - ax), h = T * .28;
      ctx.strokeStyle = ctx.fillStyle = P.ink; ctx.lineWidth = Math.max(4, T * .12); ctx.lineCap = "butt";
      ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx - Math.cos(ang) * h * .6, by - Math.sin(ang) * h * .6); ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(bx + Math.cos(ang) * h * .5, by + Math.sin(ang) * h * .5);
      ctx.lineTo(bx - Math.cos(ang - .6) * h, by - Math.sin(ang - .6) * h);
      ctx.lineTo(bx - Math.cos(ang + .6) * h, by - Math.sin(ang + .6) * h);
      ctx.fill();
    }
  }

  return { Board, readPalette };
})();
