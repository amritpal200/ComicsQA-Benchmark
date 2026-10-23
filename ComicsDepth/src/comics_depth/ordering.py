"""Depth-ordering accuracy in the ComicsDepth benchmark format (fixed upstream evaluation.py).

Annotation file: one point per line, "inter intra x y" (integers). `inter` is the object depth
level (1 = closest); `intra` orders points inside the same object (1 = closest). For every pair
of points: different `inter` -> inter-object pair; same `inter` but different `intra` ->
intra-object pair; the closer point must get the strictly larger prediction (inverse depth).
x, y are pixel coordinates in the image the prediction was made for.
"""


def read_ordering(path):
    points = []
    with open(path) as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) != 4:
                raise ValueError(f"{path}:{line_no}: expected 'inter intra x y'")
            points.append(tuple(int(v) for v in parts))
    return points


def ordering_accuracy(pred, points):
    """pred: 2-D array (H, W) of inverse depth. Returns counts for inter/intra pairs."""
    height, width = pred.shape
    counts = {"inter_correct": 0, "inter_total": 0, "intra_correct": 0, "intra_total": 0,
              "ties": 0, "out_of_bounds": 0}
    valid = []
    for inter, intra, x, y in points:
        if 0 <= x < width and 0 <= y < height:
            valid.append((inter, intra, float(pred[y][x])))
        else:
            counts["out_of_bounds"] += 1
    for i in range(len(valid)):
        for j in range(i):
            a, b = valid[i], valid[j]
            if a[0] != b[0]:
                kind, near, far = "inter", *((a, b) if a[0] < b[0] else (b, a))
            elif a[1] != b[1]:
                kind, near, far = "intra", *((a, b) if a[1] < b[1] else (b, a))
            else:
                continue
            counts[f"{kind}_total"] += 1
            counts[f"{kind}_correct"] += int(near[2] > far[2])
            counts["ties"] += int(near[2] == far[2])
    return counts


def summarize(counts_list):
    total = {}
    for counts in counts_list:
        for key, value in counts.items():
            total[key] = total.get(key, 0) + value
    for kind in ("inter", "intra"):
        n = total.get(f"{kind}_total", 0)
        total[f"{kind}_accuracy"] = total.get(f"{kind}_correct", 0) / n if n else None
    return total
