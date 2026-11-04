"""Path model shared by the PythonToKRL generators (no tkinter).

A program body is a list of items, one per line:
    Ptp / Lin / Circ   motion lines,
    Comment            '; text' lines (layer / turn / transition markers, user comments),
    Raw                any other line, kept exactly as it is (header lines, hand edits).

    to_krl(item), program_to_krl(items)   model -> KRL text (the ONLY place lines are formatted)
    parse_krl(text)                       KRL text -> model
    path_3d(items)                        model -> 3D polyline per move (for views and checks)

Number format: every value is written with fmt() (str of the float, full precision).
Rounding of the output is a deliberate change made here, nowhere else.
"""
import math
import re
from dataclasses import dataclass
from typing import Optional

# ------------------------------------------------------------------ formatting

def fmt(v):
    """Coordinates and angles: full precision, always written as a float ('180.0')."""
    return str(float(v))


def fmt_st(v):
    """Status / Turn: integer with a trailing dot, as the app always wrote ('S 2., T 43.')."""
    return "{}.".format(int(v))


_POSE_KEYS = ("X", "Y", "Z", "A", "B", "C", "S", "T")


@dataclass
class Pose:
    """A KRL POS/FRAME aggregate. Missing components are None and not written."""
    x: float
    y: float
    z: float
    a: Optional[float] = None
    b: Optional[float] = None
    c: Optional[float] = None
    s: Optional[float] = None
    t: Optional[float] = None

    @property
    def xyz(self):
        return (self.x, self.y, self.z)

    def to_krl(self):
        parts = []
        for key in _POSE_KEYS:
            v = getattr(self, key.lower())
            if v is not None:
                parts.append("{} {}".format(key, fmt_st(v) if key in "ST" else fmt(v)))
        return "{" + ", ".join(parts) + "}"


def pose(xyz, abc=None, s=None, t=None):
    """Pose from a point (x, y, z) and optional orientation (a, b, c)."""
    a, b, c = abc if abc is not None else (None, None, None)
    return Pose(xyz[0], xyz[1], xyz[2], a, b, c, s, t)


def _tail(approx, note):
    out = (" " + approx) if approx else ""
    if note is not None:
        out += " ;" + note
    return out


@dataclass
class Ptp:
    target: Pose
    approx: Optional[str] = None      # e.g. "C_PTP"
    note: Optional[str] = None        # trailing ';' comment (text after the ';')

    def to_krl(self):
        return "PTP " + self.target.to_krl() + _tail(self.approx, self.note)


@dataclass
class Lin:
    target: Pose
    approx: Optional[str] = None      # e.g. "C_DIS"
    note: Optional[str] = None

    def to_krl(self):
        return "LIN " + self.target.to_krl() + _tail(self.approx, self.note)


@dataclass
class Circ:
    via: Pose                         # auxiliary point (only X, Y, Z are written)
    target: Pose
    approx: Optional[str] = None
    note: Optional[str] = None

    def to_krl(self):
        return "CIRC " + self.via.to_krl() + "," + self.target.to_krl() + _tail(self.approx, self.note)


@dataclass
class Comment:
    text: str                         # written as '; ' + text

    def to_krl(self):
        return "; " + self.text


@dataclass
class Raw:
    text: str                         # written exactly as it is

    def to_krl(self):
        return self.text


MOTIONS = (Ptp, Lin, Circ)


def to_krl(item):
    return item.to_krl()


def program_to_krl(items):
    """Items -> text, one line per item, joined with '\\n' (no trailing newline added)."""
    return "\n".join(i.to_krl() for i in items)


# ------------------------------------------------------------------ parsing

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_FIELD_RE = re.compile(r"\s*([A-Za-z])\s+(" + _NUM + r")\s*")
_TAIL_RE = re.compile(r"^\s*(C_DIS|C_PTP|C_VEL|C_ORI)?\s*(?:;(.*))?$", re.IGNORECASE)
_MOVE_RE = re.compile(r"^(PTP|LIN|CIRC)\s*(\{[^}]*\})(?:\s*,\s*(\{[^}]*\}))?(.*)$", re.IGNORECASE)


def _parse_pose(braced):
    """'{X 1, Y 2, ...}' -> Pose, or None if it is not a plain X/Y/Z(/A/B/C/S/T) aggregate."""
    vals = {}
    for part in braced[1:-1].split(","):
        m = _FIELD_RE.fullmatch(part)
        if not m:
            return None
        key = m.group(1).upper()
        if key not in _POSE_KEYS or key in vals:
            return None
        vals[key] = float(m.group(2))
    if not all(k in vals for k in "XYZ"):
        return None
    return Pose(*(vals.get(k) for k in _POSE_KEYS))


def parse_line(line):
    """One KRL line -> item. Anything not understood is kept as Raw (unchanged)."""
    if line.startswith("; "):
        return Comment(line[2:])
    m = _MOVE_RE.match(line)
    if not m:
        return Raw(line)
    kind, p1, p2, rest = m.groups()
    kind = kind.upper()
    tail = _TAIL_RE.match(rest)
    if not tail:
        return Raw(line)
    approx, note = tail.group(1), tail.group(2)
    approx = approx.upper() if approx else None
    a, b = _parse_pose(p1), (_parse_pose(p2) if p2 else None)
    if a is None or (p2 and b is None):
        return Raw(line)
    if kind == "CIRC":
        if b is None:
            return Raw(line)
        return Circ(a, b, approx, note)
    if b is not None:
        return Raw(line)
    return (Ptp if kind == "PTP" else Lin)(a, approx, note)


def parse_krl(text):
    """KRL text -> list of items (one per line). program_to_krl(parse_krl(t)) == t for
    everything this app writes."""
    return [parse_line(line) for line in text.split("\n")]


# ------------------------------------------------------------------ 3D geometry

def _v_sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _v_add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _v_mul(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def _v_dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _v_cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def arc_points_3d(p1, pv, p2, step_deg=5.0):
    """Points along the circular arc p1 -> pv -> p2 in 3D (what a KUKA CIRC does).
    Falls back to the straight polyline if the three points are collinear."""
    a, b = _v_sub(p1, p2), _v_sub(pv, p2)
    axb = _v_cross(a, b)
    n2 = _v_dot(axb, axb)
    if n2 < 1e-12:
        return [p1, pv, p2]
    # circumcentre of the triangle (p2 as origin)
    c = _v_add(p2, _v_mul(_v_cross(_v_sub(_v_mul(b, _v_dot(a, a)), _v_mul(a, _v_dot(b, b))), axb), 1.0 / (2 * n2)))
    r_vec = _v_sub(p1, c)
    R = math.sqrt(_v_dot(r_vec, r_vec))
    e1 = _v_mul(r_vec, 1.0 / R)
    nhat = _v_mul(axb, 1.0 / math.sqrt(n2))
    e2 = _v_cross(nhat, e1)
    two_pi = 2 * math.pi
    def ang(q):
        d = _v_sub(q, c)
        return math.atan2(_v_dot(d, e2), _v_dot(d, e1)) % two_pi
    av, a2 = ang(pv), ang(p2)
    sweep = a2 if av <= a2 else -(two_pi - a2)       # go the way that passes the via point
    n = max(4, int(abs(math.degrees(sweep)) / step_deg))
    pts = []
    for k in range(n + 1):
        t = sweep * k / n
        pts.append(_v_add(c, _v_add(_v_mul(e1, R * math.cos(t)), _v_mul(e2, R * math.sin(t)))))
    pts[-1] = p2
    return pts


_LAYER_RE = re.compile(r";\s*=+\s*LAYER\s+(\d+)")
_N_MOVES_RE = re.compile(r"\((\d+)\s+moves?\)")


def path_3d(items):
    """Items -> (start_point, moves) with moves as
    {'kind': 'LIN'/'CIRC', 'pts': [(x,y,z), ...], 'layer': n, 'transition': bool}.

    Layers come from '; ===== LAYER n' comments. Moves after a comment containing
    'TRANSITION' are transition moves up to and including the first CIRC, or exactly the
    next n moves if the comment says '(n moves)' (e.g. a lane change made of two arcs)."""
    moves, pos, start = [], None, None
    layer, in_transition = 0, False
    n_left = None                                   # moves left in a '(n moves)' transition
    for item in items:
        if isinstance(item, Raw) and item.text.strip() != item.text:
            item = parse_line(item.text.strip())     # hand-indented line: still show it
        if isinstance(item, (Comment, Raw)):
            line = item.to_krl().strip()
            if line.startswith(";"):
                m = _LAYER_RE.match(line)
                if m:
                    layer = int(m.group(1))
                if "TRANSITION" in line:
                    in_transition = True
                    m = _N_MOVES_RE.search(line)
                    n_left = int(m.group(1)) if m else None
            continue
        if isinstance(item, Ptp):
            pos = item.target.xyz
            if start is None:
                start = pos
            continue
        if isinstance(item, Lin) and pos is not None:
            p = item.target.xyz
            moves.append({'kind': 'LIN', 'pts': [pos, p], 'layer': layer, 'transition': in_transition})
            pos = p
        elif isinstance(item, Circ) and pos is not None:
            p2 = item.target.xyz
            moves.append({'kind': 'CIRC', 'pts': arc_points_3d(pos, item.via.xyz, p2), 'layer': layer,
                          'transition': in_transition})
            pos = p2
            if n_left is None:
                in_transition = False   # a transition ends with (at most) one CIRC ...
        else:
            continue
        if n_left is not None:
            n_left -= 1
            if n_left <= 0:
                in_transition, n_left = False, None
    # ... except the inward kind, which is CIRC + a short straight LIN into P1. That LIN is
    # followed by the turn's own LIN in the same direction (two LINs in a row never happen
    # inside a turn), so mark it as part of the transition.
    for i in range(len(moves) - 2):
        m0, m1, m2 = moves[i], moves[i + 1], moves[i + 2]
        if m0['transition'] and m0['kind'] == 'CIRC' and m1['kind'] == 'LIN' and m2['kind'] == 'LIN':
            d1 = _v_sub(m1['pts'][-1], m1['pts'][0])
            d2 = _v_sub(m2['pts'][-1], m2['pts'][0])
            l1, l2 = math.sqrt(_v_dot(d1, d1)), math.sqrt(_v_dot(d2, d2))
            if l1 > 0 and l2 > 0 and _v_dot(d1, d2) / (l1 * l2) > 0.9999:
                m1['transition'] = True
    return start, moves


def _norm(v):
    n = math.sqrt(_v_dot(v, v))
    return _v_mul(v, 1.0 / n) if n > 0 else None


def move_tangents(start, item):
    """Exact unit travel directions (3D) at the start and the end of a LIN / CIRC that
    begins at `start`. Returns (t_start, t_end), or None for a degenerate move."""
    p2 = item.target.xyz
    if isinstance(item, Lin):
        t = _norm(_v_sub(p2, start))
        return (t, t) if t else None
    pv = item.via.xyz
    a, b = _v_sub(start, p2), _v_sub(pv, p2)
    axb = _v_cross(a, b)
    n2 = _v_dot(axb, axb)
    if n2 < 1e-12:                                   # collinear "arc": a straight line
        t = _norm(_v_sub(p2, start))
        return (t, t) if t else None
    c = _v_add(p2, _v_mul(_v_cross(_v_sub(_v_mul(b, _v_dot(a, a)), _v_mul(a, _v_dot(b, b))), axb), 1.0 / (2 * n2)))
    nhat = _norm(axb)
    tan = lambda p: _norm(_v_cross(nhat, _v_sub(p, c)))
    t1, t2 = tan(start), tan(p2)
    if _v_dot(t1, _v_sub(pv, start)) < 0:           # make it point along the travel
        t1, t2 = _v_mul(t1, -1), _v_mul(t2, -1)
    return t1, t2


def tangent_kinks(items):
    """Kink angle (deg) at every join between consecutive LIN/CIRC moves (0 = tangent),
    as a list of (index of the move after the join, angle)."""
    out, pos, prev_end, k = [], None, None, 0
    for item in items:
        if isinstance(item, Ptp):
            pos, prev_end = item.target.xyz, None
            continue
        if not isinstance(item, (Lin, Circ)) or pos is None:
            continue
        t = move_tangents(pos, item)
        if t and prev_end:
            # atan2(|a x b|, a.b) is accurate near 0 deg (acos is not)
            cr = _v_cross(prev_end, t[0])
            out.append((k, math.degrees(math.atan2(math.sqrt(_v_dot(cr, cr)), _v_dot(prev_end, t[0])))))
        prev_end = t[1] if t else None
        pos = item.target.xyz
        k += 1
    return out


def path_length(moves):
    """Total length (mm) of the moves from path_3d (arcs measured along their polyline)."""
    total = 0.0
    for m in moves:
        pts = m['pts']
        for p, q in zip(pts, pts[1:]):
            d = _v_sub(q, p)
            total += math.sqrt(_v_dot(d, d))
    return total
