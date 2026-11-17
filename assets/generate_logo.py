"""
Generate the cp_parallel logo: SVG assembled from simple polygons (no drawing
tools involved). The motif is three "cells" (flat-top hexagons, a nod to
honeycomb/cell-mosaic imagery) each running down its own parallel track --
CellProfiler processing several plates/wells at once. "CP" is set directly
into the top track's line (on the left) and "Parallel" into the bottom
track's line (toward the right), each wordmark using the same teal -> cyan ->
blue gradient as the tracks themselves.

Run with: python assets/generate_logo.py
Writes: assets/logo.svg
"""

import math
import pathlib

LANE_COLORS = ["#0d9488", "#0891b2", "#2563eb"]  # teal -> cyan -> blue
WIDTH, HEIGHT = 480, 200
LANE_Y = [50, 100, 150]
CELL_X = 70
CELL_RADIUS = 26
NUCLEUS_RADIUS = 9
ORGANELLE_RADIUS = 2.6
TRACK_START_X = CELL_X + CELL_RADIUS + 14
TRACK_END_X = WIDTH - 60
TICK_SIZE = 7
ARROW_LENGTH = 20
ARROW_WIDTH = 14

FONT_STACK = "'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
LABEL_FONT_SIZE = 40
LABEL_GAP = 10  # horizontal gap left between a wordmark and the line resuming
ARROW_LABEL_GAP = 4  # tighter gap specifically between a wordmark and an arrowhead
# Actual rendered widths (in px, via SVGTextElement.getBBox() in a real
# browser) of each wordmark at MEASURED_FONT_SIZE, with this exact font stack,
# weight, and letter-spacing. A generic per-character average turned out to
# overestimate "Parallel" by ~40%, leaving a large unwanted gap before it --
# real measurements avoid that, and scale cleanly if LABEL_FONT_SIZE changes.
MEASURED_FONT_SIZE = 40
MEASURED_TEXT_WIDTH = {"CP": 57.58, "Parallel": 150.33}


def hexagon_points(cx: float, cy: float, r: float) -> str:
    """Flat-top regular hexagon vertices, as an SVG `points` string."""
    angles = [math.radians(angle) for angle in (0, 60, 120, 180, 240, 300)]
    points = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in angles]
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def organelle_positions(cx: float, cy: float, r: float) -> list:
    """A few small dots scattered between the nucleus and the cell membrane."""
    offsets = [(-0.55, -0.35), (0.5, -0.4), (0.15, 0.55)]
    return [(cx + dx * r, cy + dy * r) for dx, dy in offsets]


def arrowhead_points(tip_x: float, tip_y: float) -> str:
    back_x = tip_x - ARROW_LENGTH
    points = [
        (tip_x, tip_y),
        (back_x, tip_y - ARROW_WIDTH / 2),
        (back_x, tip_y + ARROW_WIDTH / 2),
    ]
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def text_width(text: str) -> float:
    return MEASURED_TEXT_WIDTH[text] * (LABEL_FONT_SIZE / MEASURED_FONT_SIZE)


def build_cell(cx: float, cy: float, color: str) -> str:
    cell = hexagon_points(cx, cy, CELL_RADIUS)
    organelles = "\n        ".join(
        f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{ORGANELLE_RADIUS}" '
        f'fill="{color}" opacity="0.55" />'
        for x, y in organelle_positions(cx, cy, CELL_RADIUS)
    )
    return f"""<polygon points="{cell}" fill="{color}" fill-opacity="0.16"
                 stroke="{color}" stroke-width="3" stroke-linejoin="round" />
        {organelles}
        <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{NUCLEUS_RADIUS}" fill="{color}" opacity="0.9" />"""


def build_track(cy: float, color: str, x_start: float, x_end: float) -> str:
    """A track segment with evenly-spaced tick marks (no label on it)."""
    span = x_end - x_start
    if span <= 1:
        return ""
    # Short stub segments (e.g. the gap between a wordmark and the arrowhead)
    # are too small for tick marks to read cleanly, so skip them there.
    ticks = (
        "\n        ".join(
            f'<rect x="{x_start + span * frac - TICK_SIZE / 2:.2f}" '
            f'y="{cy - TICK_SIZE / 2:.2f}" width="{TICK_SIZE}" height="{TICK_SIZE}" '
            f'fill="{color}" opacity="0.9" />'
            for frac in (0.35, 0.7)
        )
        if span >= 40
        else ""
    )
    return f"""<line x1="{x_start:.2f}" y1="{cy}" x2="{x_end:.2f}" y2="{cy}"
              stroke="{color}" stroke-width="3" stroke-linecap="round" opacity="0.85" />
        {ticks}"""


def build_label(text: str, anchor: str, x: float, cy: float) -> str:
    """A wordmark sitting right on its track, vertically centered on the line."""
    baseline = cy + LABEL_FONT_SIZE * 0.32
    return (
        f'<text x="{x:.2f}" y="{baseline:.2f}" text-anchor="{anchor}" '
        f'font-family="{FONT_STACK}" font-size="{LABEL_FONT_SIZE}" '
        f'font-weight="700" letter-spacing="1" fill="url(#wordmark)">{text}</text>'
    )


def build_labeled_lane(cy: float, color: str, label: str, label_side: str) -> str:
    """A lane whose wordmark sits snug against the element on its side -- the
    hexagon for a left-side label (e.g. "CP"), the arrowhead for a right-side
    label (e.g. "Parallel") -- with the same small gap used in both cases, so
    neither label reads as detached from the icon it's next to."""
    label_w = text_width(label)

    if label_side == "left":
        label_x_start = TRACK_START_X
        label_x_end = TRACK_START_X + label_w
        line = build_track(
            cy, color, label_x_end + LABEL_GAP, TRACK_END_X - ARROW_LENGTH
        )
        label_el = build_label(label, "start", label_x_start, cy)
    else:
        label_x_end = TRACK_END_X - ARROW_LENGTH - ARROW_LABEL_GAP
        label_x_start = label_x_end - label_w
        line = build_track(cy, color, TRACK_START_X, label_x_start - LABEL_GAP)
        label_el = build_label(label, "end", label_x_end, cy)

    return f"""
    <g>
        {line}
        <polygon points="{arrowhead_points(TRACK_END_X, cy)}" fill="{color}" />
        {build_cell(CELL_X, cy, color)}
        {label_el}
    </g>"""


def build_plain_lane(cy: float, color: str) -> str:
    return f"""
    <g>
        {build_track(cy, color, TRACK_START_X, TRACK_END_X - ARROW_LENGTH)}
        <polygon points="{arrowhead_points(TRACK_END_X, cy)}" fill="{color}" />
        {build_cell(CELL_X, cy, color)}
    </g>"""


def build_svg() -> str:
    top_lane = build_labeled_lane(LANE_Y[0], LANE_COLORS[0], "CP", "left")
    middle_lane = build_plain_lane(LANE_Y[1], LANE_COLORS[1])
    bottom_lane = build_labeled_lane(LANE_Y[2], LANE_COLORS[2], "Parallel", "right")

    return f"""<svg width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}"
     xmlns="http://www.w3.org/2000/svg"
     role="img" aria-label="cp_parallel logo: three cells running down parallel tracks, with CP set into the top track and Parallel set into the bottom track">
    <title>cp_parallel</title>
    <defs>
        <linearGradient id="wordmark" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="{LANE_COLORS[0]}" />
            <stop offset="50%" stop-color="{LANE_COLORS[1]}" />
            <stop offset="100%" stop-color="{LANE_COLORS[2]}" />
        </linearGradient>
    </defs>
{top_lane}
{middle_lane}
{bottom_lane}
</svg>
"""


if __name__ == "__main__":
    svg = build_svg()
    out_path = pathlib.Path(__file__).parent / "logo.svg"
    out_path.write_text(svg)
    print(f"Wrote {out_path} ({WIDTH}x{HEIGHT})")
