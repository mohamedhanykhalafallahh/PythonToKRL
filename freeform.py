"""Free-form path generator: any closed outline from a design file (no tkinter).

generate(params) -> (items, info), like cuboid.generate and cylinder.generate.

Path (the same idea as the cuboid and the cylinder, for any closed outline)
  - Turn 0 of a layer is the outline itself; turn t is the outline moved by E*t (outward, or
    inward with `inward`). Sharp outside corners become arcs, so the path stays round.
  - A 2D file (SVG / DXF) gives one outline, used for every layer. A 3D file (STL) is cut at
    the middle height of every layer, so each layer follows the model at its own height.
  - Even layers go from turn 0 to turn N-1, odd layers back, like the other shapes.
  - The fiber is never cut: the last part of every loop (the TRANSITION, about 20 mm) slides
    smoothly over to the next loop, or climbs to the next layer. It leaves and arrives tangent.
  - The seam (start of every loop) is put on the longest straight part of the first outline
    (else at its right-most point); the next loops start at the nearest point to it.
  - Fill: inward turns are added until nothing useful is left (the loop would be shorter than
    60 mm). Where the inside splits into separate areas, only the largest one is filled.
  - A path that is OPEN, or closed but crossing itself (an infinity shape), cannot be offset:
    it is followed exactly as drawn, one pass per layer (_generate_trace). A crossing path
    climbs to the next layer near its end; an open path is printed back and forth.
  - The points are turned into LIN and CIRC moves (contours.fit_moves), within 0.01 mm for
    drawings and 0.05 mm for meshes (fine facets become arcs again); `smoothing` sets it.
    A wider tolerance gives fewer moves but larger angles where two moves meet.

Orientation (auto-orient on): A = travel direction at the end of every move (the mean of the
two directions where two moves meet at an angle), B and C from the interface.
"""
import math
from dataclasses import dataclass
from typing import Optional

import contours as ct
import import_formats
import path_model as pm

MIN_RADIUS_WARN = 20.0      # mm: smallest arc radius the head is known to follow well
KINK_WARN = 5.0             # deg: a corner sharper than this is reported
PTP_S, PTP_T = 2, 43        # Status / Turn on the start PTP (same as the other shapes)
TRANSITION_STEP = 0.5       # mm: point spacing along a transition before it is fitted
FILL_MIN_LOOP = 60.0        # mm: Fill stops when the next inward loop would be shorter than this
FILL_MIN_WIDTH = 40.0       # mm: ... or narrower than this (two times the 20 mm radius the head can follow)
FILL_MAX_TURNS = 300
SMOOTH_3D = 0.05            # mm: automatic fit tolerance for sliced meshes (2D files: contours.FIT_TOL)


@dataclass
class FreeformParams:
    design: object                       # import_formats.Design, or None when no file is loaded
    xc: float
    yc: float
    z0: float
    step: float                          # E: distance between turns (mm)
    layer_height: float
    turns: int
    layers: int
    scale: float = 1.0
    rotation: float = 0.0                # deg, counter-clockwise, about the shape's centre
    outline: int = 1                     # 2D file: which closed outline (1 = the largest)
    corner_radius: Optional[float] = None    # None = keep sharp corners
    a: float = 180.0
    b: float = 0.0
    c: float = 180.0
    auto_orient: bool = True
    inward: bool = False                 # turns grow inward instead of outward
    smoothing: Optional[float] = None    # mm: how closely LIN / CIRC follow the points (None = automatic)
    fill: bool = False                   # inward turns until the shape is full (Turns is not used)


def normalize_angle(angle):
    while angle > 180.0:
        angle -= 360.0
    while angle < -180.0:
        angle += 360.0
    return angle


def a1(v):
    return round(float(v), 1)


def validate(p):
    """Returns (errors, warnings). Geometry problems show up in generate()."""
    errors = []
    d = p.design
    if d is None:
        errors.append("Choose a design file first (SVG, DXF or STL).")
    if p.step <= 0:
        errors.append("Turn step E must be greater than 0.")
    if p.layer_height <= 0:
        errors.append("Layer height must be greater than 0.")
    if p.turns < 1 or p.layers < 1:
        errors.append("Turns and layers must be at least 1.")
    if p.scale <= 0:
        errors.append("Scale must be greater than 0.")
    if p.corner_radius is not None and p.corner_radius < 0:
        errors.append("Corner radius cannot be negative (leave it blank to keep the corners).")
    if p.smoothing is not None and not (0 < p.smoothing <= 1.0):
        errors.append("Smoothing must be between 0 and 1 mm (leave it blank for automatic).")
    if d is not None and d.kind == "2d" and not (1 <= p.outline <= len(d.paths)):
        errors.append("Outline number must be 1..%d for this file." % len(d.paths))
    return errors, []


# ------------------------------------------------------------------ outlines per layer

def _place(poly, p, centre):
    """Design coordinates -> bed coordinates: scale and rotate about `centre`, centre to (xc, yc)."""
    return ct.transform(poly, p.scale, p.rotation, (p.xc - centre[0], p.yc - centre[1]), centre)


def _inside(poly, q):
    n, hit = len(poly), False
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > q[1]) != (y2 > q[1]) and q[0] < x1 + (q[1] - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def _overlap(a, b):
    """Do two outlines lie over each other? (their boxes overlap and one holds a point of the other)"""
    ba, bb = ct.bounds(a), ct.bounds(b)
    if ba[2] < bb[0] or bb[2] < ba[0] or ba[3] < bb[1] or bb[3] < ba[1]:
        return False
    step_a, step_b = max(1, len(a) // 40), max(1, len(b) // 40)
    return any(_inside(b, q) for q in a[::step_a]) or any(_inside(a, q) for q in b[::step_b])


def layer_outlines(p):
    """Base outline (turn 0) of every layer, in bed coordinates: (list of outlines, notes).
    A 2D design gives the same outline object for every layer."""
    d, notes = p.design, []
    if d.kind == "2d":
        src = d.paths[p.outline - 1][1]
        b = ct.bounds(src)
        base = ct.normalize(_place(src, p, ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)))
        if p.corner_radius:
            base = _rounded(base, p.corner_radius, "the outline")
        return [base] * p.layers, notes
    available = max(1, int(d.height * p.scale / p.layer_height + 1e-6))
    n = min(p.layers, available)
    if p.layers > available:
        notes.append("The model is %.1f mm high: %d layer%s of %g mm (not %d)."
                     % (d.height * p.scale, available, "" if available == 1 else "s", p.layer_height, p.layers))
    elif p.layers < available:
        notes.append("Only the lowest %d of the model's %d layers are printed (Layers = %d)."
                     % (n, available, p.layers))
    heights = [(k + 0.5) * p.layer_height / p.scale for k in range(n)]
    out, islands, jumps, prev = [], 0, 0, None
    for k, loops in enumerate(import_formats.slice_mesh(d, heights)):
        if not loops:
            raise ct.GeometryError("Layer %d (model height %.2f mm): the cut gives no closed outline. "
                                   "The STL may have gaps (not watertight)." % (k + 1, heights[k] * p.scale))
        # Which outline of this layer? The largest one that lies over the outline printed in the
        # layer below (so the wall goes straight up one part of the model); the largest of all
        # for the first layer, or if nothing lies over the previous one.
        chosen = loops[0]
        if prev is not None:
            over = [l for l in loops if _overlap(prev, l)]
            if over:
                chosen = over[0]
            else:
                jumps += 1
        prev = chosen
        islands += any(o is not chosen and not _inside(chosen, o[0]) and not _inside(o, chosen[0]) for o in loops)
        base = ct.normalize(_place(chosen, p, d.centre))
        if p.corner_radius:
            base = _rounded(base, p.corner_radius, "layer %d" % (k + 1))
        out.append(base)
    if jumps:
        notes.append("%d layer%s do%s not lie over the layer below (the model has an overhang or a gap there): "
                     "the path jumps sideways at that height." % (jumps, "" if jumps == 1 else "s",
                                                                   "es" if jumps == 1 else ""))
    if islands:
        notes.append("%d layer%s of the model ha%s several separate parts: only one of them (the one over "
                     "the layer below) is printed, because the fiber is never cut." % (islands, "" if islands == 1 else "s",
                                                           "s" if islands == 1 else "ve"))
    return out, notes


def _rounded(poly, r, what):
    try:
        out = ct.round_corners(poly, r)
    except ct.GeometryError:
        raise ct.GeometryError("Corner radius %g mm is too large for %s (it is narrower than twice "
                               "the radius somewhere)." % (r, what))
    if ct.area(out) < 0.5 * ct.area(poly):
        raise ct.GeometryError("Corner radius %g mm removes more than half of %s. Use a smaller radius." % (r, what))
    return out


# ------------------------------------------------------------------ path pieces

def _transition_length(step, loop_length, climb=0.0):
    """Length of the slide to the next loop: at least 20 mm, longer for a big step so its
    S-curve stays wider than a 30 mm radius, and 30 x the height of a climb to the next layer
    (a gentle slope, about 2 deg); never more than 40 % of the loop."""
    return min(max(20.0, math.sqrt(180.0 * step), 30.0 * climb), 0.4 * loop_length)


def _first_seam(poly, D):
    """Start point for the first loop: on the longest straight part (so the slide to the next
    loop happens on a straight), else the right-most point."""
    moves = ct.fit_moves(poly + [poly[0]])
    best, pos = None, poly[0]
    for m in moves:
        if m[0] == 'L':
            l = ct.dist(pos, m[1])
            if best is None or l > best[0] + 1e-9:
                best = (l, pos, m[1])
        pos = m[-1] if m[0] == 'L' else m[2]
    if best and best[0] >= 5.0:
        l, a, b = best
        f = min(l, (l + D) / 2.0) / l
        return (a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1]))
    return max(poly, key=lambda q: (q[0], -q[1]))


def _split_tail(path, D):
    """Closed path (first point repeated at the end) -> (main part, last D mm), both ending /
    starting at the same point."""
    acc = [0.0]
    for a, b in zip(path, path[1:]):
        acc.append(acc[-1] + ct.dist(a, b))
    cut = acc[-1] - D
    k = 0
    while acc[k + 1] < cut:
        k += 1
    seg = acc[k + 1] - acc[k]
    f = 0.0 if seg <= 0 else (cut - acc[k]) / seg
    q = (path[k][0] + f * (path[k + 1][0] - path[k][0]), path[k][1] + f * (path[k + 1][1] - path[k][1]))
    return path[:k + 1] + [q], [q] + path[k + 1:]


def _densify(pts, step):
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(math.ceil(ct.dist(a, b) / step)))
        for j in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * j / n, a[1] + (b[1] - a[1]) * j / n))
    return out


def _along(pts):
    """Function u (0..1) -> point at that fraction of the length of the open path `pts`."""
    acc = [0.0]
    for a, b in zip(pts, pts[1:]):
        acc.append(acc[-1] + ct.dist(a, b))
    total = acc[-1]

    def at(u):
        s_ = u * total
        k = at.k
        while k < len(pts) - 2 and acc[k + 1] < s_:
            k += 1
        at.k = k
        seg = acc[k + 1] - acc[k]
        f = 0.0 if seg <= 0 else min(1.0, max(0.0, (s_ - acc[k]) / seg))
        return (pts[k][0] + f * (pts[k + 1][0] - pts[k][0]), pts[k][1] + f * (pts[k + 1][1] - pts[k][1]))
    at.k = 0
    return at, total


def _blend(tail, target, z_from, z_to):
    """The tail of a loop, sliding over to the outline `target` (which must START at the point
    where the slide arrives) and from z_from to z_to: list of (x, y, z).

    The tail and the matching last part of the target are walked together, and the path moves
    from the first to the second with a smooth step, so it leaves and arrives tangent."""
    closed = target + [target[0]]
    _, i, _, _ = ct.closest_point(target, tail[0])
    q = ct.closest_point(target, tail[0])[0]
    part = [q] + closed[i + 1:]
    d_tail = math.fsum(ct.dist(a, b) for a, b in zip(tail, tail[1:]))
    d_part = math.fsum(ct.dist(a, b) for a, b in zip(part, part[1:]))
    if not (d_tail / 3.0 <= d_part <= d_tail * 3.0):     # odd shape: take the same length instead
        part = _split_tail(closed, min(d_tail, 0.4 * ct.perimeter(target)))[1]
    fa, la = _along(tail)
    fb, _ = _along(part)
    n = max(2, int(math.ceil(la / TRANSITION_STEP)))
    out = []
    for j in range(n + 1):
        u = j / float(n)
        w = u * u * (3.0 - 2.0 * u)
        pa, pb = fa(u), fb(u)
        out.append((pa[0] + w * (pb[0] - pa[0]), pa[1] + w * (pb[1] - pa[1]), z_from + w * (z_to - z_from)))
    out[-1] = (target[0][0], target[0][1], z_to)
    return out


def _fit3(points3, tol):
    """(x, y, z) points -> moves ('L', end3, t_start, t_end) / ('C', via3, end3, t_start, t_end, radius)
    with the travel directions (deg, in XY) at both ends."""
    zmap = {}
    for x, y, z in points3:
        zmap.setdefault((x, y), z)
    flat = [(x, y) for x, y, z in points3]
    pos = ct.dedupe(flat, False, 1e-9)[0]
    out = []
    for m in ct.fit_moves(flat, tol):
        if m[0] == 'L':
            end = m[1]
            h = math.degrees(math.atan2(end[1] - pos[1], end[0] - pos[0]))
            out.append(('L', (end[0], end[1], zmap[end]), h, h))
        else:
            _, via, end, centre, radius = m
            ccw = (pos[0] - centre[0]) * (via[1] - centre[1]) - (pos[1] - centre[1]) * (via[0] - centre[0]) > 0
            turn = 90.0 if ccw else -90.0
            h0 = math.degrees(math.atan2(pos[1] - centre[1], pos[0] - centre[0])) + turn
            h1 = math.degrees(math.atan2(end[1] - centre[1], end[0] - centre[0])) + turn
            z0, z1 = zmap[pos], zmap[end]
            out.append(('C', (via[0], via[1], (z0 + z1) / 2.0), (end[0], end[1], z1), h0, h1, radius))
        pos = end
    return out


# ------------------------------------------------------------------ generator

def generate(p):
    """Build the motion body. Returns (items, info). Raises ValueError (with a message for the
    user) when the parameters or the outline cannot give a path."""
    errors, _ = validate(p)
    if errors:
        raise ValueError(" ".join(errors))
    if p.design.kind == "2d" and p.design.paths[p.outline - 1][0] != "outline":
        return _generate_trace(p, *p.design.paths[p.outline - 1])
    bases, notes = layer_outlines(p)
    n_layers = len(bases)
    sign = -1.0 if (p.inward or p.fill) else 1.0

    cache, split_at = {}, []

    def turn_loop(layer, t):
        base = bases[layer]
        key = (id(base), t)
        if key not in cache:
            if t == 0:
                cache[key] = base
            else:
                loops = ct.offset(base, sign * p.step * t)
                if not loops:
                    raise ct.GeometryError("Layer %d, turn %d: the shape is too small or too thin: nothing is left "
                                           "%.3g mm %s the outline." % (layer + 1, t + 1, p.step * t,
                                                                        "inside" if sign < 0 else "outside"))
                if len(loops) > 1 and sign < 0:
                    split_at.append(t + 1)
                cache[key] = loops[0]
        return cache[key]

    counts = {}

    def n_turns(layer):
        """Turns of this layer: the Turns field, or with Fill as many inward turns as fit."""
        if not p.fill:
            return p.turns
        key = id(bases[layer])
        if key not in counts:
            n = 1
            while n < FILL_MAX_TURNS:
                try:
                    nxt = turn_loop(layer, n)
                    box = ct.bounds(nxt)
                    if ct.perimeter(nxt) < FILL_MIN_LOOP or min(box[2] - box[0], box[3] - box[1]) < FILL_MIN_WIDTH:
                        break
                except ct.GeometryError:
                    break
                n += 1
            counts[key] = n
        return counts[key]

    seq = []                                            # (layer, turn, outline, z) in print order
    for layer in range(n_layers):
        n = n_turns(layer)
        order = range(n) if layer % 2 == 0 else range(n - 1, -1, -1)
        for t in order:
            seq.append((layer, t, turn_loop(layer, t), p.z0 + p.layer_height * layer))
    if p.fill:
        ns = sorted(set(n_turns(layer) for layer in range(n_layers)))
        notes.append("Fill: %s inward turn%s per layer." % (ns[0] if len(ns) == 1 else "%d to %d" % (ns[0], ns[-1]),
                                                            "" if ns == [1] else "s"))
        if split_at:
            notes.append("From turn %d on the inside splits into separate areas: only the largest one is filled "
                         "(the fiber is never cut)." % min(split_at))

    # a mesh is made of flat facets: a wider tolerance turns them back into arcs
    tol = p.smoothing if p.smoothing is not None else (SMOOTH_3D if p.design.kind == "3d" else ct.FIT_TOL)
    entries = []                                        # ('comment', text) or a move from _fit3
    first = seq[0][2]
    seam = _first_seam(first, _transition_length(p.step, ct.perimeter(first)))
    start = None
    for k, (layer, t, poly, z) in enumerate(seq):
        if k == 0 or seq[k - 1][0] != layer:
            nt_ = n_turns(layer)
            kind = "SINGLE TURN" if nt_ == 1 else ("TURNS 0 -> %d" % (nt_ - 1) if layer % 2 == 0
                                                   else "TURNS %d -> 0" % (nt_ - 1))
            entries.append(('comment', "===== LAYER %d ===== (FREE-FORM, %s)" % (layer, kind)))
        loop = ct.reseam(poly, seam)
        seam = loop[0]
        if start is None:
            start = (seam[0], seam[1], z)
        path = loop + [loop[0]]
        entries.append(('comment', "L%d T%d%s" % (layer, t, " - START" if k == 0 else "")))
        if k == len(seq) - 1:
            entries.extend(_fit3([(x, y, z) for x, y in path], tol))
            break
        nl, nt, npoly, nz = seq[k + 1]
        main, tail = _split_tail(path, _transition_length(p.step, ct.perimeter(poly), abs(nz - z)))
        entries.extend(_fit3([(x, y, z) for x, y in main], tol))
        target = ct.reseam(npoly, seam)                  # the next loop, starting where the slide arrives
        slide = _blend(tail, target, z, nz)
        seam = target[0]
        moves = _fit3(slide, tol)
        if nl == layer:
            entries.append(('comment', "L%d T%d -> T%d TRANSITION (%d move%s)"
                            % (layer, t, nt, len(moves), "" if len(moves) == 1 else "s")))
        else:
            entries.append(('comment', "L%d -> L%d TRANSITION (%d move%s)"
                            % (layer, nl, len(moves), "" if len(moves) == 1 else "s")))
        entries.extend(moves)

    return _finish(p, entries, start, notes, n_layers, (n_turns(0) if p.fill else p.turns) * p.step)


def _generate_trace(p, kind, src):
    """A path that cannot be offset (open, or crossing itself): followed exactly as drawn, one
    pass per layer."""
    b = ct.bounds(src)
    pts = _place(src, p, ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0))
    what = "crosses itself" if kind == "crossing" else "is open"
    notes = []
    if p.fill or p.inward:                              # (Turns is simply not used: one pass per layer)
        notes.append("This path %s, so it is followed exactly as drawn, one pass per layer "
                     "(inward and Fill are not used)." % what)
    if p.corner_radius:
        notes.append("Corner radius is not used for a path that %s." % what)
    tol = p.smoothing if p.smoothing is not None else ct.FIT_TOL
    z_of = lambda layer: p.z0 + p.layer_height * layer
    entries = []
    if kind == "crossing":
        notes.append("The path crosses itself: at the crossing the fiber lies on top of itself (twice the "
                     "height there in every layer).")
        length = ct.perimeter(pts)
        D = _transition_length(p.step, length, p.layer_height)
        loop = ct.reseam(pts, _first_seam(pts, D))
        path = loop + [loop[0]]
        start = (path[0][0], path[0][1], z_of(0))
        for layer in range(p.layers):
            z = z_of(layer)
            entries.append(('comment', "===== LAYER %d ===== (FREE-FORM, AS DRAWN)" % layer))
            entries.append(('comment', "L%d T0%s" % (layer, " - START" if layer == 0 else "")))
            if layer == p.layers - 1:
                entries.extend(_fit3([(x, y, z) for x, y in path], tol))
                break
            main, tail_ = _split_tail(path, D)
            entries.extend(_fit3([(x, y, z) for x, y in main], tol))
            moves = _fit3(_climb(tail_, z, z_of(layer + 1)), tol)
            entries.append(('comment', "L%d -> L%d TRANSITION (%d move%s)"
                            % (layer, layer + 1, len(moves), "" if len(moves) == 1 else "s")))
            entries.extend(moves)
    else:
        if p.layers > 1:
            notes.append("An open path is printed back and forth: the head turns round at both ends.")
        length = math.fsum(ct.dist(q, r) for q, r in zip(pts, pts[1:]))
        D = min(max(20.0, 30.0 * p.layer_height), 0.4 * length)
        start = (pts[0][0], pts[0][1], z_of(0))
        for layer in range(p.layers):
            z = z_of(layer)
            path = pts if layer % 2 == 0 else pts[::-1]
            if layer > 0:                                # the first part of the way back climbs
                rest, head = _split_tail(path[::-1], D)
                head, path = head[::-1], rest[::-1]
                moves = _fit3(_climb(head, z_of(layer - 1), z), tol)
                entries.append(('comment', "L%d -> L%d TRANSITION (%d move%s)"
                                % (layer - 1, layer, len(moves), "" if len(moves) == 1 else "s")))
                entries.extend(moves)
            entries.append(('comment', "===== LAYER %d ===== (FREE-FORM, AS DRAWN)" % layer))
            entries.append(('comment', "L%d T0%s" % (layer, " - START" if layer == 0 else "")))
            entries.extend(_fit3([(x, y, z) for x, y in path], tol))
    return _finish(p, entries, start, notes, p.layers, p.step)


def _climb(pts, z_from, z_to):
    """The same stretch, rising from z_from to z_to with a smooth step: list of (x, y, z)."""
    dense = _densify(pts, TRANSITION_STEP)
    acc = [0.0]
    for a, b in zip(dense, dense[1:]):
        acc.append(acc[-1] + ct.dist(a, b))
    total = acc[-1] or 1.0
    out = []
    for q, s_ in zip(dense, acc):
        u = s_ / total
        out.append((q[0], q[1], z_from + u * u * (3.0 - 2.0 * u) * (z_to - z_from)))
    return out


def _finish(p, entries, start, notes, n_layers, wall):
    """Entries (comments and fitted moves) -> (items, info): orientation, warnings, numbers."""
    radii = []
    # orientation: A at the end of a move = mean of its end direction and the next move's start
    moves = [e for e in entries if e[0] != 'comment']

    def ori(heading):
        if p.auto_orient:
            return (a1(normalize_angle(heading)), p.b, p.c)
        return (p.a, p.b, p.c)

    def h_start(m):
        return m[2] if m[0] == 'L' else m[3]

    def h_end(m):
        return m[3] if m[0] == 'L' else m[4]
    items = [pm.Ptp(pm.pose(start, ori(h_start(moves[0])), PTP_S, PTP_T))]
    idx = 0
    for e in entries:
        if e[0] == 'comment':
            items.append(pm.Comment(e[1]))
            continue
        he = h_end(e)
        if idx + 1 < len(moves):
            he = he + pm.angle_diff(he, h_start(moves[idx + 1])) / 2.0
        if e[0] == 'L':
            items.append(pm.Lin(pm.pose(e[1], ori(he))))
        else:
            items.append(pm.Circ(pm.pose(e[1]), pm.pose(e[2], ori(he))))
            radii.append(e[5])
        idx += 1

    warnings = list(notes)
    kinks = [abs(pm.angle_diff(h_end(m0), h_start(m1))) for m0, m1 in zip(moves, moves[1:])]
    max_kink = max(kinks) if kinks else 0.0
    if max_kink > KINK_WARN:
        n_sharp = sum(k > KINK_WARN for k in kinks)
        advice = ("Enter a Corner radius to round real corners. If they are the flat facets of a coarse "
                  "STL, export the STL with a finer resolution." if p.design.kind == "3d"
                  else "Enter a Corner radius to round them.")
        warnings.append("%d sharp corner%s (up to %.0f deg): the head has to turn on the spot there. %s"
                        % (n_sharp, "" if n_sharp == 1 else "s", max_kink, advice))
    if radii and min(radii) < MIN_RADIUS_WARN - 0.01:
        warnings.append("Smallest arc radius is %.1f mm (below %g mm): the head may not follow it well."
                        % (min(radii), MIN_RADIUS_WARN))
    _, moves3 = pm.path_3d(items)
    info = {
        "moves": len(moves3),
        "length_mm": pm.path_length(moves3),
        "min_arc_radius": min(radii) if radii else None,
        "max_kink_deg": max_kink,
        "layers": n_layers,
        "z_range": (p.z0, p.z0 + p.layer_height * (n_layers - 1)),
        "wall_thickness": wall,
        "warnings": warnings,
    }
    return items, info
