"""Shape geometry for the generators (no tkinter).

A *loop* is the app's base-path data:
    points           [P1, LIN end, LIN end, ...]   P1 = PTP start, one more per LIN
    points_circ      [via, end, via, end, ...]     two per CIRC
    motion_commands  ["LIN", "CIRC", ...]          the moves after P1, in order

Functions:
    auto_corner_radius(L, W)        default corner radius of a rounded rectangle
    rounded_rect_base(...)          the 11-point rounded-rectangle base loop
    loop_normals(...)               outward unit normal at every loop point
    offset_loop(..., d)             the loop moved outward by d (next turn)

Offsetting: every point moves by d along its outward normal. On a straight edge that
moves the edge by d; on an arc it keeps the centre and grows the radius by d. So the
offset of a tangent-continuous loop is again tangent-continuous, whatever its order or
direction (CW / CCW) - no point indices are hard-coded.
"""
import math

SQRT_HALF = 2 ** -0.5          # 45 deg component (the value the app always used)
_SNAP = (0.0, 1.0, -1.0, SQRT_HALF, -SQRT_HALF)
_SNAP_TOL = 1e-9


# ------------------------------------------------------------------ rounded rectangle

def auto_corner_radius(L, W):
    """15% of the shorter side, clamped to [2 mm, shorter side / 3]."""
    min_edge = max(min(L, W), 1.0)
    return max(2.0, min(0.15 * min_edge, min_edge / 3.0))


def rounded_rect_base(xr, yr, z, L, W, r):
    """Axis-aligned rounded rectangle (centre xr/yr, size L x W, corner radius r) at height z.

    Order (counter-clockwise, start top-right):
        PTP P1 -> LIN P2 (top edge) -> CIRC TL -> LIN P5 (left) -> CIRC BL -> LIN P8 (bottom)
        -> CIRC BR -> LIN P11 (right edge). The 4th corner (P11 -> P1) is closed by the
        turn/layer transition. Via points sit at 45 deg on each fillet.
    Returns (points, points_circ, motion_commands)."""
    top_y, bottom_y = yr + W / 2, yr - W / 2
    left_x, right_x = xr - L / 2, xr + L / 2

    center_TL = (left_x + r, top_y - r)
    center_BL = (left_x + r, bottom_y + r)
    center_BR = (right_x - r, bottom_y + r)
    k = SQRT_HALF
    mid_TL = (center_TL[0] - r * k, center_TL[1] + r * k)
    mid_BL = (center_BL[0] - r * k, center_BL[1] - r * k)
    mid_BR = (center_BR[0] + r * k, center_BR[1] - r * k)

    points = [
        (right_x - r, top_y, z),        # P1  start (PTP), top edge near TR
        (left_x + r, top_y, z),         # P2  end of top edge
        (left_x, bottom_y + r, z),      # P5  end of left edge
        (right_x - r, bottom_y, z),     # P8  end of bottom edge
        (right_x, top_y - r, z),        # P11 end of right edge
    ]
    points_circ = [
        (mid_TL[0], mid_TL[1], z), (left_x, top_y - r, z),        # P3, P4  TL corner
        (mid_BL[0], mid_BL[1], z), (left_x + r, bottom_y, z),     # P6, P7  BL corner
        (mid_BR[0], mid_BR[1], z), (right_x, bottom_y + r, z),    # P9, P10 BR corner
    ]
    motion_commands = ["LIN", "CIRC", "LIN", "CIRC", "LIN", "CIRC", "LIN"]
    return points, points_circ, motion_commands


# ------------------------------------------------------------------ generic loop offset

def _path_order(points, points_circ, motion_commands):
    """Loop as a list of moves: ('LIN', start, end) / ('CIRC', start, via, end), with each
    point given as ('p', index) or ('c', index) so results can be written back."""
    moves, cur = [], ('p', 0)
    i, j = 1, 0
    for k in motion_commands:
        if k == "LIN":
            moves.append(("LIN", cur, ('p', i)))
            cur = ('p', i)
            i += 1
        elif k == "CIRC":
            moves.append(("CIRC", cur, ('c', j), ('c', j + 1)))
            cur = ('c', j + 1)
            j += 2
    return moves


def _snap(v):
    for s in _SNAP:
        if abs(v - s) < _SNAP_TOL:
            return s
    return v


def _unit(x, y):
    n = math.hypot(x, y)
    return (x / n, y / n) if n > 0 else None


def _circumcentre(a, b, c):
    ax, ay, bx, by, cx, cy = a[0], a[1], b[0], b[1], c[0], c[1]
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy)


def loop_orientation(points, points_circ, motion_commands):
    """+1 for a counter-clockwise loop, -1 for clockwise (signed area of all its points)."""
    get = lambda ref: (points if ref[0] == 'p' else points_circ)[ref[1]]
    seq = [get(('p', 0))]
    for m in _path_order(points, points_circ, motion_commands):
        seq.extend(get(ref) for ref in m[2:])
    area = sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(seq, seq[1:] + seq[:1]))
    return 1 if area >= 0 else -1


def loop_normals(points, points_circ, motion_commands):
    """Outward unit normal (nx, ny) for every loop point, as (normals, normals_circ) in the
    same layout as (points, points_circ).

    Straight-edge points take the edge's normal (exact for axis-aligned edges); the via of
    an arc, and an arc end not followed by a straight edge, take the radial direction of
    the arc. Components within 1e-9 of 0, +-1 or +-sqrt(1/2) are snapped to those exact
    values, so axis-aligned / 45 deg geometry stays exact."""
    get = lambda ref: (points if ref[0] == 'p' else points_circ)[ref[1]]
    orient = loop_orientation(points, points_circ, motion_commands)
    moves = _path_order(points, points_circ, motion_commands)
    normals, normals_circ = [None] * len(points), [None] * len(points_circ)

    def put(ref, n, overwrite=True):
        arr = normals if ref[0] == 'p' else normals_circ
        if overwrite or arr[ref[1]] is None:
            arr[ref[1]] = n

    def edge_normal(a, b):
        t = _unit(b[0] - a[0], b[1] - a[1])
        if t is None:
            return None
        # outward = right of travel for a CCW loop, left for CW
        return (orient * t[1], -orient * t[0])

    def normal_of(ref):
        return (normals if ref[0] == 'p' else normals_circ)[ref[1]]

    # 1) arcs: radial normals for start (if nothing better comes later), via and end
    for m in moves:
        if m[0] != "CIRC":
            continue
        s, v, e = get(m[1]), get(m[2]), get(m[3])
        c = _circumcentre(s, v, e)
        turn = (v[0] - s[0]) * (e[1] - v[1]) - (v[1] - s[1]) * (e[0] - v[0])
        sign = 1 if (turn > 0) == (orient > 0) else -1          # convex corner: away from centre
        for ref in (m[1], m[2], m[3]):
            p = get(ref)
            n = _unit(p[0] - c[0], p[1] - c[1]) if c else None
            if n is None:                                         # straight "arc": use the chord
                n = edge_normal(s, e)
            else:
                n = (sign * n[0], sign * n[1])
            put(ref, n, overwrite=(ref != m[1]))
    # 2) straight edges: their normal wins for both of their points (exact, keeps edges straight)
    for m in moves:
        if m[0] == "LIN":
            n = edge_normal(get(m[1]), get(m[2]))
            if n is not None:
                put(m[1], n)
                put(m[2], n)
    # 3) zero-length edges (e.g. r = L/2): an end without a normal takes the other end's
    for m in moves:
        if m[0] == "LIN":
            for a, b in ((m[1], m[2]), (m[2], m[1])):
                if normal_of(a) is None and normal_of(b) is not None:
                    put(a, normal_of(b))
    # 4) anything still left (degenerate input only): no move
    for arr in (normals, normals_circ):
        for idx, n in enumerate(arr):
            if n is None:
                arr[idx] = (0.0, 0.0)
    snap = lambda n: (_snap(n[0]), _snap(n[1]))
    return [snap(n) for n in normals], [snap(n) for n in normals_circ]


def offset_loop(points, points_circ, motion_commands, d):
    """The loop moved outward by d (mm): every point p becomes p + d * n (n = outward
    normal, Z unchanged). Returns new (points, points_circ) as lists of [x, y, z]."""
    normals, normals_circ = loop_normals(points, points_circ, motion_commands)
    move = lambda p, n: [p[0] + d * n[0], p[1] + d * n[1], p[2]]
    return ([move(p, n) for p, n in zip(points, normals)],
            [move(p, n) for p, n in zip(points_circ, normals_circ)])
