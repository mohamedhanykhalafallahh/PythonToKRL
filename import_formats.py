"""Design file readers for the free-form import (no tkinter, no extra libraries).

    load_design(path) -> Design

2D files give outlines (closed paths) in mm, Y pointing up:
    .svg   paths (lines, Bezier curves, arcs), rect, circle, ellipse, line, polyline, polygon,
           nested transforms; real units from width / height / viewBox (else 96 px per inch)
    .dxf   ASCII DXF: LINE, ARC, CIRCLE, LWPOLYLINE, POLYLINE (with bulges), ELLIPSE, SPLINE;
           loose pieces are joined into outlines; $INSUNITS (inch, mm, cm, m) is respected
3D files give a triangle mesh that is sliced layer by layer (slice_mesh):
    .stl   binary or ASCII

STEP (.stp / .step) holds exact CAD surfaces and needs a CAD kernel to read; it is not read
here. Export the part as STL (3D) or its profile as DXF (2D) from the CAD program instead.
"""
import math
import os
import re
import struct
import xml.etree.ElementTree as ET

import contours as ct

JOIN_TOL = 0.02          # mm: ends of DXF pieces / slice segments closer than this are joined
SLICE_TOL = 0.005        # mm: slice points this close to a straight line are dropped (STL numbers are single
                         # precision, and fine meshes give tiny zigzag edges that would upset the offset)
EXTENSIONS_2D = (".svg", ".dxf")
EXTENSIONS_3D = (".stl",)
FILETYPES = [("Design files", "*.svg *.dxf *.stl"), ("SVG drawing", "*.svg"), ("DXF drawing", "*.dxf"),
             ("STL mesh", "*.stl"), ("All files", "*.*")]


class ImportError_(ValueError):
    """The file cannot be used (the message is shown to the user)."""


class Design(object):
    """An imported design. kind '2d': `paths` = [(kind, points), ...] in the order of the
    "Outline no." field: 'outline' (closed, counter-clockwise, largest first), then 'crossing'
    (closed but crossing itself, e.g. an infinity shape; as drawn), then 'open' (as drawn).
    `outlines`, `crossing` and `open_paths` are the three groups on their own.
    kind '3d': `triangles` [((x,y,z), (x,y,z), (x,y,z)), ...] and `zmin` / `zmax`.
    `bounds` = (xmin, ymin, xmax, ymax) of everything; `notes` = remarks for the user."""

    def __init__(self, path, kind):
        self.path, self.kind = path, kind
        self.name = os.path.basename(path)
        self.outlines, self.crossing, self.open_paths, self.triangles, self.paths = [], [], [], [], []
        self.zmin = self.zmax = 0.0
        self.bounds = (0.0, 0.0, 0.0, 0.0)
        self.notes = []
        self._slices = {}

    @property
    def centre(self):
        b = self.bounds
        return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)

    @property
    def size(self):
        b = self.bounds
        return (b[2] - b[0], b[3] - b[1])

    @property
    def height(self):
        return self.zmax - self.zmin

    def describe(self):
        w, h = self.size
        if self.kind == "3d":
            return "%d triangles, %.1f x %.1f x %.1f mm" % (len(self.triangles), w, h, self.height)
        parts = []
        for group, one, many in ((self.outlines, "closed outline", "closed outlines"),
                                 (self.crossing, "self-crossing path", "self-crossing paths"),
                                 (self.open_paths, "open path", "open paths")):
            if group:
                parts.append("%d %s" % (len(group), one if len(group) == 1 else many))
        return "%s, %.1f x %.1f mm" % (" + ".join(parts), w, h)


def load_design(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".stp", ".step", ".igs", ".iges"):
        raise ImportError_("STEP / IGES files hold exact CAD surfaces and cannot be read directly.\n\n"
                           "In the CAD program, export the part as STL (3D shape, sliced layer by layer here) "
                           "or its profile as DXF (2D outline), and import that file.")
    if not os.path.exists(path):
        raise ImportError_("The design file was not found:\n%s" % path)
    try:
        if ext == ".svg":
            return _finish_2d(Design(path, "2d"), *load_svg(path))
        if ext == ".dxf":
            return _finish_2d(Design(path, "2d"), *load_dxf(path))
        if ext == ".stl":
            return _finish_3d(Design(path, "3d"), load_stl(path))
    except ImportError_:
        raise
    except (OSError, ValueError, KeyError, IndexError, struct.error, ET.ParseError) as ex:
        raise ImportError_("Could not read %s:\n%s" % (os.path.basename(path), ex))
    raise ImportError_("Unknown file type '%s'. Supported: SVG, DXF (2D outlines) and STL (3D)." % ext)


def _path_length(pts):
    return math.fsum(ct.dist(p, q) for p, q in zip(pts, pts[1:]))


def _finish_2d(design, pieces, notes):
    closed, opened = ct.chain_segments(pieces, JOIN_TOL)
    outlines, crossing = [], []
    for c in closed:
        c = ct.simplify(c, 1e-7)
        if len(c) < 3:
            continue
        if ct.crosses_itself(c):
            crossing.append(c)                           # kept as drawn (direction and start)
        elif abs(ct.area(c)) > 1e-6:
            outlines.append(ct.normalize(c))
    outlines.sort(key=lambda o: -ct.area(o))
    crossing.sort(key=lambda o: -_path_length(o + [o[0]]))
    opened = [o for o in (ct.dedupe(o, False, 1e-9) for o in opened) if len(o) >= 2 and _path_length(o) >= 1.0]
    opened.sort(key=lambda o: -_path_length(o))
    design.outlines, design.crossing, design.open_paths, design.notes = outlines, crossing, opened, list(notes)
    design.paths = [("outline", o) for o in outlines] + [("crossing", o) for o in crossing] + \
        [("open", o) for o in opened]
    pts = [q for _, o in design.paths for q in o]
    if not pts:
        raise ImportError_("No drawing was found in %s (no lines, curves or shapes that can be read)." % design.name)
    design.bounds = ct.bounds(pts)
    return design


def _finish_3d(design, triangles):
    if not triangles:
        raise ImportError_("%s has no triangles." % design.name)
    design.triangles = triangles
    xs = [v[0] for t in triangles for v in t]
    ys = [v[1] for t in triangles for v in t]
    zs = [v[2] for t in triangles for v in t]
    design.bounds = (min(xs), min(ys), max(xs), max(ys))
    design.zmin, design.zmax = min(zs), max(zs)
    if design.height <= 1e-9:
        raise ImportError_("%s is flat (no height): nothing to slice." % design.name)
    return design


# ====================================================================== SVG

_UNIT_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72.0, "pc": 25.4 / 6.0, "px": 25.4 / 96.0, "": 25.4 / 96.0}
_LEN_RE = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([a-zA-Z%]*)\s*$")
_NUM_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_PATH_RE = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")
_TRANSFORM_RE = re.compile(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)")
_SKIP_TAGS = ("defs", "clipPath", "mask", "pattern", "symbol", "marker", "metadata", "style", "title", "desc",
              "text", "image", "filter", "linearGradient", "radialGradient")


def _length(text, default=None):
    """SVG length -> (value, unit) or default."""
    m = _LEN_RE.match(text or "")
    return (float(m.group(1)), m.group(2).lower()) if m else default


def _mat_mul(a, b):
    """Affine matrices (a, b, c, d, e, f): the result applies b first, then a."""
    return (a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
            a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
            a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5])


def _mat_apply(m, p):
    return (m[0] * p[0] + m[2] * p[1] + m[4], m[1] * p[0] + m[3] * p[1] + m[5])


def _parse_transform(text):
    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for name, args in _TRANSFORM_RE.findall(text or ""):
        v = [float(x) for x in _NUM_RE.findall(args)]
        if name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "translate" and v:
            t = (1.0, 0.0, 0.0, 1.0, v[0], v[1] if len(v) > 1 else 0.0)
        elif name == "scale" and v:
            t = (v[0], 0.0, 0.0, v[1] if len(v) > 1 else v[0], 0.0, 0.0)
        elif name == "rotate" and v:
            c, s = math.cos(math.radians(v[0])), math.sin(math.radians(v[0]))
            t = (c, s, -s, c, 0.0, 0.0)
            if len(v) == 3:
                t = _mat_mul(_mat_mul((1.0, 0.0, 0.0, 1.0, v[1], v[2]), t), (1.0, 0.0, 0.0, 1.0, -v[1], -v[2]))
        elif name == "skewX" and v:
            t = (1.0, 0.0, math.tan(math.radians(v[0])), 1.0, 0.0, 0.0)
        elif name == "skewY" and v:
            t = (1.0, math.tan(math.radians(v[0])), 0.0, 1.0, 0.0, 0.0)
        else:
            continue
        m = _mat_mul(m, t)
    return m


def _svg_arc(p0, rx, ry, phi_deg, large, sweep, p1, tol):
    """Points of an SVG elliptical arc from p0 to p1 (without p0)."""
    if rx == 0 or ry == 0 or (abs(p0[0] - p1[0]) < 1e-12 and abs(p0[1] - p1[1]) < 1e-12):
        return [p1]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(phi_deg)
    c, s = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2.0, (p0[1] - p1[1]) / 2.0
    x1, y1 = c * dx + s * dy, -s * dx + c * dy
    lam = (x1 / rx) ** 2 + (y1 / ry) ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    k = math.sqrt(max(0.0, num / den)) * (-1 if bool(large) == bool(sweep) else 1)
    cxp, cyp = k * rx * y1 / ry, -k * ry * x1 / rx
    cx, cy = c * cxp - s * cyp + (p0[0] + p1[0]) / 2.0, s * cxp + c * cyp + (p0[1] + p1[1]) / 2.0
    a0 = math.atan2((y1 - cyp) / ry, (x1 - cxp) / rx)
    a1 = math.atan2((-y1 - cyp) / ry, (-x1 - cxp) / rx)
    d = a1 - a0
    if sweep and d < 0:
        d += 2 * math.pi
    elif not sweep and d > 0:
        d -= 2 * math.pi
    n = ct._arc_steps(max(rx, ry), d, tol)
    out = []
    for i in range(1, n + 1):
        a = a0 + d * i / n
        ex, ey = rx * math.cos(a), ry * math.sin(a)
        out.append((c * ex - s * ey + cx, s * ex + c * ey + cy))
    out[-1] = p1
    return out


def _svg_path(d, tol):
    """SVG path data -> list of sub-paths (point lists; a closed one repeats its first point)."""
    tokens = _PATH_RE.findall(d or "")
    subs, cur = [], []
    pos, start = (0.0, 0.0), (0.0, 0.0)
    cmd, last_ctrl, last_cmd = None, None, None
    i = 0

    def nums(n):
        nonlocal i
        vals = []
        for _ in range(n):
            if i >= len(tokens) or not tokens[i][1]:
                raise ValueError("bad path data")
            vals.append(float(tokens[i][1]))
            i += 1
        return vals
    while i < len(tokens):
        if tokens[i][0]:
            cmd = tokens[i][0]
            i += 1
            if cmd in "Zz":
                if cur:
                    cur.append(start)
                    subs.append(cur)
                    cur = []
                pos = start
                last_cmd = "Z"
                continue
        elif cmd is None:
            raise ValueError("bad path data")
        elif cmd in "Zz":
            raise ValueError("bad path data")
        rel = cmd.islower()
        c = cmd.upper()
        ox, oy = pos if rel else (0.0, 0.0)
        if c != "M" and not cur:
            cur = [pos]                               # drawing goes on after a 'Z' without a new 'M'
        if c == "M":
            x, y = nums(2)
            if len(cur) > 1:
                subs.append(cur)
            pos = start = (ox + x, oy + y)
            cur = [pos]
            cmd = "l" if rel else "L"                 # further pairs are line-tos
        elif c == "L":
            x, y = nums(2)
            pos = (ox + x, oy + y)
            cur.append(pos)
        elif c == "H":
            x, = nums(1)
            pos = ((pos[0] if rel else 0.0) + x, pos[1])
            cur.append(pos)
        elif c == "V":
            y, = nums(1)
            pos = (pos[0], (pos[1] if rel else 0.0) + y)
            cur.append(pos)
        elif c in "CS":
            if c == "C":
                x1, y1, x2, y2, x, y = nums(6)
                c1 = (ox + x1, oy + y1)
            else:
                x2, y2, x, y = nums(4)
                c1 = (2 * pos[0] - last_ctrl[0], 2 * pos[1] - last_ctrl[1]) if last_cmd in ("C", "S") else pos
            c2, end = (ox + x2, oy + y2), (ox + x, oy + y)
            cur.extend(ct.flatten_bezier([pos, c1, c2, end], tol, include_start=False))
            last_ctrl, pos = c2, end
        elif c in "QT":
            if c == "Q":
                x1, y1, x, y = nums(4)
                c1 = (ox + x1, oy + y1)
            else:
                x, y = nums(2)
                c1 = (2 * pos[0] - last_ctrl[0], 2 * pos[1] - last_ctrl[1]) if last_cmd in ("Q", "T") else pos
            end = (ox + x, oy + y)
            cur.extend(ct.flatten_bezier([pos, c1, end], tol, include_start=False))
            last_ctrl, pos = c1, end
        elif c == "A":
            rx, ry, phi, large, sweep, x, y = nums(7)
            end = (ox + x, oy + y)
            cur.extend(_svg_arc(pos, rx, ry, phi, large, sweep, end, tol))
            pos = end
        last_cmd = c
    if len(cur) > 1:
        subs.append(cur)
    return subs


def _svg_shape(tag, a, tol):
    """Basic shapes -> sub-paths in the element's own coordinates."""
    f = lambda k, d=0.0: float(_length(a.get(k), (d, ""))[0])
    if tag == "path":
        return _svg_path(a.get("d", ""), tol)
    if tag == "rect":
        x, y, w, h = f("x"), f("y"), f("width"), f("height")
        if w <= 0 or h <= 0:
            return []
        rx = f("rx", -1.0) if a.get("rx") else None
        ry = f("ry", -1.0) if a.get("ry") else None
        rx = ry if rx is None else rx
        ry = rx if ry is None else ry
        rx, ry = min(rx or 0.0, w / 2.0), min(ry or 0.0, h / 2.0)
        if rx <= 0 or ry <= 0:
            return [[(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]]
        d = "M %r %r H %r A %r %r 0 0 1 %r %r V %r A %r %r 0 0 1 %r %r H %r A %r %r 0 0 1 %r %r V %r A %r %r 0 0 1 %r %r Z" % (
            x + rx, y, x + w - rx, rx, ry, x + w, y + ry, y + h - ry, rx, ry, x + w - rx, y + h,
            x + rx, rx, ry, x, y + h - ry, y + ry, rx, ry, x + rx, y)
        return _svg_path(d, tol)
    if tag in ("circle", "ellipse"):
        cx, cy = f("cx"), f("cy")
        rx, ry = (f("r"), f("r")) if tag == "circle" else (f("rx"), f("ry"))
        if rx <= 0 or ry <= 0:
            return []
        n = max(8, ct._arc_steps(max(rx, ry), 2 * math.pi, tol))
        pts = [(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n)) for k in range(n)]
        return [pts + [pts[0]]]
    if tag == "line":
        return [[(f("x1"), f("y1")), (f("x2"), f("y2"))]]
    if tag in ("polyline", "polygon"):
        v = [float(x) for x in _NUM_RE.findall(a.get("points", ""))]
        pts = list(zip(v[0::2], v[1::2]))
        if len(pts) < 2:
            return []
        return [pts + [pts[0]]] if tag == "polygon" else [pts]
    return []


def load_svg(path, tol=ct.FLATTEN_TOL):
    """-> (pieces in mm with Y up, notes)."""
    root = ET.parse(path).getroot()
    if root.tag.split("}")[-1] != "svg":
        raise ImportError_("%s is not an SVG drawing." % os.path.basename(path))
    notes = []
    # user units -> mm: from width / height (with units) and the viewBox
    vb = [float(x) for x in _NUM_RE.findall(root.get("viewBox", ""))]
    w = _length(root.get("width"))
    h = _length(root.get("height"))
    sx = sy = _UNIT_MM["px"]
    base = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    if len(vb) == 4 and vb[2] > 0 and vb[3] > 0:
        if w and w[1] in _UNIT_MM and h and h[1] in _UNIT_MM:
            sx, sy = w[0] * _UNIT_MM[w[1]] / vb[2], h[0] * _UNIT_MM[h[1]] / vb[3]
        base = (1.0, 0.0, 0.0, 1.0, -vb[0], -vb[1])
    if not (w and w[1] in ("mm", "cm", "in")):
        notes.append("The SVG gives no real size (mm): 96 px per inch was assumed. Check the size, "
                     "and use Scale if it is wrong.")
    pieces, skipped = [], set()

    def walk(el, m):
        tag = el.tag.split("}")[-1] if isinstance(el.tag, str) else ""
        if tag in _SKIP_TAGS:
            return
        if el.get("display") == "none" or "display:none" in (el.get("style") or "").replace(" ", ""):
            return
        m = _mat_mul(m, _parse_transform(el.get("transform")))
        if tag in ("path", "rect", "circle", "ellipse", "line", "polyline", "polygon"):
            scale = math.sqrt(abs(m[0] * m[3] - m[1] * m[2])) * max(sx, sy)
            local_tol = tol / scale if scale > 1e-12 else tol
            for sub in _svg_shape(tag, el.attrib, local_tol):
                pts = [_mat_apply(m, p) for p in sub]
                pieces.append([(x * sx, -y * sy) for x, y in pts])       # mm, Y up
        elif tag == "use":
            skipped.add("<use> (copies of other shapes)")
        for child in el:
            walk(child, m)
    walk(root, base)
    if skipped:
        notes.append("Not read: %s." % ", ".join(sorted(skipped)))
    return pieces, notes


# ====================================================================== DXF

_INSUNITS_MM = {1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0}


def _dxf_pairs(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"AutoCAD Binary DXF"):
        raise ImportError_("This is a BINARY DXF. Save it as an ASCII (text) DXF in the drawing program.")
    text = raw.decode("utf-8", "replace") if b"\x00" not in raw[:200] else raw.decode("utf-16", "replace")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    pairs = []
    for k in range(0, len(lines) - 1, 2):
        try:
            pairs.append((int(lines[k].strip()), lines[k + 1].strip()))
        except ValueError:
            if lines[k].strip():
                raise ImportError_("This does not look like an ASCII DXF file (line %d)." % (k + 1))
    return pairs


def _bulge_points(p0, p1, bulge, tol):
    """Points of a polyline segment with a bulge (without p0)."""
    if abs(bulge) < 1e-12:
        return [p1]
    chord = ct.dist(p0, p1)
    if chord < 1e-12:
        return [p1]
    theta = 4.0 * math.atan(bulge)                       # included angle, + = counter-clockwise
    r = chord / (2.0 * math.sin(abs(theta) / 2.0))
    mx, my = (p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0
    h = r * math.cos(abs(theta) / 2.0)                   # centre to chord (signed by the bulge side)
    ux, uy = (p1[0] - p0[0]) / chord, (p1[1] - p0[1]) / chord
    sgn = 1.0 if bulge > 0 else -1.0
    cx, cy = mx - sgn * h * uy, my + sgn * h * ux
    a0 = math.atan2(p0[1] - cy, p0[0] - cx)
    pts = ct.flatten_arc((cx, cy), r, a0, theta, tol, include_start=False)
    pts[-1] = p1
    return pts


def _bspline(degree, knots, ctrl, weights, tol):
    """Points of a (rational) B-spline by de Boor's algorithm."""
    n = len(ctrl)
    if n < 2:
        return list(ctrl)
    if len(knots) != n + degree + 1 or degree < 1:
        return list(ctrl)
    w = weights if len(weights) == n else [1.0] * n
    t0, t1 = knots[degree], knots[n]
    length = math.fsum(ct.dist(ctrl[i], ctrl[i + 1]) for i in range(n - 1))
    steps = max(8, min(20000, int(length / max(math.sqrt(8 * tol * max(length / n, 1e-9)), 1e-6)), 200 * n))

    def point(t):
        k = degree
        while k < n - 1 and t >= knots[k + 1]:
            k += 1
        d = [(ctrl[j + k - degree][0] * w[j + k - degree], ctrl[j + k - degree][1] * w[j + k - degree],
              w[j + k - degree]) for j in range(degree + 1)]
        for r in range(1, degree + 1):
            for j in range(degree, r - 1, -1):
                i = j + k - degree
                den = knots[i + degree - r + 1] - knots[i]
                a = 0.0 if den == 0 else (t - knots[i]) / den
                d[j] = tuple((1 - a) * d[j - 1][c] + a * d[j][c] for c in range(3))
        return (d[degree][0] / d[degree][2], d[degree][1] / d[degree][2])
    return [point(t0 + (t1 - t0) * s / steps) for s in range(steps + 1)]


def load_dxf(path, tol=ct.FLATTEN_TOL):
    """-> (pieces in mm, notes)."""
    pairs = _dxf_pairs(path)
    notes = []
    unit = 1.0
    for i, (code, val) in enumerate(pairs):
        if code == 9 and val == "$INSUNITS" and i + 1 < len(pairs):
            try:
                u = int(float(pairs[i + 1][1]))
            except ValueError:
                u = 0
            if u in _INSUNITS_MM:
                unit = _INSUNITS_MM[u]
            elif u != 0:
                notes.append("Unusual drawing unit (INSUNITS %d): the numbers were read as mm." % u)
            break
    # entities of the ENTITIES section only (blocks are not placed)
    start = None
    for i in range(len(pairs) - 1):
        if pairs[i] == (0, "SECTION") and pairs[i + 1] == (2, "ENTITIES"):
            start = i + 2
            break
    if start is None:
        raise ImportError_("The DXF has no ENTITIES section.")
    entities, cur = [], None
    for code, val in pairs[start:]:
        if code == 0:
            if val == "ENDSEC":
                break
            cur = (val, [])
            entities.append(cur)
        elif cur is not None:
            cur[1].append((code, val))
    pieces, skipped = [], {}
    poly, poly_closed = None, False

    def first(data, code, default=0.0):
        for c, v in data:
            if c == code:
                return float(v)
        return default

    def close_poly(verts, closed):
        if len(verts) < 2:
            return
        pts = [verts[0][0]]
        seq = verts + ([verts[0]] if closed else [])
        for k in range(len(seq) - 1):
            pts.extend(_bulge_points(seq[k][0], seq[k + 1][0], seq[k][1], tol / unit))
        pieces.append(pts)
    for name, data in entities:
        if name == "LINE":
            pieces.append([(first(data, 10), first(data, 20)), (first(data, 11), first(data, 21))])
        elif name == "CIRCLE":
            pts = ct.flatten_arc((first(data, 10), first(data, 20)), first(data, 40), 0.0, 2 * math.pi, tol / unit)
            pieces.append(pts[:-1] + [pts[0]])
        elif name == "ARC":
            a0, a1 = math.radians(first(data, 50)), math.radians(first(data, 51))
            sweep = (a1 - a0) % (2 * math.pi) or 2 * math.pi
            pieces.append(ct.flatten_arc((first(data, 10), first(data, 20)), first(data, 40), a0, sweep, tol / unit))
        elif name == "LWPOLYLINE":
            verts, closed = [], int(first(data, 70)) & 1
            for c, v in data:
                if c == 10:
                    verts.append([(float(v), 0.0), 0.0])
                elif c == 20 and verts:
                    verts[-1][0] = (verts[-1][0][0], float(v))
                elif c == 42 and verts:
                    verts[-1][1] = float(v)
            close_poly(verts, closed)
        elif name == "POLYLINE":
            poly, poly_closed = [], int(first(data, 70)) & 1
        elif name == "VERTEX" and poly is not None:
            poly.append([(first(data, 10), first(data, 20)), first(data, 42)])
        elif name == "SEQEND" and poly is not None:
            close_poly(poly, poly_closed)
            poly = None
        elif name == "ELLIPSE":
            cx, cy = first(data, 10), first(data, 20)
            mx, my = first(data, 11), first(data, 21)
            ratio = first(data, 40, 1.0)
            t0, t1 = first(data, 41, 0.0), first(data, 42, 2 * math.pi)
            sweep = (t1 - t0) % (2 * math.pi) or 2 * math.pi
            a = ct.hyp(mx, my)
            n = max(8, ct._arc_steps(a, sweep, tol / unit))
            pts = []
            for k in range(n + 1):
                t = t0 + sweep * k / n
                pts.append((cx + mx * math.cos(t) - my * ratio * math.sin(t),
                            cy + my * math.cos(t) + mx * ratio * math.sin(t)))
            if abs(sweep - 2 * math.pi) < 1e-9:
                pts[-1] = pts[0]
            pieces.append(pts)
        elif name == "SPLINE":
            degree = int(first(data, 71, 3))
            knots = [float(v) for c, v in data if c == 40]
            weights = [float(v) for c, v in data if c == 41]
            xs = [float(v) for c, v in data if c == 10]
            ys = [float(v) for c, v in data if c == 20]
            ctrl = list(zip(xs, ys))
            if len(ctrl) >= 2 and len(knots) == len(ctrl) + degree + 1:
                pts = _bspline(degree, knots, ctrl, weights, tol / unit)
                if int(first(data, 70)) & 1 and ct.dist(pts[0], pts[-1]) < 1e-6:
                    pts[-1] = pts[0]
                pieces.append(pts)
            else:
                fit = list(zip([float(v) for c, v in data if c == 11], [float(v) for c, v in data if c == 21]))
                if len(fit) >= 2:
                    pieces.append(fit)
                    notes.append("A spline had only fit points: it was read as straight pieces between them.")
                else:
                    skipped["SPLINE (no data)"] = skipped.get("SPLINE (no data)", 0) + 1
        elif name in ("INSERT", "HATCH", "3DFACE", "SOLID", "REGION", "3DSOLID", "MESH"):
            skipped[name] = skipped.get(name, 0) + 1
    if skipped:
        notes.append("Not read: %s. (Explode blocks in the drawing program if the outline is inside one.)"
                     % ", ".join("%d x %s" % (n, k) for k, n in sorted(skipped.items())))
    if unit != 1.0:
        pieces = [[(x * unit, y * unit) for x, y in p] for p in pieces]
        notes.append("The drawing unit was converted to mm (x %g)." % unit)
    return pieces, notes


# ====================================================================== STL

def load_stl(path):
    """-> list of triangles ((x, y, z), (x, y, z), (x, y, z))."""
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) >= 84:
        n = struct.unpack_from("<I", raw, 80)[0]
        if len(raw) == 84 + 50 * n:                      # binary STL (the size matches exactly)
            tris = []
            for k in range(n):
                v = struct.unpack_from("<9f", raw, 84 + 50 * k + 12)
                tris.append((v[0:3], v[3:6], v[6:9]))
            return tris
    text = raw.decode("ascii", "replace")
    if "facet" not in text:
        raise ImportError_("This is not a valid STL file (neither binary nor ASCII).")
    nums = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", text)
    verts = [(float(a), float(b), float(c)) for a, b, c in nums]
    return [(verts[k], verts[k + 1], verts[k + 2]) for k in range(0, len(verts) - 2, 3)]


def slice_mesh(design, heights):
    """Cut the mesh at the given heights (measured from its lowest point). Returns one list of
    closed outlines (counter-clockwise, largest first) per height; an empty list where the
    cut gives no closed outline. Results are remembered in the design."""
    todo = [h for h in heights if round(h, 6) not in design._slices]
    if todo:
        zs = [design.zmin + h for h in todo]
        order = sorted(range(len(zs)), key=lambda k: zs[k])
        sorted_z = [zs[k] for k in order]
        segs = [[] for _ in zs]
        import bisect
        for tri in design.triangles:
            tz = (tri[0][2], tri[1][2], tri[2][2])
            lo, hi = min(tz), max(tz)
            if lo == hi:
                continue
            for pos in range(bisect.bisect_left(sorted_z, lo), bisect.bisect_right(sorted_z, hi)):
                z = sorted_z[pos]
                pts = []
                for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                    za, zb = a[2] - z, b[2] - z
                    if (za < 0) != (zb < 0):             # this edge crosses the cutting height
                        t = za / (za - zb)
                        pts.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
                if len(pts) == 2 and ct.dist(pts[0], pts[1]) > 1e-9:
                    segs[order[pos]].append(pts)
        for k, h in enumerate(todo):
            closed, _ = ct.chain_segments(segs[k], JOIN_TOL)
            loops = []
            for c in closed:
                c = ct.simplify(c, SLICE_TOL)
                if len(c) >= 3 and abs(ct.area(c)) > 1e-6:
                    loops.append(ct.normalize(c))
            loops.sort(key=lambda o: -ct.area(o))
            design._slices[round(h, 6)] = loops
    return [design._slices[round(h, 6)] for h in heights]
