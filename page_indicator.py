"""Page indicator drawing for Conference Badge app."""

import math


def draw_page_indicator(ctx, num_pages, current_page, progress,
                        fg_color=None, bg_color=None):
    """Draw semi-circular progress indicator at bottom of display.

    Draws background color first, then overlays foreground for progress.

    Args:
        ctx: Drawing context
        num_pages: Total number of pages
        current_page: Current page index (0-based)
        progress: Progress within current page (0.0 to 1.0)
        fg_color: RGB tuple (floats) for foreground/complete (default: light grey)
        bg_color: RGB tuple (floats) for background/incomplete (default: dark grey)
    """
    if num_pages < 1:
        return

    # Arc parameters
    arc_radius = 119  # 1px from display edge
    line_width = 2
    gap_angle = math.pi / 45  # ~4 degrees gap between segments

    # Default colors: light grey foreground, dark grey background
    color_fg = fg_color if fg_color else (0.827, 0.827, 0.827)  # lightgray
    color_bg = bg_color if bg_color else (0.663, 0.663, 0.663)  # darkgray

    # Arc spans from just under 9 o'clock to just under 3 o'clock (through bottom)
    # In screen coords (y-down): 180° = 9 o'clock, 90° = 6 o'clock (bottom), 0° = 3 o'clock
    start_angle = 170 * math.pi / 180  # just under 9 o'clock (toward bottom)
    end_angle = 10 * math.pi / 180     # just under 3 o'clock (toward bottom)
    total_arc = start_angle - end_angle  # ~160 degrees through bottom (clockwise)

    # Calculate segment size
    total_gaps = gap_angle * (num_pages - 1) if num_pages > 1 else 0
    segment_arc = (total_arc - total_gaps) / num_pages

    points_per_segment = 50
    ctx.line_width = line_width

    # First pass: draw all segments in background color
    for i in range(num_pages):
        seg_start = start_angle - i * (segment_arc + gap_angle)
        _draw_arc_segment(ctx, seg_start, segment_arc, arc_radius, color_bg)

    # Second pass: overlay foreground color for completed portions
    for i in range(num_pages):
        seg_start = start_angle - i * (segment_arc + gap_angle)

        if i < current_page:
            # Fully complete - draw entire segment in foreground
            _draw_arc_segment(ctx, seg_start, segment_arc, arc_radius, color_fg)
        elif i == current_page:
            # Partially complete - draw progress portion in foreground
            if progress > 0:
                fill_arc = segment_arc * progress
                _draw_arc_segment(ctx, seg_start, fill_arc, arc_radius, color_fg)


def _draw_arc_segment(ctx, start_angle, arc_length, radius, color):
    """Draw a single arc segment."""
    points = 50
    ctx.rgb(*color)

    prev_x, prev_y = None, None
    for p in range(points + 1):
        t = p / points
        angle = start_angle - t * arc_length
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)

        if prev_x is not None:
            ctx.move_to(prev_x, prev_y)
            ctx.line_to(x, y)
            ctx.stroke()

        prev_x, prev_y = x, y
