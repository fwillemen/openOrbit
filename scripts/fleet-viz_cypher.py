#!/usr/bin/env python3
"""
fleet-viz_cypher.py — Cyberpunk Mission Control Dashboard
=========================================================
A neon-soaked, retro-futuristic TUI for the Fleet multi-agent framework.
Pure Python + ANSI truecolor — zero external dependencies.

Sprite data and game logic are shared with fleet-viz.py (loaded dynamically).

Controls (--watch mode):
  q / Ctrl-C   quit
  g            toggle grid (2×4) / pipeline (1×8) layout
  f / n        cycle focus agent (zoom ×2 sprite)
  c            toggle cyberpunk effects (matrix + feed)
  ← →          shift selected-agent highlight
  Esc          exit focus mode

Usage:
  python3 scripts/fleet-viz_cypher.py [DB_PATH]
  python3 scripts/fleet-viz_cypher.py --watch [DB_PATH]
  python3 scripts/fleet-viz_cypher.py --replay [LOG_PATH]
  python3 scripts/fleet-viz_cypher.py --snapshot [DB_PATH]
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import random
import re as _re
import select
import shutil
import sqlite3
import sys
import termios
import time
import tty


# ══════════════════════════════════════════════════════════════════════════════
# ANSI helpers
# ══════════════════════════════════════════════════════════════════════════════

def fg(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"

def bg(r: int, g: int, b: int) -> str:
    return f"\033[48;2;{r};{g};{b}m"

RESET       = "\033[0m"
BOLD        = "\033[1m"
DIM         = "\033[2m"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

_ANSI_RE = _re.compile(r"\033\[[^m]*m")

def _vis(s: str) -> int:
    """Visible terminal width of a string (strips ANSI codes)."""
    return len(_ANSI_RE.sub("", s))


# ══════════════════════════════════════════════════════════════════════════════
# Cyberpunk colour palette
# ══════════════════════════════════════════════════════════════════════════════

CP: dict[str, tuple[int, int, int]] = {
    # Neon primaries
    "neon_cyan":    (0,   255, 220),
    "neon_magenta": (255, 0,   180),
    "neon_purple":  (180, 0,   255),
    "electric":     (0,   140, 255),
    "neon_green":   (57,  255, 20 ),
    "neon_lime":    (180, 255, 0  ),
    "neon_gold":    (255, 200, 0  ),
    "neon_orange":  (255, 90,  0  ),
    "neon_red":     (255, 30,  60 ),
    "neon_pink":    (255, 60,  140),
    # Backgrounds / neutrals
    "void":         (5,   5,   15 ),
    "border_dim":   (0,   55,  80 ),
    "border_mid":   (0,   110, 150),
    "text_hi":      (220, 220, 255),
    "text_lo":      (70,  70,  120),
    # Matrix stream
    "matrix_green": (0,   90,  25 ),
    "matrix_cyan":  (0,   60,  80 ),
}

# PICO-8 palette kept for sprite pixel colour lookups
P: dict[str, tuple[int, int, int] | None] = {
    "black":    (0,   0,   0  ), "navy":     (29,  43,  83 ),
    "plum":     (126, 37,  83 ), "forest":   (0,   135, 81 ),
    "brown":    (171, 82,  54 ), "slate":    (95,  87,  79 ),
    "silver":   (194, 195, 199), "white":    (255, 241, 232),
    "red":      (255, 0,   77 ), "orange":   (255, 163, 0  ),
    "yellow":   (255, 236, 39 ), "green":    (0,   228, 54 ),
    "blue":     (41,  173, 255), "lavender": (131, 118, 156),
    "pink":     (255, 119, 168), "peach":    (255, 204, 170),
    "cyan":     (0,   228, 228), "indigo":   (63,  63,  176),
    "teal":     (0,   171, 171), "lime":     (148, 255, 74 ),
    "gold":     (255, 200, 0  ), "cream":    (240, 230, 180),
    "magenta":  (180, 0,   180), "purple":   (110, 0,   160),
    "dark":     (20,  20,  30 ), "mid":      (60,  60,  80 ),
    "dim":      (80,  80,  90 ), "_":        None,
}

_TBG = CP["void"]   # transparent pixel background


# ══════════════════════════════════════════════════════════════════════════════
# Animation helpers
# ══════════════════════════════════════════════════════════════════════════════

ARROW_GLYPHS = ["→", "⇒", "➜", "➤"]
ARROW_COLS   = [CP["neon_cyan"], CP["electric"], CP["neon_purple"], CP["neon_magenta"]]
MATRIX_CHARS = "01│/\\-+◆◈▸▹·•∘"


def _scale(rgb: tuple[int, int, int], f: float) -> tuple[int, int, int]:
    return (
        max(0, min(255, int(rgb[0] * f))),
        max(0, min(255, int(rgb[1] * f))),
        max(0, min(255, int(rgb[2] * f))),
    )

def _blend(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))

def _pulse(frame: int, speed: float = 0.4) -> float:
    """Sine wave in [0.0, 1.0]."""
    return math.sin(frame * speed) * 0.5 + 0.5

def _noise(frame: int) -> float:
    """Very subtle per-frame noise for flicker (±3 %)."""
    random.seed(frame * 0x9e37 + 0xdeadbeef)
    return random.uniform(-0.03, 0.03)


# ══════════════════════════════════════════════════════════════════════════════
# Shared data — loaded dynamically from fleet-viz.py
# ══════════════════════════════════════════════════════════════════════════════

def _load_base() -> object:
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "fleet-viz.py")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"fleet-viz_cypher.py requires fleet-viz.py in the same directory.\n"
            f"Expected: {path}"
        )
    spec = importlib.util.spec_from_file_location("_fv_base", path)
    mod  = importlib.util.module_from_spec(spec)        # type: ignore[arg-type]
    spec.loader.exec_module(mod)                        # type: ignore[union-attr]
    return mod

_fv             = _load_base()
SPRITES         = _fv.SPRITES           # type: ignore[attr-defined]
AGENT_ORDER     = _fv.AGENT_ORDER       # type: ignore[attr-defined]
load_db_state   = _fv.load_db_state     # type: ignore[attr-defined]
load_last_events = _fv.load_last_events  # type: ignore[attr-defined]


# ══════════════════════════════════════════════════════════════════════════════
# Sprite renderer (half-block, same technique as fleet-viz.py)
# ══════════════════════════════════════════════════════════════════════════════

SPRITE_W    = 9
PANEL_INNER = 9    # interior content width of each panel
PANEL_W     = PANEL_INNER + 2   # 11 — includes left/right border chars


def render_sprite(
    grid: list[list[str]],
    tint: tuple[int, int, int] | None = None,
    dim_factor: float = 1.0,
) -> list[str]:
    """Return ANSI half-block lines. Each pair of pixel rows → 1 terminal line."""
    lines: list[str] = []
    h = len(grid)
    w = len(grid[0]) if grid else 0
    for ri in range(0, h, 2):
        line = ""
        top = grid[ri]
        bot = grid[ri + 1] if ri + 1 < h else ["_"] * w
        for c in range(w):
            tc = P.get(top[c])
            bc = P.get(bot[c])
            if dim_factor < 1.0:
                if tc is not None:
                    tc = _scale(tc, dim_factor)
                if bc is not None:
                    bc = _scale(bc, dim_factor)
            if tc is None and bc is None:
                line += " "
            elif tc is None:
                line += bg(*bc) + fg(*_TBG) + "▄" + RESET
            elif bc is None:
                line += fg(*tc) + bg(*_TBG) + "▀" + RESET
            else:
                if tint and top[c] not in ("black", "dark", "_"):
                    tc = tint
                line += fg(*tc) + bg(*bc) + "▀" + RESET
        lines.append(line)
    return lines


# ══════════════════════════════════════════════════════════════════════════════
# Status colours / icons (cyberpunk overrides)
# ══════════════════════════════════════════════════════════════════════════════

_ST_COL = {
    "active":  CP["neon_cyan"],
    "done":    CP["neon_green"],
    "fail":    CP["neon_red"],
    "blocked": CP["neon_orange"],
    "idle":    CP["border_dim"],
    "unknown": CP["text_lo"],
}
_ST_ICON = {
    "active":  "◆ ACTIVE",
    "done":    "✓ DONE  ",
    "fail":    "✗ FAILED",
    "blocked": "○ BLOCKED",
    "idle":    "· idle  ",
    "unknown": "? ????? ",
}
_AGENT_COLS = {
    "product-owner":   CP["neon_gold"],
    "scrum-master":    CP["neon_purple"],
    "architect":       CP["neon_cyan"],
    "programmer":      CP["neon_green"],
    "code-reviewer":   CP["neon_orange"],
    "tester":          CP["electric"],
    "docs-writer":     CP["neon_magenta"],
    "retrospective":   CP["neon_pink"],
}


# ══════════════════════════════════════════════════════════════════════════════
# Cyberpunk panel renderer
# ══════════════════════════════════════════════════════════════════════════════

def render_cypher_panel(
    agent_id: str,
    status: str,
    frame: int,
    selected: bool = False,
) -> list[str]:
    """Return 12 lines (header + 8 sprite + status + footer + neon strip).

    Layout (all 11 chars wide = PANEL_W):
        ╭──[ARC]──╮   header with agent label
        │ sprite  │   × 8 half-block lines
        │ ◆ ACTIVE│   status text
        ╰─────────╯   footer
        ▔▔▔▔▔▔▔▔▔▔▔   thin neon colour strip (status tint)
    """
    spec  = SPRITES[agent_id]
    label = spec["label"][:3]
    inner = PANEL_INNER  # 9

    # ── Visual modifiers by status ────────────────────────────────────────────
    pf = 0.85 + 0.15 * _pulse(frame)
    if status == "active":
        nf       = pf + _noise(frame)
        tint     = _scale(spec["active_color"], nf)
        dim      = nf
        b_rgb    = _scale(CP["neon_cyan"], pf)
    elif status == "done":
        tint, dim, b_rgb = None, 0.78, CP["neon_green"]
    elif status == "fail":
        tint, dim = None, 0.65
        b_rgb     = _scale(CP["neon_red"], 0.8 + 0.2 * _pulse(frame, 0.8))
    elif status == "blocked":
        tint, dim, b_rgb = None, 0.60, CP["neon_orange"]
    else:                               # idle / unknown
        tint, dim, b_rgb = None, 0.22, CP["border_dim"]

    if selected:
        b_rgb = _blend(b_rgb, CP["neon_magenta"], 0.55)

    b = fg(*b_rgb)

    # ── Sprite ────────────────────────────────────────────────────────────────
    sprite_frame = spec["frames"][frame % len(spec["frames"])]
    sprite_lines = render_sprite(sprite_frame, tint=tint, dim_factor=dim)

    # ── Header: ╭──[LABEL]──╮ ───────────────────────────────────────────────
    ld     = len(label)
    h_lpad = (inner - 2 - ld) // 2       # chars left of "[label]"
    h_rpad = inner - 2 - ld - h_lpad
    name_c = fg(*CP["text_hi"]) if status != "idle" else fg(*CP["text_lo"])
    header = (
        b + "╭" + "─" * h_lpad + "[" + RESET
        + BOLD + name_c + label + RESET
        + b + "]" + "─" * h_rpad + "╮" + RESET
    )

    # ── Status row: │ ◆ ACTIVE │ ────────────────────────────────────────────
    st_raw  = _ST_ICON.get(status, "? ????? ")
    st_txt  = st_raw[:inner].ljust(inner)[:inner]   # exactly 9 chars
    st_row  = (
        b + "│" + RESET
        + fg(*_ST_COL.get(status, CP["text_lo"])) + BOLD + st_txt + RESET
        + b + "│" + RESET
    )

    # ── Footer + neon strip ───────────────────────────────────────────────────
    footer    = b + "╰" + "─" * inner + "╯" + RESET
    strip_rgb = _scale(_ST_COL.get(status, CP["border_dim"]), 0.40)
    strip     = fg(*strip_rgb) + "▔" * PANEL_W + RESET

    # Assemble
    panel: list[str] = [header]
    for sl in sprite_lines:
        panel.append(b + "│" + RESET + sl + b + "│" + RESET)
    panel.append(st_row)
    panel.append(footer)
    panel.append(strip)
    return panel   # 12 rows


# ══════════════════════════════════════════════════════════════════════════════
# Matrix background strip
# ══════════════════════════════════════════════════════════════════════════════

def matrix_strip(width: int, frame: int, n_rows: int = 1) -> list[str]:
    """Faint scrolling matrix characters for cyberpunk ambience."""
    seed = frame // 6          # slow scroll: new pattern every 6 frames
    rng  = random.Random(seed)
    rows: list[str] = []
    for row_i in range(n_rows):
        line = ""
        for col_i in range(width):
            phase = (frame // 3 + col_i * 7 + row_i * 13) % 32
            if phase < 8:
                char  = rng.choice(MATRIX_CHARS)
                alpha = 0.06 + 0.18 * (1 - phase / 8)
                c     = _scale(CP["matrix_green"], alpha)
                line += fg(*c) + char
            elif phase < 12 and rng.random() < 0.04:
                c = _scale(CP["neon_cyan"], 0.07)
                line += fg(*c) + rng.choice("01·")
            else:
                line += " "
        rows.append(line + RESET)
    return rows


# ══════════════════════════════════════════════════════════════════════════════
# Activity feed
# ══════════════════════════════════════════════════════════════════════════════

# Each entry: (3-char label, RGB colour, message string)
_feed: list[tuple[str, tuple[int, int, int], str]] = []


def _feed_push(agent: str, msg: str) -> None:
    label = SPRITES[agent]["label"] if agent in SPRITES else agent[:3].upper()
    col   = _AGENT_COLS.get(agent, CP["text_lo"])
    _feed.append((label, col, msg))
    if len(_feed) > 60:
        _feed.pop(0)


def _feed_from_events(events: dict[str, dict]) -> None:
    for agent, ev in events.items():
        action  = ev.get("action", "")
        item_id = ev.get("item_id", "")
        outcome = ev.get("outcome", "")
        parts   = [x for x in [action, item_id] if x]
        if outcome:
            parts.append(f"[{outcome}]")
        msg = " ".join(parts).strip()
        if msg:
            _feed_push(agent, msg)


def _render_feed(max_w: int, n: int = 3) -> list[str]:
    """Return n feed lines, each truncated to max_w visible chars."""
    recent = _feed[-n:]
    lines: list[str] = []
    for label, col_rgb, msg in recent:
        prefix = f"[{label}]▸ "
        avail  = max_w - len(prefix)
        body   = msg[:max(avail, 0)]
        lines.append(
            fg(*col_rgb) + prefix + RESET
            + fg(*CP["text_lo"]) + body + RESET
        )
    while len(lines) < n:
        lines.append(fg(*CP["text_lo"]) + "·" * min(8, max_w) + RESET)
    return lines


# ══════════════════════════════════════════════════════════════════════════════
# Sparkline subsystem
# ══════════════════════════════════════════════════════════════════════════════

_spark: dict[str, list[str]] = {}
_SPARK_CH: dict[str, str] = {
    "active": "█", "done": "▓", "fail": "▌",
    "blocked": "▒", "idle": "░", "unknown": "·",
}
_SPARK_CO: dict[str, tuple[int, int, int]] = {
    "active":  CP["neon_cyan"],   "done":    CP["neon_green"],
    "fail":    CP["neon_red"],    "blocked": CP["neon_orange"],
    "idle":    CP["border_dim"],  "unknown": CP["text_lo"],
}


def _spark_update(agent_status: dict[str, str]) -> None:
    for ag, st in agent_status.items():
        h = _spark.setdefault(ag, [])
        h.append(st)
        if len(h) > 20:
            h.pop(0)


def _sparkline(agent_id: str, w: int = 6) -> str:
    hist   = _spark.get(agent_id, [])
    recent = hist[-w:]
    out    = "".join(
        fg(*_SPARK_CO.get(s, _SPARK_CO["unknown"])) + _SPARK_CH.get(s, "·")
        for s in recent
    )
    out += fg(*_SPARK_CO["idle"]) + "·" * (w - len(recent))
    return out + RESET


def _spark_row(agent_ids: list[str], agent_status: dict[str, str], W: int) -> str:
    """One sparkline strip aligned under agent panels."""
    total_w = len(agent_ids) * PANEL_W + (len(agent_ids) - 1)
    pad     = max(0, (W - 2 - total_w) // 2)
    parts   = []
    for ag in agent_ids:
        lbl = SPRITES[ag]["label"]
        st  = agent_status.get(ag, "idle")
        lc  = fg(*_SPARK_CO.get(st, _SPARK_CO["idle"]))
        bar = _sparkline(ag, w=6)
        # " " + label(3) + " " + bar(6) = 11 = PANEL_W ✓
        parts.append(" " + lc + lbl + RESET + " " + bar)
    return " " * pad + " ".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
# Neon gradient progress bar
# ══════════════════════════════════════════════════════════════════════════════

def _neon_bar(done: int, total: int, w: int = 20) -> str:
    if not total:
        return fg(*CP["border_dim"]) + "░" * w + RESET
    filled = max(0, min(w, int(w * done / total)))
    bar = ""
    for i in range(w):
        if i < filled:
            t = i / max(w - 1, 1)
            if t < 0.33:
                c = _blend(CP["neon_red"],    CP["neon_orange"], t / 0.33)
            elif t < 0.67:
                c = _blend(CP["neon_orange"], CP["neon_gold"],   (t - 0.33) / 0.34)
            else:
                c = _blend(CP["neon_gold"],   CP["neon_green"],  (t - 0.67) / 0.33)
            bar += fg(*c) + "█"
        else:
            bar += fg(*CP["border_dim"]) + "░"
    return bar + RESET


# ══════════════════════════════════════════════════════════════════════════════
# Keyboard input (non-blocking, Unix only)
# ══════════════════════════════════════════════════════════════════════════════

def getch_nonblock() -> str | None:
    if not sys.stdin.isatty():
        return None
    try:
        fd  = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            r, _, _ = select.select([sys.stdin], [], [], 0)
            if r:
                ch = sys.stdin.read(1)
                if ch == "\x1b":                          # escape or arrow
                    r2, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if r2:
                        ch2 = sys.stdin.read(1)
                        if ch2 == "[":
                            r3, _, _ = select.select([sys.stdin], [], [], 0.05)
                            if r3:
                                ch3 = sys.stdin.read(1)
                                if ch3 == "C": return "RIGHT"
                                if ch3 == "D": return "LEFT"
                return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Terminal bell tracker
# ══════════════════════════════════════════════════════════════════════════════

_prev_status: dict[str, str] = {}

def _check_bells(status: dict[str, str]) -> int:
    """0 = quiet, 1 = single ping (done), 2 = double ping (fail)."""
    result = 0
    for ag, st in status.items():
        prev = _prev_status.get(ag, "idle")
        if prev != "done" and st == "done":
            result = max(result, 1)
        elif prev != "fail" and st == "fail":
            result = max(result, 2)
        _prev_status[ag] = st
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Panel row stacking
# ══════════════════════════════════════════════════════════════════════════════

def hstack(panels: list[list[str]], sep: str = "") -> list[str]:
    if not panels:
        return []
    height = max(len(p) for p in panels)
    padded = [p + [""] * (height - len(p)) for p in panels]
    return [sep.join(row[r] for row in padded) for r in range(height)]


def _agent_row(
    agent_ids: list[str],
    agent_status: dict[str, str],
    frame: int,
    arrow_str: str,
    selected_agent: str | None,
) -> tuple[list[str], int]:
    """Render one horizontal strip of agent panels; return (rows, content_width)."""
    panels = [
        render_cypher_panel(ag, agent_status.get(ag, "idle"), frame,
                            selected=(ag == selected_agent))
        for ag in agent_ids
    ]
    n = len(agent_ids)
    all_p: list[list[str]] = []
    for i, p in enumerate(panels):
        all_p.append(p)
        if i < n - 1:
            h   = len(p)
            arr = [" "] * h
            arr[h // 2 - 2] = arrow_str   # mid-sprite row
            all_p.append(arr)
    stacked = hstack(all_p, sep="")
    total_w = n * PANEL_W + (n - 1) * 1   # 11 per panel + 1 per arrow gap
    return stacked, total_w


# ══════════════════════════════════════════════════════════════════════════════
# Focus mode (2× zoomed single-agent view)
# ══════════════════════════════════════════════════════════════════════════════

def _focus_lines(
    agent_id: str,
    agent_status: dict[str, str],
    frame: int,
    W: int,
) -> list[str]:
    """Return content lines (NO outer ║ prefix) for the focused agent view."""
    spec   = SPRITES[agent_id]
    status = agent_status.get(agent_id, "idle")
    pf     = 0.85 + 0.15 * _pulse(frame)
    dim    = (pf + _noise(frame)) if status == "active" else (0.78 if status == "done" else 0.28)
    tint   = _scale(spec["active_color"], pf) if status == "active" else None
    b_rgb  = _scale(_ST_COL.get(status, CP["text_lo"]), 0.7 + 0.3 * _pulse(frame, 0.6))
    bdr    = fg(*b_rgb)

    grid       = spec["frames"][frame % len(spec["frames"])]
    sp_lines   = render_sprite(grid, tint=tint, dim_factor=dim)

    inner_w = W - 4   # inside ╭ and ╮ with 2-space outer margin

    lines: list[str] = []
    lines.append("  " + bdr + "╭" + "─" * inner_w + "╮" + RESET)

    for sl in sp_lines:
        # 2× horizontal: double each non-ANSI character
        expanded = ""
        i = 0
        while i < len(sl):
            if sl[i] == "\033":
                j = sl.index("m", i) + 1
                expanded += sl[i:j]
                i = j
            else:
                expanded += sl[i] * 2
                i += 1
        pad = max(0, (inner_w - SPRITE_W * 2) // 2)
        lines.append(
            "  " + bdr + "│" + RESET
            + " " * pad + expanded + " " * pad
            + bdr + "│" + RESET
        )

    # Name + status bar
    st_col  = fg(*_ST_COL.get(status, CP["text_lo"]))
    st_icon = _ST_ICON.get(status, "?")
    name_c  = fg(*CP["text_hi"])
    name_ln = (
        f"  {bdr}│{RESET}  {BOLD}{name_c}{spec['name'].upper()}{RESET}"
        f"   {st_col}{st_icon}{RESET}"
        f"   {_sparkline(agent_id, w=12)}"
    )
    lines.append(name_ln)
    lines.append(
        f"  {bdr}│{RESET}  {DIM}f/n = next agent   Esc = exit focus{RESET}"
    )
    lines.append("  " + bdr + "╰" + "─" * inner_w + "╯" + RESET)
    return lines


# ══════════════════════════════════════════════════════════════════════════════
# Effects toggle state
# ══════════════════════════════════════════════════════════════════════════════

class FX:
    """Runtime-togglable visual effects."""
    matrix: bool = True
    feed:   bool = True


# ══════════════════════════════════════════════════════════════════════════════
# Main dashboard renderer
# ══════════════════════════════════════════════════════════════════════════════

_CYPHER_TITLE = "◆ FLEET CYPHER  MISSION CONTROL ◆"


def render_dashboard(
    state: dict,
    events: dict[str, dict],
    frame: int = 0,
    term_width: int = 120,
    focus_agent: str | None = None,
    selected_agent: str | None = None,
    fx: FX | None = None,
    use_grid: bool = False,
) -> str:
    if fx is None:
        fx = FX()

    W   = min(term_width, 126)
    out: list[str] = []

    bdr = fg(*CP["border_mid"])

    # ── Animated arrow (colour cycles through neon spectrum) ─────────────────
    ai        = frame % len(ARROW_GLYPHS)
    arrow_col = _blend(ARROW_COLS[ai], ARROW_COLS[(ai + 1) % len(ARROW_COLS)],
                       _pulse(frame, 0.6))
    arrow_str = fg(*arrow_col) + ARROW_GLYPHS[ai] + RESET

    sprint = state["sprint"]["name"] if state["sprint"] else "NO SPRINT"

    # ── Outer top border ──────────────────────────────────────────────────────
    out.append(bdr + "╔" + "═" * (W - 2) + "╗" + RESET)

    # ── Title bar ─────────────────────────────────────────────────────────────
    title_col  = fg(*_scale(CP["neon_magenta"], 0.8 + 0.2 * _pulse(frame, 0.3)))
    sprint_col = fg(*CP["neon_cyan"])
    gap = W - 2 - len(_CYPHER_TITLE) - 2 - len(sprint)
    out.append(
        bdr + "║" + RESET
        + " " + BOLD + title_col + _CYPHER_TITLE + RESET
        + " " * max(gap, 1)
        + sprint_col + sprint + RESET
        + bdr + "║" + RESET
    )
    out.append(bdr + "╠" + "═" * (W - 2) + "╣" + RESET)

    # ── Matrix decoration strip ───────────────────────────────────────────────
    if fx.matrix and W >= 80:
        for ml in matrix_strip(W - 2, frame, n_rows=1):
            out.append(bdr + "║" + RESET + ml)
        out.append(bdr + "╟" + "─" * (W - 2) + "╢" + RESET)

    # ── Agent panels (focus or grid/row) ─────────────────────────────────────
    ag_status = state["agent_status"]

    if focus_agent and focus_agent in SPRITES:
        for fl in _focus_lines(focus_agent, ag_status, frame, W):
            out.append(bdr + "║" + RESET + fl)
    else:
        def _emit(ids: list[str]) -> None:
            stacked, tw = _agent_row(ids, ag_status, frame, arrow_str, selected_agent)
            pad = max(0, (W - 2 - tw) // 2)
            for sl in stacked:
                out.append(bdr + "║" + RESET + " " * pad + sl)

        if use_grid:
            _emit(AGENT_ORDER[:4])
            out.append(bdr + "╟" + "─" * (W - 2) + "╢" + RESET)
            _emit(AGENT_ORDER[4:])
        else:
            _emit(AGENT_ORDER)

    # ── Sparkline strip ───────────────────────────────────────────────────────
    out.append(bdr + "╟" + "─" * (W - 2) + "╢" + RESET)
    if use_grid:
        out.append(bdr + "║" + RESET + _spark_row(AGENT_ORDER[:4], ag_status, W))
        out.append(bdr + "║" + RESET + _spark_row(AGENT_ORDER[4:], ag_status, W))
    else:
        out.append(bdr + "║" + RESET + _spark_row(AGENT_ORDER, ag_status, W))

    # ── Activity feed ─────────────────────────────────────────────────────────
    if fx.feed and _feed:
        out.append(bdr + "╟" + "─" * (W - 2) + "╢" + RESET)
        feed_hdr = (
            fg(*CP["neon_magenta"]) + BOLD + " ▸ ACTIVITY FEED" + RESET
        )
        out.append(bdr + "║" + RESET + feed_hdr)
        feed_w = W - 6
        for fl in _render_feed(feed_w, n=3):
            out.append(bdr + "║" + RESET + "  " + fl)

    # ── Metrics ───────────────────────────────────────────────────────────────
    out.append(bdr + "╠" + "═" * (W - 2) + "╣" + RESET)
    done  = state["items_done"]
    total = state["items_total"]
    cov   = f"{state['coverage']:.1f}%" if state["coverage"] else "—"
    cost  = f"${state['cost_usd']:.2f}"

    if total:
        bar   = _neon_bar(done, total, w=20)
        m_line = (
            f"  Items: {fg(*CP['neon_gold'])}{done}/{total}{RESET}  "
            f"{bar}  "
            f"Coverage: {fg(*CP['electric'])}{cov}{RESET}  "
            f"Cost: {fg(*CP['neon_pink'])}{cost}{RESET}"
        )
    else:
        m_line = f"  {DIM}No sprint active — init: bash scripts/init-state.sh{RESET}"
    out.append(bdr + "║" + RESET + m_line)

    # ── Controls footer ───────────────────────────────────────────────────────
    sel_lbl = f" ({SPRITES[selected_agent]['label']})" if selected_agent else ""
    hl      = fg(*CP["neon_cyan"])
    lo      = fg(*CP["text_lo"])
    ctrl_ln = (
        f"  {lo}[{hl}q{lo}]quit  [{hl}g{lo}]grid  "
        f"[{hl}f{lo}]focus{sel_lbl}  [{hl}c{lo}]fx  "
        f"[{hl}←→{lo}]select{RESET}"
    )
    out.append(bdr + "║" + RESET + ctrl_ln)
    out.append(bdr + "╚" + "═" * (W - 2) + "╝" + RESET)

    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════════════════
# Replay mode
# ══════════════════════════════════════════════════════════════════════════════

def replay_mode(log_path: str, term_width: int) -> None:
    if not os.path.exists(log_path):
        print(f"⚠️  No event log at {log_path}")
        return

    with open(log_path) as f:
        raw = [json.loads(line) for line in f if line.strip()]

    if not raw:
        print("No events in log.")
        return

    fake: dict = {
        "sprint": {"name": "Replay"},
        "items": [],
        "agent_status": {a: "idle" for a in AGENT_ORDER},
        "coverage": None,
        "cost_usd": 0.0,
        "items_done": 0,
        "items_total": 0,
    }
    events: dict[str, dict] = {}
    fx = FX()
    print(HIDE_CURSOR)
    try:
        first = True
        af    = 0
        for ev in raw:
            agent = ev.get("agent", "")
            if agent in AGENT_ORDER:
                oc = ev.get("outcome", "")
                fake["agent_status"][agent] = (
                    "done" if oc == "pass" else "fail" if oc == "fail" else "active"
                )
            events[agent] = ev
            _feed_from_events({agent: ev})
            _spark_update(fake["agent_status"])

            for _ in range(4):
                dash = render_dashboard(
                    fake, events, af, term_width,
                    focus_agent=None, selected_agent=AGENT_ORDER[0],
                    fx=fx, use_grid=(term_width < 120),
                )
                n = dash.count("\n") + 1
                if not first:
                    sys.stdout.write(f"\033[{n}A")
                sys.stdout.write(dash + "\n")
                sys.stdout.flush()
                first = False
                af += 1
                time.sleep(0.12)
    finally:
        print(SHOW_CURSOR)


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    args     = sys.argv[1:]
    watch    = "--watch"    in args
    replay   = "--replay"   in args
    snapshot = "--snapshot" in args
    pos      = [a for a in args if not a.startswith("--")]
    root     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    tw, _ = shutil.get_terminal_size(fallback=(80, 24))

    # Graceful degradation
    if tw < 60:
        return
    if not sys.stdout.isatty() and not (watch or replay or snapshot):
        return

    if replay:
        lp = pos[0] if pos else os.path.join(root, "state", "agent-log.ndjson")
        replay_mode(lp, tw)
        return

    db_path  = pos[0] if pos else os.path.join(root, "state", "fleet.db")
    log_path = os.path.join(os.path.dirname(db_path), "agent-log.ndjson")

    # One-shot snapshot (non-TTY-safe for testing)
    if snapshot:
        state  = load_db_state(db_path)
        events = load_last_events(log_path)
        _feed_from_events(events)
        _spark_update(state["agent_status"])
        print(render_dashboard(
            state, events, 0, tw,
            focus_agent=None, selected_agent=AGENT_ORDER[0],
            fx=FX(), use_grid=(tw < 120),
        ))
        return

    # Interactive / watch loop
    fx           = FX()
    frame        = 0
    dash_lines   = 0
    state: dict  = {}
    events: dict = {}
    use_grid     = (tw < 120)
    focus_idx: int | None = None
    sel_idx      = 0

    print(HIDE_CURSOR)
    try:
        while True:
            # Reload DB every 4 frames (~0.5 s each → ~2 s interval)
            if frame % 4 == 0 or not state:
                state  = load_db_state(db_path)
                events = load_last_events(log_path)
                _feed_from_events(events)

            _spark_update(state["agent_status"])

            # Sound feedback
            bells = _check_bells(state["agent_status"])
            if bells >= 2:
                sys.stdout.write("\a\a")
            elif bells == 1:
                sys.stdout.write("\a")

            focus_agent    = AGENT_ORDER[focus_idx] if focus_idx is not None else None
            selected_agent = AGENT_ORDER[sel_idx]

            dash = render_dashboard(
                state, events, frame, tw,
                focus_agent=focus_agent,
                selected_agent=selected_agent,
                fx=fx,
                use_grid=use_grid,
            )
            n = dash.count("\n") + 1

            if dash_lines:
                sys.stdout.write(f"\033[{dash_lines}A")
            sys.stdout.write(dash + "\n")
            sys.stdout.flush()
            dash_lines = n
            frame += 1

            if not watch:
                break

            # ~12 FPS animation tick
            time.sleep(0.08)

            # Non-blocking key handler
            key = getch_nonblock()
            if key in ("q", "Q", "\x03"):
                break
            elif key in ("g", "G"):
                use_grid = not use_grid
            elif key in ("f", "F", "n", "N"):
                if focus_idx is None:
                    focus_idx = sel_idx
                else:
                    focus_idx = (focus_idx + 1) % len(AGENT_ORDER)
            elif key == "\x1b":
                focus_idx = None                     # Esc exits focus
            elif key in ("c", "C"):
                fx.matrix = not fx.matrix
                fx.feed   = not fx.feed
            elif key == "RIGHT":
                sel_idx = (sel_idx + 1) % len(AGENT_ORDER)
                if focus_idx is not None:
                    focus_idx = sel_idx
            elif key == "LEFT":
                sel_idx = (sel_idx - 1) % len(AGENT_ORDER)
                if focus_idx is not None:
                    focus_idx = sel_idx

    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
