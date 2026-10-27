"""Box geometry and manga reading order (pure Python).

`box_to_panel`, `sort_texts_within_panel` and `sort_boxes_in_reading_order` are ports of
get_text_to_panel_mapping / sort_texts_within_panel / sort_text_boxes_in_reading_order from the
MAGI v3 checkpoint's utils.py (shapely replaced by exact rectangle arithmetic), so human boxes are
ordered with the same rules MAGI v3 uses for its own text. Panel order itself is taken from the
MAGI v3 annotations (`reading_order.panels`). Boxes are [x1, y1, x2, y2] pixels.
"""
import math


def area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def intersects(a, b):
    """Closed rectangles: touching counts (as shapely.intersects)."""
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def intersection_area(a, b):
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def rect_distance(a, b):
    dx = max(0.0, b[0] - a[2], a[0] - b[2])
    dy = max(0.0, b[1] - a[3], a[1] - b[3])
    return math.hypot(dx, dy)


def point_rect_distance(x, y, r):
    dx = max(0.0, r[0] - x, x - r[2])
    dy = max(0.0, r[1] - y, y - r[3])
    return math.hypot(dx, dy)


def box_to_panel(box, panels):
    """Index of the panel with the largest overlap; if none overlaps, the nearest; -1 if no panels."""
    if not panels:
        return -1
    overlaps = [(intersection_area(box, p), j) for j, p in enumerate(panels) if intersects(box, p)]
    if overlaps:
        return max(overlaps, key=lambda x: x[0])[1]
    return min(((rect_distance(box, p), j) for j, p in enumerate(panels)), key=lambda x: x[0])[1]


def sort_texts_within_panel(boxes):
    """Order by distance from the panel's top-right reference point (right-to-left manga)."""
    if not boxes:
        return []
    ref_x = max(b[2] for b in boxes)
    ref_y = min(b[1] for b in boxes)
    return [i for _, i in sorted(((point_rect_distance(ref_x, ref_y, b), i) for i, b in enumerate(boxes)),
                                 key=lambda x: x[0])]


def sort_boxes_in_reading_order(boxes, sorted_panels):
    """Reading order of boxes given panels already in reading order: group by panel (in panel order),
    then within each panel by sort_texts_within_panel. Returns indices into `boxes`."""
    if not boxes:
        return []
    panel_of = [box_to_panel(b, sorted_panels) for b in boxes]
    order = [i for i, _ in sorted(enumerate(panel_of), key=lambda x: x[1])]
    result, start = [], 0
    while start < len(order):
        end = start
        while end < len(order) and panel_of[order[end]] == panel_of[order[start]]:
            end += 1
        group = order[start:end]
        result += [group[k] for k in sort_texts_within_panel([boxes[i] for i in group])]
        start = end
    return result
