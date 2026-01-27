"""Page indicator drawing for Conference Badge app."""

import math


def draw_page_indicator(ctx, num_pages, current_page, progress,
                        ind_inc_color=None, ind_com_color=None):
    """Draw semi-circular progress indicator at bottom of display.

    Args:
        ctx: Drawing context
        num_pages: Total number of pages
        current_page: Current page index (0-based)
        progress: Progress within current page (0.0 to 1.0)
        ind_inc_color: RGB tuple for incomplete segments (default: blue)
        ind_com_color: RGB tuple for complete segments (default: white)
    """
    if num_pages < 1:
        return

    # Arc parameters
    arc_radius = 119  # 1px from display edge
    line_width = 2
    gap_angle = math.pi / 45  # ~4 degrees gap between segments

    # Default colors if not provided (blue/white works on black background)
    color_incomplete = ind_inc_color if ind_inc_color else (0, 0, 255)
    color_complete = ind_com_color if ind_com_color else (255, 255, 255)

    # Arc spans from just under 9 o'clock to just under 3 o'clock (through bottom)
    # In screen coords (y-down): 180° = 9 o'clock, 90° = 6 o'clock (bottom), 0° = 3 o'clock
    start_angle = 170 * math.pi / 180  # just under 9 o'clock (toward bottom)
    end_angle = 10 * math.pi / 180     # just under 3 o'clock (toward bottom)
    total_arc = start_angle - end_angle  # ~160 degrees through bottom (clockwise)

    # Calculate segment size
    total_gaps = gap_angle * (num_pages - 1) if num_pages > 1 else 0
    segment_arc = (total_arc - total_gaps) / num_pages

    # Draw smooth arcs using line segments
    points_per_segment = 50  # More points for smoother lines

    ctx.line_width = line_width

    for i in range(num_pages):
        # Page 0 starts at start_angle (170°), progressing clockwise through bottom to end_angle (10°)
        seg_start = start_angle - i * (segment_arc + gap_angle)

        # Determine how much of this segment to fill with each color
        if i < current_page:
            fill_ratio = 1.0
        elif i == current_page:
            fill_ratio = progress
        else:
            fill_ratio = 0.0

        # Draw the segment as smooth line (clockwise = decreasing angles)
        prev_x, prev_y = None, None
        for p in range(points_per_segment + 1):
            t = p / points_per_segment
            angle = seg_start - t * segment_arc
            x = arc_radius * math.cos(angle)
            y = arc_radius * math.sin(angle)

            if prev_x is not None:
                if t <= fill_ratio:
                    ctx.rgb(*color_complete)
                else:
                    ctx.rgb(*color_incomplete)

                ctx.move_to(prev_x, prev_y)
                ctx.line_to(x, y)
                ctx.stroke()

            prev_x, prev_y = x, y
