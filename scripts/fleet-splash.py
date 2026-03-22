#!/usr/bin/env python3
"""
fleet-splash.py — Animated Intro Banner for Fleet Framework
============================================================
Displays a pixelated splash screen when fleet is initialized.
Pure Python 3 stdlib — zero pip dependencies.
Skipped automatically in non-interactive terminals.
Skip with: Ctrl+C or any key (non-blocking).
"""
from __future__ import annotations

import os
import shutil
import sys
import time

# Re-use the ANSI helpers and sprites from fleet-viz.py by relative import
# If running standalone, define minimal ANSI helpers inline.

RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

def fg(r: int, g: int, b: int) -> str:
    return f"\033[38;2;{r};{g};{b}m"

def bg(r: int, g: int, b: int) -> str:
    return f"\033[48;2;{r};{g};{b}m"


# PICO-8 palette subset
P = {
    "black":  (0,   0,   0  ),
    "navy":   (29,  43,  83 ),
    "blue":   (41,  173, 255),
    "cyan":   (0,   228, 228),
    "green":  (0,   228, 54 ),
    "yellow": (255, 236, 39 ),
    "orange": (255, 163, 0  ),
    "red":    (255, 0,   77 ),
    "purple": (110, 0,   160),
    "pink":   (255, 119, 168),
    "white":  (255, 241, 232),
    "silver": (194, 195, 199),
    "slate":  (95,  87,  79 ),
    "dim":    (60,  60,  80 ),
    "gold":   (255, 200, 0  ),
    "lavender": (131, 118, 156),
    "_":      None,
}

_TBG = (15, 15, 25)


def render_sprite(grid: list[list[str]]) -> list[str]:
    lines = []
    h = len(grid)
    w = len(grid[0]) if grid else 0
    for row_idx in range(0, h, 2):
        line = ""
        top_row = grid[row_idx]
        bot_row = grid[row_idx + 1] if row_idx + 1 < h else ["_"] * w
        for col in range(w):
            tc = P.get(top_row[col])
            bc = P.get(bot_row[col])
            if tc is None and bc is None:
                line += " "
            elif tc is None:
                line += bg(*bc) + fg(*_TBG) + "▄" + RESET
            elif bc is None:
                line += fg(*tc) + bg(*_TBG) + "▀" + RESET
            else:
                line += fg(*tc) + bg(*bc) + "▀" + RESET
        lines.append(line)
    return lines


# ── Fleet logo (22 wide × 6 tall pixel art) ───────────────────────────────────
# Spells "FLEET" in chunky pixel letters with a cyan/blue gradient

LOGO_ROWS = [
    "cyan", "blue", "navy",  # top → bottom gradient
]

# Block letter grid (22 chars wide × 6 rows, 0=off 1=on)
LOGO_PIXELS = [
    "111.1..1..11111.1..11111",  # F  L  E  E  T
    "1...1..1..1....1..1..1..",
    "111.1..1..111..1..1..1..",
    "1...1..1..1....1..1..1..",
    "1...1..1..1....1..1..1..",
    "1...11111.11111.11111.1..",
]


def render_logo(width: int = 24) -> list[str]:
    """Render the FLEET pixel-art logo as ANSI half-block lines."""
    # Gradient colours per pixel row
    grad = [P["cyan"], P["blue"], P["blue"], P["navy"], P["navy"], P["navy"]]
    lines = []
    pixel_rows = LOGO_PIXELS
    h = len(pixel_rows)
    for row_idx in range(0, h, 2):
        line = ""
        top_row_str = pixel_rows[row_idx]
        bot_row_str = pixel_rows[row_idx + 1] if row_idx + 1 < h else "0" * width
        tc_on = grad[row_idx]
        bc_on = grad[row_idx + 1] if row_idx + 1 < h else P["navy"]
        for col in range(min(len(top_row_str), len(bot_row_str))):
            ton = top_row_str[col] == "1"
            bon = bot_row_str[col] == "1"
            if ton and bon:
                line += fg(*tc_on) + bg(*bc_on) + "▀" + RESET
            elif ton:
                line += fg(*tc_on) + bg(*_TBG) + "▀" + RESET
            elif bon:
                line += fg(*_TBG) + bg(*bc_on) + " " + RESET
            else:
                line += " "
        lines.append(line)
    return lines


# ── Agent mini parade (condensed 3×4 sprites for the parade) ──────────────────

MINI_AGENTS = [
    ("PO",  [["navy","gold","navy"],["gold","peach","gold"],["navy","navy","navy"],["_","navy","_"]],  P["gold"]),
    ("SM",  [["lavender","lavender","lavender"],["lavender","peach","lavender"],["purple","purple","purple"],["_","purple","_"]], P["lavender"]),
    ("ARC", [["_","indigo","_"],["indigo","peach","indigo"],["indigo","indigo","indigo"],["_","navy","_"]], P["cyan"]),
    ("PRG", [["green","green","green"],["green","peach","green"],["dim","green","dim"],["dim","dim","dim"]], P["green"]),
    ("CRV", [["brown","brown","brown"],["brown","peach","white"],["brown","brown","brown"],["_","brown","_"]], P["orange"]),
    ("TST", [["silver","silver","silver"],["silver","peach","silver"],["teal","cyan","teal"],["_","silver","_"]], P["cyan"]),
    ("DOC", [["cream","cream","cream"],["cream","peach","white"],["cream","blue","cream"],["_","cream","_"]], P["blue"]),
    ("RET", [["magenta","magenta","magenta"],["magenta","peach","magenta"],["purple","cyan","purple"],["_","purple","_"]], P["pink"]),
]

# Add missing palette entries used by mini agents
P["brown"] = (171, 82, 54)
P["peach"] = (255, 204, 170)
P["teal"]  = (0, 171, 171)
P["cream"] = (240, 230, 180)
P["indigo"]= (63, 63, 176)
P["magenta"]=(180, 0, 180)


def render_mini_sprite(rows: list[list[str]]) -> list[str]:
    h = len(rows)
    w = len(rows[0]) if rows else 3
    lines = []
    for row_idx in range(0, h, 2):
        line = ""
        top_row = rows[row_idx]
        bot_row = rows[row_idx + 1] if row_idx + 1 < h else ["_"] * w
        for col in range(w):
            tc = P.get(top_row[col])
            bc = P.get(bot_row[col])
            if tc is None and bc is None:
                line += " "
            elif tc is None:
                line += bg(*bc) + fg(*_TBG) + "▄" + RESET
            elif bc is None:
                line += fg(*tc) + bg(*_TBG) + "▀" + RESET
            else:
                line += fg(*tc) + bg(*bc) + "▀" + RESET
        lines.append(line)
    return lines


# ── Typewriter effect ──────────────────────────────────────────────────────────

def typewrite(text: str, delay: float = 0.03) -> None:
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")
    sys.stdout.flush()


def clear_lines(n: int) -> None:
    for _ in range(n):
        sys.stdout.write("\033[A\033[2K")
    sys.stdout.flush()


# ── Main splash sequence ───────────────────────────────────────────────────────

def run_splash(term_w: int) -> None:
    centre = lambda s, w=term_w: " " * max(0, (w - visible_len(s)) // 2) + s

    import re
    def visible_len(s: str) -> int:
        return len(re.sub(r"\033\[[^m]*m", "", s))

    sys.stdout.write(HIDE_CURSOR)

    # ── Frame 1: Logo materialises ──
    logo_lines = render_logo()
    print()
    for line in logo_lines:
        print(centre(line))
    time.sleep(0.3)

    tagline = (
        fg(*P["silver"]) + "Semi-Autonomous Multi-Agent Development Framework" + RESET
    )
    print(centre(tagline))
    time.sleep(0.4)

    separator = fg(*P["navy"]) + "─" * 56 + RESET
    print(centre(separator))
    time.sleep(0.2)

    # ── Frame 2: Agent parade slides in ──
    print()
    parade_label = fg(*P["lavender"]) + BOLD + "  Agents boarding:" + RESET
    print(parade_label)
    print()

    parade_line_count = 3  # label + blank + sprite lines (2 each) + name

    for label, pixel_rows, color in MINI_AGENTS:
        sprite_lines = render_mini_sprite(pixel_rows)
        # Print sprite sliding in from left
        name_str = fg(*color) + BOLD + label + RESET
        print("  " + "  ".join(sprite_lines))
        print("   " + name_str)
        time.sleep(0.15)

    time.sleep(0.2)

    # ── Frame 3: Ready message ──
    print()
    print(centre(fg(*P["yellow"]) + BOLD + "✨  Fleet is ready for launch!" + RESET))
    print()
    print(centre(
        fg(*P["dim"]) + "Run: " + RESET +
        fg(*P["green"]) + "bash scripts/fleet-status.sh" + RESET +
        fg(*P["dim"]) + "  │  " + RESET +
        fg(*P["cyan"]) + "python3 scripts/fleet-viz.py --watch" + RESET
    ))
    print()
    time.sleep(0.5)


def main() -> None:
    # Skip in non-interactive terminals
    if not sys.stdout.isatty():
        return

    term_w, _ = shutil.get_terminal_size(fallback=(80, 24))
    if term_w < 60:
        return

    try:
        run_splash(term_w)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
