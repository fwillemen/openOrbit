#!/usr/bin/env python3
"""
fleet-viz.py — Pixelated Agent Mission Control Dashboard
=========================================================
Renders all 8 fleet agents as pixel-art sprites with live status.
Uses ANSI truecolor + Unicode half-block characters (▀) — zero pip deps.

Usage:
  python3 scripts/fleet-viz.py [DB_PATH]            # snapshot (default)
  python3 scripts/fleet-viz.py --watch [DB_PATH]    # auto-refresh every 2s
  python3 scripts/fleet-viz.py --replay [LOG_PATH]  # animate agent-log.ndjson

Graceful degradation: exits silently if terminal < 60 cols or non-interactive.
"""
from __future__ import annotations

import json
import math
import os
import select
import shutil
import sqlite3
import sys
import termios
import time
import tty
import unicodedata


# ── ANSI helpers ──────────────────────────────────────────────────────────────

def fg(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"

def bg(r: int, g: int, b: int) -> str:
    return f"\033[48;2;{r};{g};{b}m"

RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
SAVE_POS    = "\033[s"
RESTORE_POS = "\033[u"
CLEAR_DOWN  = "\033[J"


# ── Animation / visual helpers ────────────────────────────────────────────────

ARROW_GLYPHS = ["→", "⇒", "➜", "➤"]

def _scale_rgb(rgb: tuple[int,int,int], factor: float) -> tuple[int,int,int]:
    """Scale an RGB colour by a factor, clamped to [0, 255]."""
    return (
        max(0, min(255, int(rgb[0] * factor))),
        max(0, min(255, int(rgb[1] * factor))),
        max(0, min(255, int(rgb[2] * factor))),
    )

def _blend_rgb(
    a: tuple[int,int,int], b: tuple[int,int,int], t: float
) -> tuple[int,int,int]:
    """Linearly interpolate between two RGB colours, t in [0, 1]."""
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )

def _pulse_factor(frame: int) -> float:
    """Return 0.85..1.00 following a slow sine wave (period ~16 frames)."""
    return 0.85 + 0.15 * (math.sin(frame * 0.4) * 0.5 + 0.5)

def _gradient_bar(done: int, total: int, width: int = 18) -> str:
    """Progress bar that grades red → orange → yellow → green."""
    if not total:
        return fg(*P["slate"]) + "░" * width + RESET
    filled = max(0, min(width, int(width * done / total)))
    bar = ""
    for i in range(width):
        if i < filled:
            t = i / max(width - 1, 1)
            if t < 0.33:
                c = _blend_rgb(P["red"],    P["orange"], t / 0.33)
            elif t < 0.67:
                c = _blend_rgb(P["orange"], P["yellow"], (t - 0.33) / 0.34)
            else:
                c = _blend_rgb(P["yellow"], P["green"],  (t - 0.67) / 0.33)
            bar += fg(*c) + "█"
        else:
            bar += fg(*P["slate"]) + "░"
    return bar + RESET

# Sparkline history: last 20 per-frame status for each agent.
_spark_hist: dict[str, list[str]] = {}
_SPARK_CHARS = {
    "active": "█", "done": "▓", "fail": "▌",
    "blocked": "▒", "idle": "░", "unknown": "·",
}
_SPARK_COLS = {
    "active": (255, 200, 0), "done": (0, 228, 54), "fail": (255, 0, 77),
    "blocked": (255, 163, 0), "idle": (60, 60, 80), "unknown": (95, 87, 79),
}

def _update_spark(agent_status: dict[str, str]) -> None:
    for ag, st in agent_status.items():
        hist = _spark_hist.setdefault(ag, [])
        hist.append(st)
        if len(hist) > 20:
            hist.pop(0)

def _render_sparkline(agent_id: str, bar_w: int = 9) -> str:
    hist = _spark_hist.get(agent_id, [])
    recent = hist[-bar_w:]
    out = ""
    for s in recent:
        out += fg(*_SPARK_COLS.get(s, _SPARK_COLS["unknown"])) + _SPARK_CHARS.get(s, "·")
    out += fg(*_SPARK_COLS["idle"]) + "·" * (bar_w - len(recent))
    return out + RESET

# Terminal-bell tracking (ring only once per status transition)
_prev_status: dict[str, str] = {}

def _check_bells(agent_status: dict[str, str]) -> bool:
    """Return True and update history if a bell should ring."""
    ring = False
    for ag, st in agent_status.items():
        prev = _prev_status.get(ag, "idle")
        if prev not in ("done", "fail") and st in ("done", "fail"):
            ring = True
        _prev_status[ag] = st
    return ring

def _getch_nonblock() -> str | None:
    """Return a single keypress without blocking (None if none pending)."""
    if not sys.stdin.isatty():
        return None
    try:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            r, _, _ = select.select([sys.stdin], [], [], 0)
            if r:
                return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        pass
    return None


# ── PICO-8 inspired palette ────────────────────────────────────────────────────

P = {
    "black":    (0,   0,   0  ),
    "navy":     (29,  43,  83 ),
    "plum":     (126, 37,  83 ),
    "forest":   (0,   135, 81 ),
    "brown":    (171, 82,  54 ),
    "slate":    (95,  87,  79 ),
    "silver":   (194, 195, 199),
    "white":    (255, 241, 232),
    "red":      (255, 0,   77 ),
    "orange":   (255, 163, 0  ),
    "yellow":   (255, 236, 39 ),
    "green":    (0,   228, 54 ),
    "blue":     (41,  173, 255),
    "lavender": (131, 118, 156),
    "pink":     (255, 119, 168),
    "peach":    (255, 204, 170),
    "cyan":     (0,   228, 228),
    "indigo":   (63,  63,  176),
    "teal":     (0,   171, 171),
    "lime":     (148, 255, 74 ),
    "gold":     (255, 200, 0  ),
    "cream":    (240, 230, 180),
    "magenta":  (180, 0,   180),
    "purple":   (110, 0,   160),
    "dark":     (20,  20,  30 ),
    "mid":      (60,  60,  80 ),
    "dim":      (80,  80,  90 ),
    "_":        None,           # transparent / use terminal bg
}

_TBG = (15, 15, 25)  # terminal background colour


# ── Sprite renderer (half-block technique) ─────────────────────────────────────
# Each sprite is a list of rows; each row is a list of palette key strings.
# Width W, height H (must be even). Renders as W chars × H/2 lines.
# Each char: ▀ with fg=top-pixel-color, bg=bottom-pixel-color.

def render_sprite(
    grid: list[list[str]],
    tint: tuple[int,int,int] | None = None,
    dim_factor: float = 1.0,
) -> list[str]:
    """Return a list of ANSI-colored strings, one per rendered line."""
    lines = []
    h = len(grid)
    w = len(grid[0]) if grid else 0
    for row_idx in range(0, h, 2):
        line = ""
        top_row    = grid[row_idx]
        bot_row    = grid[row_idx + 1] if row_idx + 1 < h else ["_"] * w
        for col in range(w):
            tc = P.get(top_row[col])
            bc = P.get(bot_row[col])
            if dim_factor < 1.0:
                if tc is not None:
                    tc = _scale_rgb(tc, dim_factor)
                if bc is not None:
                    bc = _scale_rgb(bc, dim_factor)
            if tc is None and bc is None:
                line += " "
            elif tc is None:
                # transparent top → use terminal bg
                line += bg(*bc) + fg(*_TBG) + "▄" + RESET
            elif bc is None:
                line += fg(*tc) + bg(*_TBG) + "▀" + RESET
            else:
                if tint and top_row[col] not in ("black", "dark", "_"):
                    tc = tint
                line += fg(*tc) + bg(*bc) + "▀" + RESET
        lines.append(line)
    return lines


# ── Agent sprite definitions (5 wide × 8 tall) ────────────────────────────────

def _s(*rows: str) -> list[list[str]]:
    """Parse sprite shorthand: 5-char rows → list[list[palette_key]]."""
    mapping = {
        ".": "_",       # transparent
        "W": "white",   "w": "silver",  "G": "green",   "g": "lime",
        "B": "blue",    "b": "navy",    "N": "navy",     "n": "indigo",
        "Y": "yellow",  "y": "gold",    "O": "orange",   "o": "brown",
        "R": "red",     "P": "peach",   "p": "pink",     "S": "slate",
        "K": "black",   "D": "dark",    "d": "dim",      "M": "mid",
        "C": "cyan",    "c": "teal",    "V": "lavender", "v": "plum",
        "U": "purple",  "u": "magenta", "F": "forest",   "L": "cream",
        "I": "indigo",
    }
    result = []
    for row in rows:
        result.append([mapping.get(ch, "_") for ch in row])
    return result


# Each sprite: 9×16 colour grid. Two frames (idle vs. active) for animation.
# Rendering: half-block ▀ pairs 2 pixel rows → 1 terminal line, giving 9 chars × 8 lines.
# Distinctiveness guide:
#   PO  = navy suit + gold star badge + briefcase
#   SM  = lavender robe + baton raised to right
#   ARC = TALL indigo wizard hat (6 rows!) + cyan scroll
#   PRG = green hoodie + dark laptop (bottom half)
#   CRV = FULL-WIDTH brown hat brim (2 rows) + yellow magnifying glass
#   TST = white lab coat + cyan+lime bubbling flask
#   DOC = cream monk cowl + white quill + open book
#   RET = magenta hood tip + cyan crystal ball (bottom)

SPRITES: dict[str, dict] = {
    "product-owner": {
        "label": "PO",
        "name": "Product Owner",
        "persona": "executive",
        "frames": [
            _s(".....y...",  # gold hair peak
               "..yPPPy..",  # gold hair sides + peach face
               "..PKyKP..",  # BLACK eyes (K) + gold center dot
               "..yPPPy..",  # chin + gold edges
               ".bbbbbbbb",  # WIDE navy jacket — full shoulders
               "bbbybbbb.",  # jacket + gold star BADGE (y)!
               "bbbWbbbb.",  # white shirt center visible
               "bbbWbboo.",  # shirt + brown BRIEFCASE in hand (o)!
               "bbbWbboo.",  # briefcase continues
               "bbbWbboo.",  # briefcase bottom
               ".bbbbbbb.",  # waist
               ".bbbbbbb.",  # hips
               "..KK..KK.",  # dark trouser legs (WIDE GAP = distinctive silhouette)
               "..KK..KK.",
               "..KK..KK.",
               "..WW..WW."),  # white shoes
            _s(".....y...",
               "..yPPPy..",
               "..PKyKP..",
               "..yPPPy..",
               ".bbbbbbbb",
               "bbbybbbb.",
               "bbbWbbbb.",
               "bbbWbbwww",  # active: silver phone raised!
               "bbbWbbwww",
               "bbbWbbwww",
               ".bbbbbbb.",
               ".bbbbbbb.",
               "..KK..KK.",
               "..KK..KK.",
               "..KK..KK.",
               "..WW..WW."),
        ],
        "active_color": P["gold"],
        "done_color":   P["green"],
    },
    "scrum-master": {
        "label": "SM",
        "name": "Scrum Master",
        "persona": "conductor",
        "frames": [
            _s("...vvv...",  # plum conductor's hat top
               "..vvvvv..",  # hat body
               "..vvvvv..",  # hat brim
               "..vPPPv..",  # peach face under hat
               ".vvKvKvv.",  # BLACK eyes!
               "VVVVVVVVy",  # full lavender robe + GOLD baton tip (y)!
               "VVVVVVVwY",  # robe + silver arm + yellow baton shaft
               "VVVyVVVwY",  # gold MEDAL badge + baton arm
               "VVVVVVVwY",  # robe body + arm
               "VVVVVVVVV",  # full robe
               ".VVVVVVV.",  # waist
               ".VVVVVVV.",  # hips
               "..VV.VV..",  # legs
               "..VV.VV..",
               "..VV.VV..",
               "..WW.WW.."),  # shoes
            _s("...vvv..Y",  # baton TIP visible at top right! (Y=yellow)
               "..vvvvvwY",  # arm + baton going UP
               "..vvvvvwY",
               "..vPPPvwY",  # face + baton beside head
               ".vvKvKvwY",  # eyes + baton arm raised HIGH
               "VVVVVVVwY",  # full robe + baton arm straight up
               "VVVVVVVwV",  # arm coming down
               "VVVyVVVVV",  # gold medal
               "VVVVVVVVV",
               "VVVVVVVVV",
               ".VVVVVVV.",
               ".VVVVVVV.",
               "..VV.VV..",
               "..VV.VV..",
               "..VV.VV..",
               "..WW.WW.."),
        ],
        "active_color": P["lavender"],
        "done_color":   P["green"],
    },
    "architect": {
        "label": "ARC",
        "name": "Architect",
        "persona": "wizard",
        "frames": [
            _s("....I....",  # HAT TIP — single-pixel pointy top
               "...III...",  # hat shaft widens immediately
               "..IIIII..",  # hat shaft wider
               ".IIIIIII.",  # hat brim — very wide!
               "..IPPPII.",  # face begins under brim (peach skin)
               "..IKyKII.",  # BLACK eyes + gold twinkle!
               "..IPPPII.",  # chin
               ".IIIIIII.",  # WIDE robe shoulders
               "IIICCCIIy",  # indigo robe + CYAN magic scroll + gold star!
               "IICCCCCIy",  # scroll wider + blazing
               "IIICCCIIy",  # scroll continues
               "..III.III",  # robe splits at sandals
               "..III.III",
               "..WII.WII",  # white sandal straps
               "........."),
            _s("Y...I....",  # GOLD STAR blazing at hat tip — casting spell!
               "...III...",
               "..IIIII..",
               ".IIIIIII.",
               "..IPPPII.",
               "..IKyKIIC",  # CYAN MAGIC erupting from right hand!
               "..IPPPII.",
               ".IIIIIIC.",  # magic trail
               "IICCCCCIy",  # scroll blazing
               "IICCCCCIy",
               "IIICCCIIy",
               "..III.III",
               "..III.III",
               "..WII.WII",
               "........."),
        ],
        "active_color": P["cyan"],
        "done_color":   P["green"],
    },
    "programmer": {
        "label": "PRG",
        "name": "Programmer",
        "persona": "hacker",
        "frames": [
            _s("...GGG...",  # green hoodie hood up
               "..GGGGG..",
               "..GPPPG..",  # face inside hood (peach)
               "..GKyKG..",  # BLACK eyes + gold pixel (glasses)!
               ".GGGGGGG.",  # hoodie body
               ".GGGgGGG.",  # lime kangaroo pocket
               "GGGGGGGGG",  # full-width hoodie arms
               "GGGGGGGGG",
               "DDDDDDDDD",  # LAPTOP LID — solid dark rectangle!
               "DGgGGgGGD",  # screen: green code characters!
               "DgGGgGGgD",  # more code
               "DGGGGGGgD",  # code + cursor
               "DDDDDDDDD",  # keyboard bezel
               "DDDDDDDDD",  # laptop base/trackpad
               "..KK..KK.",  # legs (hoodie person sitting behind laptop)
               "..KK..KK."),  # feet
            _s("...GGG...",
               "..GGGGG..",
               "..GPPPG..",
               "..GKyKG..",
               ".GGGGGGG.",
               ".GGGgGGG.",
               "GGGGGGGGG",
               "GGGGGGGGG",
               "DDDDDDDDD",
               "DgggGgggD",  # fast typing: lots of chars!
               "DGGgGGGgD",
               "DgGGGGGgD",
               "DDDDDDDDD",
               "DDDDDDDDD",
               "..KK..KK.",
               "..KK..KK."),
        ],
        "active_color": P["lime"],
        "done_color":   P["green"],
    },
    "code-reviewer": {
        "label": "CRV",
        "name": "Code Reviewer",
        "persona": "detective",
        "frames": [
            _s("ooooooooo",  # FULL-WIDTH wide-brim hat! (o=brown)
               "ooooooooo",  # double-thick brim — VERY distinctive!
               "...ooo...",  # hat crown
               "...PPP...",  # face
               "..PKKPo..",  # BLACK eyes (K)!
               ".oooPPoo.",  # face wider + coat begins
               ".oooooooo",  # amber trench coat
               ".oooYoooo",  # magnifying glass LENS (Y=yellow)!
               ".ooYYYooo",  # larger lens circle
               ".oooYoooo",  # lens handle bottom
               ".ooooooo.",  # coat lower
               "..oo.oo..",  # legs
               "..oo.oo..",
               "..oo.oo..",
               "..oo.oo..",
               "..WW.WW.."),  # shoes
            _s("ooooooooo",
               "ooooooooo",
               "...ooo...",
               "..oYYoo..",  # looking DOWN into lens!
               "..PYYPP..",  # face pressed to lens
               ".oooYPooo",  # lens in front of face
               ".ooYYYooo",  # wide lens
               ".oooYoooo",
               ".ooooooo.",
               ".ooooooo.",
               "..oo.oo..",
               "..oo.oo..",
               "..oo.oo..",
               "..oo.oo..",
               "..oo.oo..",
               "..WW.WW.."),
        ],
        "active_color": P["orange"],
        "done_color":   P["green"],
    },
    "tester": {
        "label": "TST",
        "name": "Tester",
        "persona": "scientist",
        "frames": [
            _s("...www...",  # white/silver hair
               "..wPPPw..",  # face with silver hair sides
               "..wKyKw..",  # BLACK eyes (K) + gold glasses frames (y)!
               "..wPPPw..",  # chin
               ".wwwwwww.",  # WHITE lab coat shoulders
               ".wwwwwww.",  # lab coat body
               "wwwCCCwww",  # FLASK! Cyan liquid neck (C=cyan)
               "wwwCCCwww",  # flask neck
               "wwCCCCCww",  # flask body WIDER
               "wwCCgCCww",  # LIME BUBBLE in cyan liquid!
               "wwCgCgCww",  # more bubbles!
               ".wwwwwww.",  # coat lower
               "..ww.ww..",  # legs
               "..ww.ww..",
               "..WW.WW..",  # shoes
               "........."),
            _s("...www...",
               "..wPPPw..",
               "..wKyKw..",
               "..wPPPw..",
               ".wwwwwww.",
               ".wwwwwww.",
               "wwwCCCwww",
               "wwwCCCwww",
               "wwCCCCCww",
               "wwCgCgCww",  # vigorous bubbles!
               "wwgCgCgww",  # even MORE bubbles (lime + cyan)!
               ".wwwwwww.",
               "..ww.ww..",
               "..ww.ww..",
               "..WW.WW..",
               "........."),
        ],
        "active_color": P["cyan"],
        "done_color":   P["green"],
    },
    "docs-writer": {
        "label": "DOC",
        "name": "Docs Writer",
        "persona": "scribe",
        "frames": [
            _s("...LLL...",  # cream monk hood top
               "..LLLLL..",  # hood wider
               ".LLWyLLL.",  # WHITE+gold QUILL FEATHER sticking up!
               "..LPPPL..",  # peach face in cream cowl
               ".LLKyKLL.",  # BLACK eyes (K) + gold reading-glass bridge!
               ".LLLLLLL.",  # cream robe
               "LLLbbbLLL",  # OPEN BOOK! Navy pages (b=navy)
               "LLLbybLLL",  # book with gold title line!
               "LLLbbbLLL",  # more pages
               "LLLbbbLLL",  # book bottom
               ".LLLLLLL.",  # robe continues
               "..LL.LL..",  # legs
               "..LL.LL..",
               "..LL.LL..",
               "..LL.LL..",
               "..WW.WW.."),  # sandals
            _s("...LLL...",
               "..LLLLL..",
               ".LLwWLLL.",  # quill MOVING (silver blur = active writing!)
               "..LPPPL..",
               ".LLKyKLL.",
               ".LLLLLLL.",
               "LLLbbbLLL",
               "LLLbBbLLL",  # bright blue = fresh ink line!
               "LLLBBbLLL",  # ink spreading
               "LLLbbbLLL",
               ".LLLLLLL.",
               "..LL.LL..",
               "..LL.LL..",
               "..LL.LL..",
               "..LL.LL..",
               "..WW.WW.."),
        ],
        "active_color": P["blue"],
        "done_color":   P["green"],
    },
    "retrospective": {
        "label": "RET",
        "name": "Retrospective",
        "persona": "oracle",
        "frames": [
            _s("....u....",  # MAGENTA hood tip — single pixel!
               "...uuu...",  # hood widens
               "..uuuuu..",  # hood (3 rows of magenta = very distinctive!)
               "..uPPPu..",  # peach face in magenta cowl
               "..uKyKu..",  # BLACK eyes (K) + gold twinkle!
               ".UUUuUUU.",  # purple robe + magenta star dots
               "UUuUUUuUU",  # full robe with stars scattered
               "UUUuuuUUU",  # stars
               "UUuUUUuUU",  # starry robe
               ".UUUUUUU.",  # robe lower
               "..UCCCCU.",  # CRYSTAL BALL glowing (C=cyan)!
               ".UCCyCCCU",  # ball with gold reflection!
               "..UCCCCU.",  # ball bottom
               "..UUUUU..",  # robe at feet
               ".........",
               "........."),
            _s("....u....",
               "...uuu...",
               "..uuuuu..",
               "..uPPPu..",
               "..uKyKu..",
               ".UUUuUUU.",
               "UUuUUUuUU",
               "UUUuuuUUU",
               "UUuUUUuUU",
               ".UUUUUUU.",
               "..UCCCCU.",
               ".CCCCCCC.",  # BLAZING ball (full cyan = vision active)!
               "..UCCCCU.",
               "..UUUUU..",
               ".........",
               "........."),
        ],
        "active_color": P["pink"],
        "done_color":   P["green"],
    },
}

AGENT_ORDER = [
    "product-owner", "scrum-master", "architect", "programmer",
    "code-reviewer", "tester", "docs-writer", "retrospective",
]


# ── Status colours and icons ───────────────────────────────────────────────────

STATUS_STYLE = {
    "idle":       (P["dim"],    "⬜", "idle"),
    "active":     (P["yellow"], "🔄", "working"),
    "done":       (P["green"],  "✅", "done"),
    "fail":       (P["red"],    "❌", "failed"),
    "blocked":    (P["orange"], "🟠", "blocked"),
    "unknown":    (P["slate"],  "❓", "unknown"),
}


# ── Data loading ───────────────────────────────────────────────────────────────

def load_db_state(db_path: str) -> dict:
    """Load sprint/item/budget state from fleet.db."""
    state: dict = {
        "sprint": None,
        "items": [],
        "agent_status": {a: "idle" for a in AGENT_ORDER},
        "coverage": None,
        "cost_usd": 0.0,
        "items_done": 0,
        "items_total": 0,
    }
    if not os.path.exists(db_path):
        return state
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        sprint = conn.execute(
            "SELECT id, name FROM sprints WHERE status='active' LIMIT 1"
        ).fetchone()
        if sprint:
            state["sprint"] = dict(sprint)
            items = conn.execute("""
                SELECT bi.id, bi.title, si.status, si.architect_done,
                       si.programmer_done, si.tester_done, si.docs_done,
                       si.fix_cycles
                FROM sprint_items si
                JOIN backlog_items bi ON bi.id = si.backlog_item_id
                WHERE si.sprint_id = ?
                ORDER BY si.id
            """, (sprint["id"],)).fetchall()
            state["items"] = [dict(r) for r in items]
            state["items_done"] = sum(1 for r in state["items"] if r["status"] == "done")
            state["items_total"] = len(state["items"])

            cov = conn.execute("""
                SELECT MAX(coverage_pct) as c FROM test_runs
                WHERE passed=1 AND sprint_item_id IN
                  (SELECT id FROM sprint_items WHERE sprint_id=?)
            """, (sprint["id"],)).fetchone()
            if cov and cov["c"]:
                state["coverage"] = cov["c"]

            cost = conn.execute(
                "SELECT COALESCE(SUM(cost_usd),0) as c FROM budget_events WHERE sprint_id=?",
                (sprint["id"],),
            ).fetchone()
            if cost:
                state["cost_usd"] = cost["c"]

            # Infer active agent from item statuses
            for item in state["items"]:
                s = item["status"]
                if s == "designing":
                    state["agent_status"]["architect"] = "active"
                elif s == "implementing":
                    state["agent_status"]["programmer"] = "active"
                elif s == "reviewing":
                    state["agent_status"]["code-reviewer"] = "active"
                elif s == "testing":
                    state["agent_status"]["tester"] = "active"
                elif s == "fixing":
                    state["agent_status"]["programmer"] = "active"
                elif s == "documenting":
                    state["agent_status"]["docs-writer"] = "active"
                elif s == "done":
                    for ag in ["architect", "programmer", "code-reviewer",
                               "tester", "docs-writer"]:
                        if state["agent_status"][ag] == "idle":
                            state["agent_status"][ag] = "done"

        conn.close()
    except Exception:
        pass
    return state


def load_last_events(log_path: str) -> dict[str, dict]:
    """Load the most recent event per agent from agent-log.ndjson."""
    last: dict[str, dict] = {}
    if not os.path.exists(log_path):
        return last
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    agent = ev.get("agent", "")
                    if agent:
                        last[agent] = ev
                except Exception:
                    pass
    except Exception:
        pass
    return last


# ── Sprite panel rendering ─────────────────────────────────────────────────────

SPRITE_W = 9  # chars wide (each char = 1 pixel wide)
SPRITE_H = 8  # lines tall (each line = 2 pixels tall, half-block)

PANEL_INNER_W = SPRITE_W        # 9 — interior of the bordered panel
PANEL_W       = PANEL_INNER_W + 2  # 11 — including ┌ and ┐ border chars

def _rgb_to_ansi256(r: int, g: int, b: int) -> int:
    """Nearest ANSI 256-color index for fallback."""
    ri = round(r / 51)
    gi = round(g / 51)
    bi = round(b / 51)
    return 16 + 36 * min(ri, 5) + 6 * min(gi, 5) + min(bi, 5)


def render_agent_panel(
    agent_id: str,
    status: str,
    frame: int = 0,
    width: int = PANEL_W,  # kept for API compat; internal layout uses PANEL_W
) -> list[str]:
    """Render a bordered, animated agent panel. Returns 13 lines.

    Structure (11 chars wide):
        ┌─────────┐   top border
        │ sprite  │   × 8 sprite lines
        │  LABEL  │   label (blinks when active)
        │   ⬜    │   status icon
        └─────────┘   bottom border
         ░░░░░░░░░    shadow
    """
    spec = SPRITES[agent_id]

    # ── Dim / tint factors by status ─────────────────────────────────────────
    if status == "active":
        pf         = _pulse_factor(frame)
        tint       = _scale_rgb(spec["active_color"], pf)
        dim_factor = pf                   # 0.85 → 1.00
    elif status == "done":
        tint, dim_factor = None, 0.75
    elif status in ("fail", "blocked"):
        tint, dim_factor = None, 0.65
    else:                                 # idle / unknown — strongly dimmed
        tint, dim_factor = None, 0.28

    sprite_frame = spec["frames"][frame % len(spec["frames"])]
    sprite_lines = render_sprite(sprite_frame, tint=tint, dim_factor=dim_factor)

    sty, icon, _ = STATUS_STYLE.get(status, STATUS_STYLE["unknown"])

    # ── Border colour ─────────────────────────────────────────────────────────
    if status == "active":
        b_rgb = _scale_rgb(spec["active_color"], _pulse_factor(frame))
        b_col = fg(*b_rgb)
    elif status == "done":
        b_col = fg(*P["green"])
    elif status == "fail":
        b_col = fg(*P["red"])
    elif status == "blocked":
        b_col = fg(*P["orange"])
    else:
        b_col = fg(*_scale_rgb(P["slate"], 0.38))

    inner = PANEL_INNER_W  # 9

    # ── Label (blinks for active on every 4th frame) ──────────────────────────
    label_str = spec["label"]
    lpad   = (inner - len(label_str)) // 2
    lpad_r = inner - len(label_str) - lpad
    if status == "active" and (frame // 4) % 2 == 0:
        label_out = BOLD + fg(*sty) + label_str + RESET
    else:
        label_out = fg(*sty) + label_str + RESET

    panel: list[str] = []

    # Top border
    panel.append(b_col + "┌" + "─" * inner + "┐" + RESET)

    # Sprite rows
    for sl in sprite_lines:
        panel.append(b_col + "│" + RESET + sl + b_col + "│" + RESET)

    # Label row
    panel.append(
        b_col + "│" + RESET
        + " " * lpad + label_out + " " * lpad_r
        + b_col + "│" + RESET
    )

    # Icon row (emoji = 2 terminal cols → string offset by 1)
    icon_lpad = (inner - 2) // 2   # 3
    icon_rpad = inner - 2 - icon_lpad  # 4
    panel.append(
        b_col + "│" + RESET
        + " " * icon_lpad + icon + " " * icon_rpad
        + b_col + "│" + RESET
    )

    # Bottom border
    panel.append(b_col + "└" + "─" * inner + "┘" + RESET)

    # Shadow (dim ░ row below the panel, shifted 1 right for depth)
    shad = fg(*_scale_rgb(P["mid"], 0.35))
    panel.append(" " + shad + "░" * inner + " " + RESET)

    return panel


def hstack(panels: list[list[str]], sep: str = " ") -> list[str]:
    """Horizontally stack equal-height panels."""
    height = max(len(p) for p in panels)
    # Pad panels to same height
    padded = []
    for p in panels:
        while len(p) < height:
            p = p + [""]
        padded.append(p)
    result = []
    for row in range(height):
        result.append(sep.join(p[row] for p in padded))
    return result


def strip_ansi(s: str) -> int:
    """Approximate visible width (ignores ANSI sequences, not emoji-aware)."""
    import re
    return len(re.sub(r"\033\[[^m]*m", "", s))


def vis_width(s: str) -> int:
    """True terminal visual width: strips ANSI and counts wide (2-col) chars correctly."""
    import re
    clean = re.sub(r"\033\[[^m]*m", "", s)
    return sum(
        2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
        for c in clean
    )


def _render_agent_row(
    agent_ids: list[str],
    agent_status: dict[str, str],
    frame: int,
    arrow: str,
) -> tuple[list[str], int]:
    """Return (stacked_rows, total_visible_width) for one row of agents."""
    panels = [
        render_agent_panel(ag, agent_status.get(ag, "idle"), frame=frame)
        for ag in agent_ids
    ]
    n = len(agent_ids)
    all_panels: list[list[str]] = []
    for i, p in enumerate(panels):
        all_panels.append(p)
        if i < n - 1:
            h = len(p)
            arr = [" "] * h
            arr[h // 2 - 2] = arrow   # place at sprite body-centre
            all_panels.append(arr)
    stacked = hstack(all_panels, sep="")
    total_w = n * PANEL_W + (n - 1) * 1   # emoji-safe: hardcoded from known widths
    return stacked, total_w


# ── Main dashboard ─────────────────────────────────────────────────────────────

HEADER = "  🚀  FLEET — Agent Mission Control"

def render_dashboard(
    state: dict,
    events: dict[str, dict],
    frame: int = 0,
    term_width: int = 120,
    focus_agent: str | None = None,
) -> str:
    """Return the full dashboard as a single string."""
    lines: list[str] = []
    W  = min(term_width, 120)
    BL = fg(*P["blue"])   # border colour shorthand

    def _rbox(content: str, vis_override: int | None = None) -> str:
        """║ + content + right-pad to fill W columns + ║."""
        v    = vis_override if vis_override is not None else vis_width(content)
        rpad = max(0, W - 2 - v)
        return BL + "║" + RESET + content + " " * rpad + BL + "║" + RESET

    # Animated arrow glyph (cycles every frame)
    arrow_glyph = ARROW_GLYPHS[frame % len(ARROW_GLYPHS)]
    arrow_pulse  = _pulse_factor(frame)
    arrow        = fg(*_scale_rgb(P["silver"], arrow_pulse)) + arrow_glyph + RESET

    # Grid vs single-row layout.
    # Single row needs 8×11 + 7 = 95 visible chars + 2 box borders = 97 min.
    # If terminal is narrower than 100 → 2×4 grid (47 visible + 2 borders = 49).
    use_grid = (W < 100)

    # ─ Header ─────────────────────────────────────────────────────────────────
    sprint_label  = state["sprint"]["name"] if state["sprint"] else "No active sprint"
    header_vis    = vis_width(HEADER)          # accounts for 🚀 being 2-col wide
    gap = W - 2 - header_vis - len(sprint_label)
    lines.append(BL + "╔" + "═" * (W - 2) + "╗" + RESET)
    lines.append(
        BL + "║" + RESET
        + BOLD + fg(*P["yellow"]) + HEADER + RESET
        + " " * max(gap, 1)
        + fg(*P["lavender"]) + sprint_label + RESET
        + BL + "║" + RESET
    )
    lines.append(BL + "╠" + "═" * (W - 2) + "╣" + RESET)

    # ─ Focus mode (single agent zoomed 2×) ───────────────────────────────────
    if focus_agent and focus_agent in SPRITES:
        spec   = SPRITES[focus_agent]
        status = state["agent_status"].get(focus_agent, "idle")
        pf     = _pulse_factor(frame) if status == "active" else 1.0
        dim    = pf if status == "active" else (0.75 if status == "done" else 0.28)
        tint   = _scale_rgb(spec["active_color"], pf) if status == "active" else None
        sty, icon, status_word = STATUS_STYLE.get(status, STATUS_STYLE["unknown"])

        grid   = spec["frames"][frame % len(spec["frames"])]
        sprite_lines = render_sprite(grid, tint=tint, dim_factor=dim)

        # 2× horizontal scale: each half-block char → doubled
        import re as _re
        for sl in sprite_lines:
            doubled = _re.sub(r"(▀|▄|█| )", r"\1\1", sl)
            # 2 indent + SPRITE_W*2 visible chars
            lines.append(_rbox("  " + doubled, vis_override=2 + SPRITE_W * 2))

        sty_col  = fg(*sty) if sty else ""
        hint     = f"(press f to exit focus, n for next)"
        lbl_line = (
            f"  {BOLD}{sty_col}{spec['name'].upper()}{RESET}"
            f"  {icon} {status_word}  {DIM}{hint}{RESET}"
        )
        lines.append(_rbox(lbl_line))
        lines.append(BL + "╚" + "═" * (W - 2) + "╝" + RESET)
        return "\n".join(lines)

    # ─ Agent panels ───────────────────────────────────────────────────────────
    agent_status = state["agent_status"]

    def _emit_row(agent_ids: list[str]) -> None:
        stacked, total_w = _render_agent_row(agent_ids, agent_status, frame, arrow)
        pad = max(0, (W - 2 - total_w) // 2)
        for sl in stacked:
            rpad = max(0, W - 2 - pad - vis_width(sl))
            lines.append(
                BL + "║" + RESET
                + " " * pad + sl + " " * rpad
                + BL + "║" + RESET
            )

    if use_grid:
        _emit_row(AGENT_ORDER[:4])
        lines.append(BL + "╟" + "─" * (W - 2) + "╢" + RESET)
        _emit_row(AGENT_ORDER[4:])
    else:
        _emit_row(AGENT_ORDER)

    # ─ Sparkline strip ────────────────────────────────────────────────────────
    # One sparkline bar per agent, 9 chars each, same grouping as panel rows
    lines.append(BL + "╟" + "─" * (W - 2) + "╢" + RESET)

    def _spark_row(agent_ids: list[str]) -> str:
        # Each "slot" = PANEL_W chars wide, separated by 1-char gaps.
        # Content per slot: 1 space + 3-char label (colored) + 1 space + 6-char sparkline
        # = 11 chars = PANEL_W ✓
        total_w = len(agent_ids) * PANEL_W + (len(agent_ids) - 1) * 1
        pad     = max(0, (W - 2 - total_w) // 2)
        rpad    = max(0, W - 2 - pad - total_w)
        parts   = []
        for ag in agent_ids:
            lbl = SPRITES[ag]["label"]
            st  = agent_status.get(ag, "idle")
            lc  = fg(*_SPARK_COLS.get(st, _SPARK_COLS["idle"]))
            bar = _render_sparkline(ag, bar_w=6)   # 6 history chars
            # " " + label(3) + " " + sparkline(6) = 11 = PANEL_W
            lbl3 = lbl.ljust(3)[:3]   # ensure exactly 3 chars to match PANEL_W
            parts.append(" " + lc + lbl3 + RESET + " " + bar)
        content = " " * pad + " ".join(parts) + " " * rpad
        return BL + "║" + RESET + content + BL + "║" + RESET

    if use_grid:
        lines.append(_spark_row(AGENT_ORDER[:4]))
        lines.append(_spark_row(AGENT_ORDER[4:]))
    else:
        lines.append(_spark_row(AGENT_ORDER))

    # ─ Separator ─────────────────────────────────────────────────────────────
    lines.append(BL + "╠" + "═" * (W - 2) + "╣" + RESET)

    # ─ Current event line ────────────────────────────────────────────────────
    active_events = [
        (ag, ev) for ag, ev in events.items()
        if ev.get("outcome") in (None, "pass", "fail")
    ]
    if active_events:
        ag, ev  = sorted(active_events, key=lambda x: x[1].get("ts", ""))[-1]
        action  = ev.get("action", "?")
        item_id = ev.get("item_id", "-")
        outcome = ev.get("outcome", "?")
        oc      = (fg(*P["green"]) if outcome == "pass"
                   else fg(*P["red"]) if outcome == "fail"
                   else fg(*P["yellow"]))
        ev_line = (
            f"  Latest: {fg(*P['cyan'])}{ag}{RESET} › "
            f"{fg(*P['lavender'])}{item_id}{RESET} › "
            f"{action} {oc}{outcome}{RESET}"
        )
    else:
        ev_line = f"  {DIM}No agent events yet — run a sprint to begin{RESET}"

    lines.append(_rbox(ev_line))

    # ─ Stats line ────────────────────────────────────────────────────────────
    done  = state["items_done"]
    total = state["items_total"]
    cov   = f"{state['coverage']:.1f}%" if state["coverage"] else "—"
    cost  = f"${state['cost_usd']:.2f}"

    if total:
        bar       = _gradient_bar(done, total, width=18)
        stats_line = (
            f"  Items: {fg(*P['yellow'])}{done}/{total}{RESET}  "
            f"{bar}  "
            f"Coverage: {fg(*P['cyan'])}{cov}{RESET}  "
            f"Cost: {fg(*P['peach'])}{cost}{RESET}"
        )
    else:
        stats_line = f"  {DIM}No sprint active. Initialize: bash scripts/init-state.sh{RESET}"

    lines.append(_rbox(stats_line))

    # ─ Help line ─────────────────────────────────────────────────────────────
    help_line = (
        f"  {DIM}--watch  live view  │  --replay  animate  │"
        f"  f  focus agent  │  q  quit{RESET}"
    )
    lines.append(_rbox(help_line))

    lines.append(BL + "╚" + "═" * (W - 2) + "╝" + RESET)

    return "\n".join(lines)


# ── Replay mode ────────────────────────────────────────────────────────────────

def replay_mode(log_path: str, term_width: int) -> None:
    """Animate through agent-log.ndjson event by event."""
    if not os.path.exists(log_path):
        print(f"⚠️  No event log at {log_path}")
        return

    with open(log_path) as f:
        raw = [json.loads(l) for l in f if l.strip()]

    if not raw:
        print("No events in log.")
        return

    fake_state: dict = {
        "sprint": {"name": "Replay"},
        "items": [],
        "agent_status": {a: "idle" for a in AGENT_ORDER},
        "coverage": None,
        "cost_usd": 0.0,
        "items_done": 0,
        "items_total": 0,
    }
    events: dict[str, dict] = {}

    print(HIDE_CURSOR)
    try:
        first = True
        anim_frame = 0
        for ev in raw:
            agent = ev.get("agent", "")
            if agent in AGENT_ORDER:
                outcome = ev.get("outcome", "")
                if outcome == "pass":
                    fake_state["agent_status"][agent] = "done"
                elif outcome == "fail":
                    fake_state["agent_status"][agent] = "fail"
                else:
                    fake_state["agent_status"][agent] = "active"
            events[agent] = ev
            _update_spark(fake_state["agent_status"])

            # Animate a few frames per event for motion
            for sub in range(4):
                dashboard = render_dashboard(
                    fake_state, events,
                    frame=anim_frame, term_width=term_width,
                )
                n_lines = dashboard.count("\n") + 1
                if not first:
                    sys.stdout.write(f"\033[{n_lines}A")
                sys.stdout.write(dashboard + "\n")
                sys.stdout.flush()
                first = False
                anim_frame += 1
                time.sleep(0.15)
    finally:
        print(SHOW_CURSOR)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    args   = sys.argv[1:]
    watch  = "--watch"  in args
    replay = "--replay" in args

    pos_args  = [a for a in args if not a.startswith("--")]
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    term_w, _ = shutil.get_terminal_size(fallback=(80, 24))

    # Graceful degradation
    if term_w < 60:
        return
    if not sys.stdout.isatty() and not watch and not replay:
        return

    if replay:
        log_path = pos_args[0] if pos_args else os.path.join(repo_root, "state", "agent-log.ndjson")
        replay_mode(log_path, term_w)
        return

    db_path  = pos_args[0] if pos_args else os.path.join(repo_root, "state", "fleet.db")
    log_path = os.path.join(os.path.dirname(db_path), "agent-log.ndjson")

    # Focus mode state
    focus_idx: int | None = None  # None = no focus; 0..7 = which agent

    frame           = 0
    dashboard_lines = 0
    state: dict     = {}
    events: dict    = {}

    print(HIDE_CURSOR)
    try:
        while True:
            # Reload DB every 4 frames (~2 s at 0.5 s/frame)
            if frame % 4 == 0 or not state:
                state  = load_db_state(db_path)
                events = load_last_events(log_path)

            _update_spark(state["agent_status"])

            # Terminal bell on completion / failure
            if _check_bells(state["agent_status"]):
                sys.stdout.write("\a")

            focus_agent = AGENT_ORDER[focus_idx] if focus_idx is not None else None
            dashboard   = render_dashboard(
                state, events,
                frame=frame,
                term_width=term_w,
                focus_agent=focus_agent,
            )
            n_lines = dashboard.count("\n") + 1

            if dashboard_lines:
                sys.stdout.write(f"\033[{dashboard_lines}A")
            sys.stdout.write(dashboard + "\n")
            sys.stdout.flush()
            dashboard_lines = n_lines
            frame += 1

            if not watch:
                break

            # Non-blocking keypress (0.5 s animation tick)
            time.sleep(0.5)
            key = _getch_nonblock()
            if key in ("q", "Q", "\x03"):
                break
            elif key in ("f", "F"):
                # Cycle focus to next agent (or exit focus if wrapping)
                if focus_idx is None:
                    focus_idx = 0
                else:
                    focus_idx = (focus_idx + 1) % len(AGENT_ORDER)
            elif key in ("n", "N"):
                if focus_idx is not None:
                    focus_idx = (focus_idx + 1) % len(AGENT_ORDER)
            elif key == "\x1b":
                focus_idx = None  # Escape clears focus

    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
