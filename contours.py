"""2D outline geometry for imported designs (no tkinter, no extra libraries).

An outline is a POLYGON: a list of (x, y) points in mm, closed (the last point joins the first
one, which is not repeated) and counter-clockwise after normalize().

    flatten_arc / flatten_bezier      curves -> points within a chord tolerance
    normalize(points)                 clean (no duplicates), counter-clockwise
    offset(poly, d)                   outline moved outward (d > 0) or inward (d < 0), round joins
    round_corners(poly, r)            sharp corners replaced by arcs of radius r
    closest_point / reseam            nearest point on an outline; start the outline there
    fit_moves(points, tol)            points -> ('L', end) / ('C', via, end) pieces (LIN / CIRC)
    chain_segments(segments, tol)     loose pieces (DXF lines, STL slice) -> closed / open paths

The offset works on points (not on lines and arcs): the outline is moved point by point along
its normal, sharp outside corners get an arc, and every part that came closer to the original
outline than the offset distance is cut away. It is exact to about the flatten tolerance, far
below what the fiber head can follow. fit_moves() then turns the points back into few LIN and
CIRC moves.
"""
import math

FLATTEN_TOL = 0.002      # mm: chord error when curves become points
FIT_TOL = 0.01           # mm: how far a fitted LIN / CIRC may be from the points
MAX_ARC_SWEEP = 100.0    # deg: longest single CIRC (the cuboid and the cylinder use 90)


class GeometryError(ValueError):
    """The outline cannot be processed (message is shown to the user)."""


# ------------------------------------------------------------------ basics

def hyp(x, y):
    """sqrt(x^2 + y^2), written out: math.hypot and sum() round differently in newer Python
    versions, and the same design must give the same program on every PC."""
    return math.sqrt(x * x + y * y)


def dist(a, b):
    return hyp(a[0] - b[0], a[1] - b[1])


def area(poly):
    """Signed area: positive for a counter-clockwise outline."""
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def perimeter(poly):
    return math.fsum(dist(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def bounds(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def dedupe(points, closed=True, tol=1e-9):
    """Remove repeated neighbours (and the closing duplicate of a closed outline)."""
    out = []
    for p in points:
        if not out or dist(out[-1], p) > tol:
            out.append((float(p[0]), float(p[1])))
    if closed:
        while len(out) > 1 and dist(out[0], out[-1]) <= tol:
            out.pop()
    return out


def normalize(points, tol=1e-9):
    """Closed outline without duplicate points, counter-clockwise."""
    poly = dedupe(points, True, tol)
    if len(poly) < 3:
        raise GeometryError("The outline has fewer than 3 points.")
    if area(poly) < 0:
        poly.reverse()
    return poly


def transform(points, scale=1.0, rotation_deg=0.0, move=(0.0, 0.0), about=(0.0, 0.0)):
    """Scale and rotate about `about`, then move by `move`."""
    c, s = math.cos(math.radians(rotation_deg)), math.sin(math.radians(rotation_deg))
    out = []
    for x, y in points:
        x, y = (x - about[0]) * scale, (y - about[1]) * scale
        out.append((about[0] + x * c - y * s + move[0], about[1] + x * s + y * c + move[1]))
    return out


# ------------------------------------------------------------------ curves -> points

def _arc_steps(radius, sweep, tol):
    if radius <= tol:
        return 1
    step = 2.0 * math.acos(max(-1.0, 1.0 - tol / radius))
    return max(1, int(math.ceil(abs(sweep) / step)))


def flatten_arc(centre, radius, a0, sweep, tol=FLATTEN_TOL, include_start=True):
    """Points on a circular arc from angle a0 over `sweep` (radians, + = counter-clockwise)."""
    n = _arc_steps(radius, sweep, tol)
    return [(centre[0] + radius * math.cos(a0 + sweep * k / n), centre[1] + radius * math.sin(a0 + sweep * k / n))
            for k in range(0 if include_start else 1, n + 1)]


def flatten_bezier(ctrl, tol=FLATTEN_TOL, include_start=True):
    """Points on a quadratic (3 control points) or cubic (4) Bezier curve."""
    if len(ctrl) == 3:
        (x0, y0), (x1, y1), (x2, y2) = ctrl
        m = 2.0 * hyp(x0 - 2 * x1 + x2, y0 - 2 * y1 + y2)
    else:
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = ctrl
        m = 6.0 * max(hyp(x0 - 2 * x1 + x2, y0 - 2 * y1 + y2), hyp(x1 - 2 * x2 + x3, y1 - 2 * y2 + y3))
    n = max(1, int(math.ceil(math.sqrt(m / (8.0 * tol)))))
    out = []
    for k in range(0 if include_start else 1, n + 1):
        t = k / float(n)
        u = 1.0 - t
        if len(ctrl) == 3:
            out.append((u * u * x0 + 2 * u * t * x1 + t * t * x2, u * u * y0 + 2 * u * t * y1 + t * t * y2))
        else:
            out.append((u ** 3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t ** 3 * x3,
                        u ** 3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t ** 3 * y3))
    return out


# ------------------------------------------------------------------ distance / closest point

def _closest_on_segment(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
    q = (a[0] + t * dx, a[1] + t * dy)
    return q, t


class _Grid(object):
    """Edges of an outline in square cells, for quick 'how far is this point' questions."""

    def __init__(self, poly, cell):
        self.poly, self.cell = poly, max(cell, 1e-6)
        self.cells = {}
        n = len(poly)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            x0, x1 = sorted((a[0], b[0]))
            y0, y1 = sorted((a[1], b[1]))
            for gx in range(int(math.floor(x0 / self.cell)), int(math.floor(x1 / self.cell)) + 1):
                for gy in range(int(math.floor(y0 / self.cell)), int(math.floor(y1 / self.cell)) + 1):
                    self.cells.setdefault((gx, gy), []).append(i)

    def closer_than(self, p, d):
        """True if some edge is closer to p than d."""
        c, n, poly = self.cell, len(self.poly), self.poly
        seen = set()
        for gx in range(int(math.floor((p[0] - d) / c)), int(math.floor((p[0] + d) / c)) + 1):
            for gy in range(int(math.floor((p[1] - d) / c)), int(math.floor((p[1] + d) / c)) + 1):
                for i in self.cells.get((gx, gy), ()):
                    if i in seen:
                        continue
                    seen.add(i)
                    q, _ = _closest_on_segment(p, poly[i], poly[(i + 1) % n])
                    if dist(p, q) < d:
                        return True
        return False


def closest_point(poly, p):
    """Nearest point of the outline to p: (point, edge index, position 0..1 on that edge, distance)."""
    best = None
    n = len(poly)
    for i in range(n):
        q, t = _closest_on_segment(p, poly[i], poly[(i + 1) % n])
        d = dist(p, q)
        if best is None or d < best[3]:
            best = (q, i, t, d)
    return best


def reseam(poly, p):
    """The same outline, starting at its point nearest to p (that point is added if needed)."""
    q, i, t, _ = closest_point(poly, p)
    n = len(poly)
    if dist(q, poly[i]) < 1e-9:
        return poly[i:] + poly[:i]
    if dist(q, poly[(i + 1) % n]) < 1e-9:
        j = (i + 1) % n
        return poly[j:] + poly[:j]
    return [q] + poly[i + 1:] + poly[:i + 1]


# ------------------------------------------------------------------ offset

def _seg_intersection(a, b, c, d):
    """Crossing point of the segments a-b and c-d, or None."""
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-18:
        return None
    qp = (c[0] - a[0], c[1] - a[1])
    t = (qp[0] * s[1] - qp[1] * s[0]) / den
    u = (qp[0] * r[1] - qp[1] * r[0]) / den
    e = 1e-9
    if -e <= t <= 1 + e and -e <= u <= 1 + e:
        return (a[0] + t * r[0], a[1] + t * r[1])
    return None


def _raw_offset(poly, d, tol):
    """The outline moved by d along its outward normals, point by point. Corners that open up get
    an arc; corners that close get the crossing point of the two moved edges when it fits, else
    both end points (the loop this makes is cut away later)."""
    n = len(poly)
    dirs, lens = [], []
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        l = dist(a, b)
        dirs.append(((b[0] - a[0]) / l, (b[1] - a[1]) / l))
        lens.append(l)
    normals = [(u[1], -u[0]) for u in dirs]             # outward for a counter-clockwise outline
    # how much each edge loses at its two ends where neighbours close up (mitre)
    trim = [[0.0, 0.0] for _ in range(n)]
    kind = [None] * n                                   # corner before edge i: 'arc' / 'mitre' / 'raw'
    for i in range(n):
        u0, u1 = dirs[i - 1], dirs[i]
        cross = u0[0] * u1[1] - u0[1] * u1[0]
        dot = u0[0] * u1[0] + u0[1] * u1[1]
        if abs(cross) < 1e-12 and dot > 0:
            kind[i] = 'straight'
        elif cross * d > 0:
            kind[i] = 'arc'
        else:
            half = math.atan2(abs(cross), dot) / 2.0
            t = abs(d) * math.tan(half) if half < math.pi / 2 - 1e-6 else float("inf")
            trim[i - 1][1] = trim[i][0] = t
            kind[i] = 'mitre'
    for i in range(n):                                  # a mitre needs room on both edges
        if kind[i] == 'mitre':
            prev = i - 1
            if trim[prev][0] + trim[prev][1] > lens[prev] * (1 - 1e-9) or \
                    trim[i][0] + trim[i][1] > lens[i] * (1 - 1e-9):
                kind[i] = 'raw'
    out = []
    max_step = max(abs(d) / 2.0, 0.5)
    for i in range(n):
        v, nx = poly[i], normals[i]
        prev_n = normals[i - 1]
        start = (v[0] + d * nx[0], v[1] + d * nx[1])
        if kind[i] == 'arc':
            a0 = math.atan2(prev_n[1] * (1 if d > 0 else -1), prev_n[0] * (1 if d > 0 else -1))
            a1 = math.atan2(nx[1] * (1 if d > 0 else -1), nx[0] * (1 if d > 0 else -1))
            sweep = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
            out.extend(flatten_arc(v, abs(d), a0, sweep, tol))
        elif kind[i] == 'mitre':
            t = trim[i][0]
            out.append((start[0] + t * dirs[i][0], start[1] + t * dirs[i][1]))
        elif kind[i] == 'raw':
            out.append((v[0] + d * prev_n[0], v[1] + d * prev_n[1]))
            out.append(start)
        else:
            out.append(start)
        # long edges get extra points, so a part that comes too close in the MIDDLE is seen
        w = poly[(i + 1) % n]
        back = trim[i][1] if kind[(i + 1) % n] == 'mitre' else 0.0     # stop at the next mitre point
        end = (w[0] + d * nx[0] - back * dirs[i][0], w[1] + d * nx[1] - back * dirs[i][1])
        a = out[-1]
        l = dist(a, end)
        k = int(l / max_step)
        for j in range(1, k + 1):
            f = j / float(k + 1)
            out.append((a[0] + f * (end[0] - a[0]), a[1] + f * (end[1] - a[1])))
    return dedupe(out, True, 1e-10)


def offset(poly, d, tol=FLATTEN_TOL):
    """Outlines at distance d from `poly` (counter-clockwise): outward for d > 0, inward for
    d < 0. Returns a list of outlines, largest first (inward offsets can split a shape, or
    give nothing when the shape is too thin)."""
    if abs(d) < 1e-9:
        return [list(poly)]
    raw = _raw_offset(poly, d, tol)
    n = len(raw)
    if n < 3:
        return []
    grid = _Grid(poly, max(abs(d), perimeter(poly) / max(len(poly), 1)))
    limit = abs(d) * (1.0 - 1e-9) - 1e-9          # raw points sit exactly at distance d: no slack needed
    valid = [not grid.closer_than(p, limit) for p in raw]
    if all(valid):
        loops = [raw]
    elif not any(valid):
        return []
    else:
        loops = _stitch(raw, valid)
    want = 1.0                                           # keep outlines that run counter-clockwise
    good = [dedupe(l, True, 1e-9) for l in loops]
    good = [l for l in good if len(l) >= 3 and area(l) * want > 1e-9]
    good.sort(key=lambda l: -abs(area(l)))
    return good


def _stitch(raw, valid):
    """Join the valid stretches of a raw offset at the points where they cross each other."""
    n = len(raw)
    # a lone valid point between bad ones is a leftover (it only touches the limit): not a stretch
    valid = [v and (valid[k - 1] or valid[(k + 1) % n]) for k, v in enumerate(valid)]
    if not any(valid):
        return []
    runs = []                                            # (first valid index, last valid index)
    i = 0
    while valid[i] and valid[i - 1]:                     # start the search just after a gap
        i += 1
        if i >= n:
            return [raw]
    k = i
    while k < i + n:
        if valid[k % n]:
            j = k
            while valid[(j + 1) % n] and j + 1 < i + n:
                j += 1
            runs.append((k % n, j % n))
            k = j + 1
        else:
            k += 1
    # every run leaves through the edge after its last point and is entered through the edge
    # before its first point; a leaving edge crosses the entering edge of the run that follows
    exits = [(raw[b], raw[(b + 1) % n]) for a, b in runs]
    entries = [(raw[a - 1], raw[a]) for a, b in runs]
    nxt, cross_pt = {}, {}
    for r, (p, q) in enumerate(exits):
        best = None
        for s, (c, e) in enumerate(entries):
            x = _seg_intersection(p, q, c, e)
            if x is not None:
                dd = dist(p, x)
                if s == r and dd < 1e-9:
                    continue                             # a one-point run: its two edges only share that point
                if best is None or dd < best[0]:
                    best = (dd, s, x)
        if best is None:
            # No crossing: the outline between the two stretches collapsed (e.g. an inside fillet
            # whose radius is the offset distance). Go on with the stretch that follows, through
            # the corner where the two directions meet if that is close, else straight across.
            s = (r + 1) % len(runs)
            a0, b0 = runs[r]
            a1, b1 = runs[s]
            x = None
            if a0 != b0 and a1 != b1:
                pa, pb = raw[b0 - 1], raw[b0]
                qa, qb = raw[(a1 + 1) % n], raw[a1]
                u = (pb[0] - pa[0], pb[1] - pa[1])
                w = (qb[0] - qa[0], qb[1] - qa[1])
                den = u[0] * w[1] - u[1] * w[0]
                gap = dist(pb, qb)
                lu, lw = hyp(u[0], u[1]), hyp(w[0], w[1])
                if abs(den) > 1e-12 * lu * lw:
                    t = ((qb[0] - pb[0]) * w[1] - (qb[1] - pb[1]) * w[0]) / den      # along u from pb
                    v = ((qb[0] - pb[0]) * u[1] - (qb[1] - pb[1]) * u[0]) / den      # along w from qb
                    if 0 <= t * lu <= 2 * gap and 0 <= v * lw <= 2 * gap:
                        x = (pb[0] + t * u[0], pb[1] + t * u[1])
            best = (0.0, s, x)
        elif dist(best[2], q) < 1e-9 and dist(best[2], entries[best[1]][0]) < 1e-9:
            best = (best[0], best[1], None)              # one bad point between two runs: drop it
        nxt[r], cross_pt[r] = best[1], best[2]
    loops, used = [], set()
    for r0 in range(len(runs)):
        if r0 in used:
            continue
        loop, r = [], r0
        while r not in used:
            used.add(r)
            a, b = runs[r]
            k = a
            while True:
                loop.append(raw[k])
                if k == b:
                    break
                k = (k + 1) % n
            if cross_pt[r] is not None:
                loop.append(cross_pt[r])
            r = nxt[r]
        if r == r0:
            loops.append(loop)
    return loops


def offset_one(poly, d, tol=FLATTEN_TOL):
    """The largest outline of offset(); raises GeometryError when nothing is left."""
    loops = offset(poly, d, tol)
    if not loops:
        raise GeometryError("The shape is too small or too thin: nothing is left %.3g mm %s the outline."
                            % (abs(d), "outside" if d > 0 else "inside"))
    return loops[0]


def round_corners(poly, r, tol=FLATTEN_TOL):
    """Replace sharp corners by arcs of radius r: outside corners (in + out), then inside
    corners (out + in). Parts narrower than 2 r are lost, so check the result's size."""
    if r <= 0:
        return list(poly)
    p = offset_one(offset_one(poly, -r, tol), r, tol)
    return offset_one(offset_one(p, r, tol), -r, tol)


# ------------------------------------------------------------------ points -> LIN / CIRC

def circle_through(a, b, c):
    """(centre, radius) of the circle through three points, or None if they are on a line."""
    ax, ay, bx, by, cx, cy = a[0], a[1], b[0], b[1], c[0], c[1]
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return None
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy), hyp(ax - ux, ay - uy)


def _line_ok(pts, i, j, tol):
    a, b = pts[i], pts[j]
    l = dist(a, b)
    if l < 1e-12:
        return False
    ux, uy = (b[0] - a[0]) / l, (b[1] - a[1]) / l
    for k in range(i + 1, j):
        px, py = pts[k][0] - a[0], pts[k][1] - a[1]
        if abs(px * uy - py * ux) > tol:
            return False
        s = px * ux + py * uy
        if s < -tol or s > l + tol:
            return False
    return True


def _arc_fit(pts, i, j, tol, max_sweep):
    """Arc through pts[i], a middle point and pts[j] if every point and every edge middle in
    between is within tol of it: (centre, radius, sweep in radians) or None."""
    if j - i < 2:
        return None
    cr = circle_through(pts[i], pts[(i + j) // 2], pts[j])
    if cr is None:
        return None
    (cx, cy), R = cr
    if R > 1e5:
        return None
    prev = math.atan2(pts[i][1] - cy, pts[i][0] - cx)
    total, sign = 0.0, 0
    for k in range(i + 1, j + 1):
        p = pts[k]
        if abs(hyp(p[0] - cx, p[1] - cy) - R) > tol:
            return None
        q = pts[k - 1]
        if abs(hyp((p[0] + q[0]) / 2 - cx, (p[1] + q[1]) / 2 - cy) - R) > tol:
            return None
        ang = math.atan2(p[1] - cy, p[0] - cx)
        step = (ang - prev + math.pi) % (2 * math.pi) - math.pi
        prev = ang
        if step == 0.0:
            continue
        s = 1 if step > 0 else -1
        if sign == 0:
            sign = s
        elif s != sign:
            return None
        total += step
    if sign == 0 or abs(total) > math.radians(max_sweep):
        return None
    return (cx, cy), R, total


def _furthest(ok, i, n):
    """Largest j (i < j < n) with ok(j), assuming ok is true up to some point and false after."""
    lo = i + 1
    if not ok(lo):
        return None
    step = 1
    hi = lo
    while True:
        nx = min(n - 1, hi + step)
        if nx == hi:
            return hi
        if ok(nx):
            hi = nx
            step *= 2
        else:
            lo, bad = hi, nx
            break
    while bad - lo > 1:
        mid = (lo + bad) // 2
        if ok(mid):
            lo = mid
        else:
            bad = mid
    return lo


def fit_moves(pts, tol=FIT_TOL, max_sweep=MAX_ARC_SWEEP):
    """Open list of points -> moves from pts[0]: ('L', end) or ('C', via, end, centre, radius).
    Every move ends ON one of the points, so the path stays connected."""
    pts = dedupe(pts, False, 1e-9)
    n = len(pts)
    moves = []
    i = 0
    while i < n - 1:
        jl = _furthest(lambda j: _line_ok(pts, i, j, tol), i, n) or i + 1
        ja = None
        if i + 2 < n:
            def arc_ok(j):
                if j < i + 2:
                    return True
                return _arc_fit(pts, i, j, tol, max_sweep) is not None
            ja = _furthest(arc_ok, i, n)
            if ja is not None and ja < i + 2:
                ja = None
        if ja is not None and ja > jl:
            (cx, cy), R, sweep = _arc_fit(pts, i, ja, tol, max_sweep)
            a0 = math.atan2(pts[i][1] - cy, pts[i][0] - cx)
            via = (cx + R * math.cos(a0 + sweep / 2), cy + R * math.sin(a0 + sweep / 2))
            moves.append(('C', via, pts[ja], (cx, cy), R))
            i = ja
        else:
            moves.append(('L', pts[jl]))
            i = jl
    return moves


# ------------------------------------------------------------------ loose pieces -> paths

def chain_segments(pieces, tol=0.01):
    """Join pieces (each a list of points) end to end where their ends meet within tol.
    Returns (closed outlines, open paths), each a list of point lists."""
    pieces = [dedupe(p, False, 1e-12) for p in pieces]
    pieces = [p for p in pieces if len(p) >= 2]
    cell = max(tol, 1e-9)
    ends = {}

    def key(p):
        return (int(math.floor(p[0] / cell)), int(math.floor(p[1] / cell)))

    def add(idx, which):
        ends.setdefault(key(pieces[idx][0 if which == 0 else -1]), []).append((idx, which))

    def find(p, skip):
        kx, ky = key(p)
        best = None
        for gx in (kx - 1, kx, kx + 1):
            for gy in (ky - 1, ky, ky + 1):
                for idx, which in ends.get((gx, gy), ()):
                    if idx in skip:
                        continue
                    q = pieces[idx][0 if which == 0 else -1]
                    dd = dist(p, q)
                    if dd <= tol and (best is None or dd < best[0]):
                        best = (dd, idx, which)
        return best
    for idx in range(len(pieces)):
        add(idx, 0)
        add(idx, 1)
    used = set()
    closed, opened = [], []
    for idx in range(len(pieces)):
        if idx in used:
            continue
        used.add(idx)
        path = list(pieces[idx])
        if dist(path[0], path[-1]) <= tol and len(path) > 2:
            closed.append(path[:-1])
            continue
        for at_end in (True, False):
            while True:
                p = path[-1] if at_end else path[0]
                hit = find(p, used)
                if hit is None:
                    break
                _, j, which = hit
                used.add(j)
                nxt = pieces[j] if which == 0 else pieces[j][::-1]      # starts at p
                if at_end:
                    path.extend(nxt[1:])
                else:
                    path = nxt[::-1][:-1] + path
                if dist(path[0], path[-1]) <= tol:
                    break
            if dist(path[0], path[-1]) <= tol and len(path) > 2:
                break
        if dist(path[0], path[-1]) <= tol and len(path) > 2:
            closed.append(path[:-1])
        else:
            opened.append(path)
    return closed, opened


def crosses_itself(poly, tol=0.01):
    """Does this closed path cross (or touch) itself, like a figure 8?"""
    pts = simplify(poly, tol)
    n = len(pts)
    if n < 4:
        return False
    segs = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        segs.append((min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1]), i, a, b))
    segs.sort(key=lambda g: g[0])
    for k, (x0, x1, y0, y1, i, a, b) in enumerate(segs):
        for x0b, x1b, y0b, y1b, j, c, e in segs[k + 1:]:
            if x0b > x1:
                break                                    # sorted by their left end: no later one can reach
            if y0b > y1 or y1b < y0:
                continue
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue                                 # neighbours only share their corner
            if _seg_intersection(a, b, c, e) is not None:
                return True
    return False


def _simplify_open(pts, tol):
    """Douglas-Peucker: the fewest of the given points so that every dropped point is within
    tol of the remaining line (first and last point are kept)."""
    n = len(pts)
    if n < 3:
        return list(pts)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        a, b = pts[i], pts[j]
        worst, at = -1.0, None
        for k in range(i + 1, j):
            dd = dist(pts[k], _closest_on_segment(pts[k], a, b)[0])
            if dd > worst:
                worst, at = dd, k
        if worst > tol:
            keep[at] = True
            stack.append((i, at))
            stack.append((at, j))
    return [q for q, kept in zip(pts, keep) if kept]


def simplify(poly, tol=1e-6):
    """Closed outline with the points dropped that are within tol of the line between the
    points that stay (so the shape moves by at most tol)."""
    pts = dedupe(poly, True, 1e-9)
    n = len(pts)
    if n <= 3:
        return pts
    far = max(range(n), key=lambda k: dist(pts[0], pts[k]))       # two fixed points: 0 and the farthest
    first = _simplify_open(pts[:far + 1], tol)
    second = _simplify_open(pts[far:] + [pts[0]], tol)
    out = first[:-1] + second[:-1]
    if len(out) >= 3:                                             # the start point may itself lie on a line
        a, q, b = out[-1], out[0], out[1]
        if dist(q, _closest_on_segment(q, a, b)[0]) <= tol:
            out = out[1:]
    return out if len(out) >= 3 else pts
