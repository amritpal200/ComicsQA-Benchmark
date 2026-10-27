"""Box matching for character grounding (pure Python, no dependencies).

Grounded boxes from one panel are merged into entities (near-duplicate boxes for "the boy" and "he"),
then matched one-to-one to reference character boxes (human or MAGI v3) by maximum total IoU
(Hungarian algorithm), as in "From Panels to Prose" (IoU + bipartite matching).
"""


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def center_inside(box, region):
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return region[0] <= cx <= region[2] and region[1] <= cy <= region[3]


def hungarian_max(weights):
    """Maximum-weight one-to-one assignment for a rectangular matrix (rows x cols).
    Returns {row: col}. O(n^3) Hungarian algorithm with potentials (minimises -weight)."""
    rows = len(weights)
    cols = len(weights[0]) if rows else 0
    if rows == 0 or cols == 0:
        return {}
    transpose = rows > cols
    if transpose:
        weights = [list(col) for col in zip(*weights)]
        rows, cols = cols, rows
    INF = float('inf')
    cost = [[-w for w in row] for row in weights]
    u, v = [0.0] * (rows + 1), [0.0] * (cols + 1)
    p, way = [0] * (cols + 1), [0] * (cols + 1)
    for i in range(1, rows + 1):
        p[0], j0 = i, 0
        minv, used = [INF] * (cols + 1), [False] * (cols + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], INF, 0
            for j in range(1, cols + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(cols + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    assignment = {p[j] - 1: j - 1 for j in range(1, cols + 1) if p[j]}
    if transpose:
        assignment = {c: r for r, c in assignment.items()}
    return assignment


def merge_boxes(boxes, threshold):
    """Group near-duplicate boxes (IoU >= threshold). Returns (entity boxes, box -> entity index)."""
    entities, members, owner = [], [], []
    for box in boxes:
        best, best_iou = None, threshold
        for k, members_k in enumerate(members):
            score = max(iou(box, other) for other in members_k)
            if score >= best_iou:
                best, best_iou = k, score
        if best is None:
            entities.append(list(box))
            members.append([box])
            owner.append(len(entities) - 1)
        else:
            members[best].append(box)
            owner.append(best)
    # entity box = coordinate-wise mean of its members
    entities = [[sum(b[i] for b in m) / len(m) for i in range(4)] for m in members]
    return entities, owner


def match_entities(entities, references, min_iou, margin):
    """Match entity boxes to reference boxes [(ref_id, box)]. Returns one result per entity:
    {'status': 'matched'|'ambiguous'|'unmatched', 'ref': ref_id|None, 'iou', 'second_iou'}.
    'ambiguous': assigned, but another reference overlaps almost as much (within margin)."""
    if not references:
        return [{'status': 'unmatched', 'ref': None, 'iou': 0.0, 'second_iou': 0.0} for _ in entities]
    scores = [[iou(e, box) for _, box in references] for e in entities]
    assignment = hungarian_max(scores)
    results = []
    for i, row in enumerate(scores):
        j = assignment.get(i)
        best = row[j] if j is not None else 0.0
        others = sorted((s for k, s in enumerate(row) if k != j), reverse=True)
        second = others[0] if others else 0.0
        if j is None or best < min_iou:
            results.append({'status': 'unmatched', 'ref': None, 'iou': round(best, 4),
                            'second_iou': round(max(row), 4) if j is None else round(second, 4)})
        else:
            status = 'ambiguous' if second >= best - margin else 'matched'
            results.append({'status': status, 'ref': references[j][0], 'iou': round(best, 4),
                            'second_iou': round(second, 4)})
    return results
