"""Robot arm model (no tkinter, no libraries): where the six axes are for every point of a program.

Used for the checks before printing (reach, axis limits, singularities) and for the robot
drawn in the 3D view. The arm is a 6-axis robot with a spherical wrist (axes 4, 5, 6 meet in
one point), which is how the KUKA KR AGILUS and most industrial arms are built, so the
inverse kinematics has an exact solution (no iteration).

    Robot                     geometry + axis limits of one robot type (ROBOTS: the built-in ones)
    forward(robot, q)         axis angles (deg) -> flange frame in the robot's world
    joint_points(robot, q)    axis angles -> the points of the arm, for drawing
    inverse(robot, frame)     flange frame -> all axis solutions (up to 8)
    analyse(items, settings)  a program + its TOOL / BASE -> Report (axis angles along the path,
                              what cannot be reached, limits, singularities, messages)

Conventions (KUKA): world X forward, Z up, origin in the robot foot. A1 positive turns clockwise
seen from above; A2, A3, A5 positive turn the arm DOWN; A4, A6 positive turn clockwise seen
from behind. A2 = -90, A3 = +90 is the arm upright with the forearm level; there the flange is
at X 525, Z 890 with A 0, B 90, C 0 for the KR 6 R900 sixx. Frames use A, B, C = rotations about
Z, Y, X in that order (as in KRL).

THE MODEL IS FROM THE DATA SHEET, NOT MEASURED ON THE ROBOT. One reading of the smartPAD
(axis angles and the Cartesian position at the same pose) is enough to confirm it: see
`pose_of` at the end of this file.
"""
import json
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import path_model as pm

# ---------------------------------------------------------------- small matrix helpers
# A rotation is a tuple of 3 rows; a frame is (rotation, (x, y, z)).

def _rx(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))


def _ry(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))


def _rz(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def _mm(a, b):
    return tuple(tuple(a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j] for j in range(3))
                 for i in range(3))


def _mv(a, v):
    return tuple(a[i][0] * v[0] + a[i][1] * v[1] + a[i][2] * v[2] for i in range(3))


def _tr(a):
    return tuple(tuple(a[j][i] for j in range(3)) for i in range(3))


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def rot_abc(a, b, c):
    """KRL angles A, B, C (deg) -> rotation matrix: Rz(A) Ry(B) Rx(C)."""
    return _mm(_rz(a), _mm(_ry(b), _rx(c)))


def abc_of(r):
    """Rotation matrix -> KRL angles (A, B, C) in deg (B within -90..90)."""
    cb = math.hypot(r[0][0], r[1][0])
    if cb < 1e-9:                                   # B = +-90: A and C turn about the same line
        return (0.0, math.degrees(math.atan2(-r[2][0], cb)), math.degrees(math.atan2(-r[1][2], r[1][1])))
    return (math.degrees(math.atan2(r[1][0], r[0][0])), math.degrees(math.atan2(-r[2][0], cb)),
            math.degrees(math.atan2(r[2][1], r[2][2])))


def frame(x, y, z, a=0.0, b=0.0, c=0.0):
    return (rot_abc(a, b, c), (float(x), float(y), float(z)))


def frame_mul(f, g):
    return (_mm(f[0], g[0]), _add(f[1], _mv(f[0], g[1])))


def frame_inv(f):
    rt = _tr(f[0])
    p = _mv(rt, f[1])
    return (rt, (-p[0], -p[1], -p[2]))


def frame_point(f, p):
    return _add(f[1], _mv(f[0], p))


# ---------------------------------------------------------------- the robot

@dataclass(frozen=True)
class Robot:
    """One robot type. Lengths in mm (see the data sheet's dimension drawing), limits in deg."""
    name: str
    base_height: float            # floor to axis 2
    shoulder: float               # axis 1 to axis 2, forward
    upper_arm: float              # axis 2 to axis 3
    elbow: float                  # axis 3 to the forearm axis (axis 4), upward when the forearm is level
    forearm: float                # axis 3 to the wrist centre (axis 5), along the forearm
    wrist: float                  # wrist centre to the flange face
    limits: Tuple[Tuple[float, float], ...]      # (lowest, highest) for A1 .. A6
    a6_endless: bool = False      # axis 6 set up as an endless axis: no limit, turns are only reported
    note: str = ""

    @property
    def reach(self):
        """Largest distance from axis 2 to the wrist centre, plus the shoulder (data sheet 'max. reach')."""
        return self.shoulder + self.upper_arm + math.hypot(self.forearm, self.elbow)


_AGILUS_LIMITS = ((-170.0, 170.0), (-190.0, 45.0), (-120.0, 156.0), (-185.0, 185.0), (-120.0, 120.0),
                  (-350.0, 350.0))

# The owner's robot. Axis 6 is treated as endless: NouvTete15 ran about 9 loops the same way
# round (9 x 360 deg on axis 6) without an axis error, which a +-350 deg limit would not allow.
KR6_R900 = Robot("KR 6 R900 sixx", 400.0, 25.0, 455.0, 35.0, 420.0, 80.0, _AGILUS_LIMITS, a6_endless=True,
                 note="axis 6 treated as endless (9 loops ran without an axis error)")
# The same family, from the same data sheet (not tried): only the two arm lengths differ.
KR6_R700 = Robot("KR 6 R700 sixx", 400.0, 25.0, 315.0, 35.0, 365.0, 80.0, _AGILUS_LIMITS)
KR10_R1100 = Robot("KR 10 R1100 sixx", 400.0, 25.0, 560.0, 35.0, 515.0, 80.0, _AGILUS_LIMITS)

KR10_R900 = Robot("KR 10 R900 sixx", 400.0, 25.0, 455.0, 35.0, 420.0, 80.0, _AGILUS_LIMITS)

ROBOTS = {r.name: r for r in (KR6_R900, KR10_R900, KR6_R700, KR10_R1100)}
DEFAULT_ROBOT = KR6_R900

# Thickness of the arm for the collision warning (radius in mm around the line between two axes).
# Rough values for the KR AGILUS; they only have to be about right.
ARM_RADIUS = {"column": 100.0, "upper": 70.0, "forearm": 55.0, "wrist": 50.0}


# ---------------------------------------------------------------- the print head (simple shape)

@dataclass(frozen=True)
class Head:
    """The print head as a few boxes, for the 3D view and the collision warning.
    A box is (label, colour, (x0, x1), (y0, y1), (z0, z1), touches) in the TOOL frame of the
    program: origin = TCP (roller contact point), +X = the travel direction (where A points),
    +Z = down into the bed, so everything above the bed has a negative Z. `touches` marks the
    part that is meant to touch the bed (the roller): it is never reported."""
    name: str
    boxes: tuple = ()
    note: str = ""


# NouvTete: ESTIMATED from photos (2026-11-16), not measured. The flange centre is at
# X -13.9, Y 3.2, Z -186.1 in this frame (from TOOL_DATA[3]). The UV lamp trails the roller.
# Which side the funnel / spool is on (+Y or -Y) is a guess.
NOUVTETE_HEAD = Head("NouvTete (estimated shape)", (
    ("roller", "#3a3d42", (-15.0, 15.0), (-12.0, 12.0), (-30.0, 0.0), True),
    ("UV lamp", "#7c5cff", (-75.0, -25.0), (-20.0, 20.0), (-60.0, -8.0), False),
    ("head body", "#8a8f98", (-45.0, 20.0), (-30.0, 35.0), (-186.0, -30.0), False),
    ("funnel and spool", "#e8c62e", (-40.0, 40.0), (35.0, 130.0), (-180.0, -70.0), False),
), note="estimated from photos, not measured")
NO_HEAD = Head("No head shape (line only)")
HEADS = {h.name: h for h in (NOUVTETE_HEAD, NO_HEAD)}
DEFAULT_HEAD = NOUVTETE_HEAD

# what the checks and the 3D view use (chosen in the main app: Tools > Robot and head)
ACTIVE = {"robot": DEFAULT_ROBOT, "head": DEFAULT_HEAD}


def set_active(robot_name=None, head_name=None):
    """Choose the robot and / or the head by name (unknown names are ignored)."""
    if robot_name in ROBOTS:
        ACTIVE["robot"] = ROBOTS[robot_name]
    if head_name in HEADS:
        ACTIVE["head"] = HEADS[head_name]
    return ACTIVE["robot"], ACTIVE["head"]


def load_choice(path):
    """The robot and head saved in the settings file (key 'robot_model'), made active."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f).get("robot_model", {})
        set_active(data.get("robot"), data.get("head"))
    except (OSError, ValueError, AttributeError):
        pass
    return ACTIVE["robot"], ACTIVE["head"]


def save_choice(path):
    """Keeps the other entries of the file (theme, transfer folder)."""
    data = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        pass
    data["robot_model"] = {"robot": ACTIVE["robot"].name, "head": ACTIVE["head"].name}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def box_corners(box):
    """The 8 corners of a head box, in the tool frame."""
    _label, _col, xs, ys, zs = box[:5]
    return [(x, y, z) for x in xs for y in ys for z in zs]


BOX_FACES = ((0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5))


def _seg_dist(p, a, b):
    """Distance from point p to the segment a-b."""
    d = _sub(b, a)
    l2 = d[0] * d[0] + d[1] * d[1] + d[2] * d[2]
    w = _sub(p, a)
    t = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, (w[0] * d[0] + w[1] * d[1] + w[2] * d[2]) / l2))
    q = (w[0] - t * d[0], w[1] - t * d[1], w[2] - t * d[2])
    return math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2])


def _chain(robot, q):
    """The frames along the arm for axis angles q (deg): returns (points, wrist rotation)."""
    a1, a2, a3, a4, a5, a6 = q
    r1 = _rz(-a1)
    p1 = (0.0, 0.0, robot.base_height)
    p2 = _mv(r1, (robot.shoulder, 0.0, robot.base_height))
    r2 = _mm(r1, _ry(a2))
    p3 = _add(p2, _mv(r2, (robot.upper_arm, 0.0, 0.0)))
    r3 = _mm(r2, _ry(a3))
    p4 = _add(p3, _mv(r3, (0.0, 0.0, robot.elbow)))
    pw = _add(p4, _mv(r3, (robot.forearm, 0.0, 0.0)))
    r6 = _mm(r3, _mm(_rx(-a4), _mm(_ry(a5), _rx(-a6))))
    pf = _add(pw, _mv(r6, (robot.wrist, 0.0, 0.0)))
    return [(0.0, 0.0, 0.0), p1, p2, p3, p4, pw, pf], r6


_FLANGE = _ry(90.0)            # the flange frame: Z out of the flange, X down when the arm is level


def forward(robot, q):
    """Axis angles (deg) -> the flange frame in the robot's world."""
    pts, r6 = _chain(robot, q)
    return (_mm(r6, _FLANGE), pts[-1])


def joint_points(robot, q):
    """Axis angles -> [foot, top of the column, axis 2, axis 3, forearm start, wrist centre, flange]."""
    return _chain(robot, q)[0]


def _wrap(deg):
    """Into (-180, 180]."""
    d = (deg + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def _near(deg, ref):
    """The same angle, written within 180 deg of ref (so an axis that keeps turning keeps counting)."""
    return ref + _wrap(deg - ref)


def inverse(robot, fl):
    """Flange frame -> list of axis solutions [(a1 .. a6), ...] in deg, angles in (-180, 180].
    Up to 8: arm in front / over the back, elbow up / down, wrist one way / flipped. Empty when
    the point is out of reach. Limits are NOT applied here."""
    r6 = _mm(fl[0], _tr(_FLANGE))
    ax = (r6[0][0], r6[1][0], r6[2][0])                       # the direction the forearm's end points
    pw = _sub(fl[1], (ax[0] * robot.wrist, ax[1] * robot.wrist, ax[2] * robot.wrist))
    l1, l2 = robot.upper_arm, math.hypot(robot.forearm, robot.elbow)
    phi = math.degrees(math.atan2(robot.elbow, robot.forearm))
    out = []
    front = math.degrees(math.atan2(pw[1], pw[0])) if math.hypot(pw[0], pw[1]) > 1e-9 else 0.0
    for theta in (front, front + 180.0):                      # the direction the arm faces
        th = math.radians(theta)
        r = pw[0] * math.cos(th) + pw[1] * math.sin(th) - robot.shoulder
        h = pw[2] - robot.base_height
        cos_d = (r * r + h * h - l1 * l1 - l2 * l2) / (2.0 * l1 * l2)
        if abs(cos_d) > 1.0:
            continue
        for sign in (-1.0, 1.0):                              # elbow up, elbow down
            d = sign * math.acos(cos_d)
            e1 = math.atan2(h, r) - math.atan2(l2 * math.sin(d), l1 + l2 * math.cos(d))
            a1, a2, a3 = _wrap(-theta), _wrap(-math.degrees(e1)), _wrap(-math.degrees(d) + phi)
            m = _mm(_tr(_mm(_rz(-a1), _ry(a2 + a3))), r6)     # = Rx(-a4) Ry(a5) Rx(-a6)
            sb = math.hypot(m[0][1], m[0][2])
            for flip in (1.0, -1.0):
                beta = math.atan2(flip * sb, m[0][0])
                if sb < 1e-9:                                 # axes 4 and 6 in line: only their sum counts
                    alpha, gamma = 0.0, math.atan2(-m[1][2], m[1][1])
                else:
                    gamma = math.atan2(flip * m[0][1], flip * m[0][2])
                    alpha = math.atan2(flip * m[1][0], -flip * m[2][0])
                out.append((a1, a2, a3, _wrap(-math.degrees(alpha)), math.degrees(beta),
                            _wrap(-math.degrees(gamma))))
    return out


def status_of(robot, q):
    """KRL Status of axis angles: bit 0 = wrist centre behind axis 1, bit 1 = elbow branch
    (A3 at or above the angle of the elbow offset), bit 2 = A5 not positive."""
    pw = joint_points(robot, q)[5]
    th = math.radians(-q[0])
    behind = pw[0] * math.cos(th) + pw[1] * math.sin(th) < 0
    phi = math.degrees(math.atan2(robot.elbow, robot.forearm))
    return (1 if behind else 0) + (2 if q[2] >= phi else 0) + (4 if q[4] <= 0 else 0)


def turn_of(q):
    """KRL Turn of axis angles: bit n-1 set when axis n is negative."""
    return sum(1 << k for k in range(6) if q[k] < 0)


def _within(robot, q, k):
    lo, hi = robot.limits[k]
    return (k == 5 and robot.a6_endless) or lo - 1e-6 <= q[k] <= hi + 1e-6


def pick(robot, sols, prev=None, status=None, turn=None):
    """Choose one of the solutions: the one nearest to the previous axis angles (a LIN / CIRC
    cannot change the arm's posture on the way), or for the first point the one matching the
    program's Status (S) and Turn (T), else arm in front, elbow up, inside the limits."""
    if not sols:
        return None
    if prev is not None:
        best, cost = None, None
        for s in sols:
            s = (s[0], s[1], s[2], _near(s[3], prev[3]), s[4], _near(s[5], prev[5]))
            c = sum(abs(s[k] - prev[k]) for k in range(6))
            if cost is None or c < cost:
                best, cost = s, c
        return best

    def score(s):
        n = 0.0
        if status is not None:
            n += 100.0 * bin(status_of(robot, s) ^ int(status)).count("1")
        else:
            n += 100.0 * bin(status_of(robot, s) ^ 2).count("1")
        n += 10.0 * sum(1 for k in range(6) if not _within(robot, s, k))
        return n + abs(s[3]) / 1000.0
    best = min(sols, key=score)
    if turn is not None:                            # A4 / A6 written on the side the Turn bits ask for
        q = list(best)
        for k in (3, 5):
            want_neg = bool(int(turn) >> k & 1)
            alt = q[k] - 360.0 if (want_neg and q[k] > 0) else (q[k] + 360.0 if (not want_neg and q[k] < 0) else q[k])
            lo, hi = robot.limits[k]
            if alt != q[k] and lo <= alt <= hi:
                q[k] = alt
        best = tuple(q)
    return best


# ---------------------------------------------------------------- a program on the robot

MAX_POSES = 4000              # at most this many points are solved (longer programs: wider steps)
A5_WARN = 8.0                 # deg: axis 5 nearer to 0 than this = wrist singularity close by
STRETCH_WARN = 0.97           # arm stretched to this share of its full length = edge of the reach
OVERHEAD_WARN = 60.0          # mm: wrist centre this close to the line of axis 1


@dataclass
class Report:
    robot: Robot
    poses: List[dict] = field(default_factory=list)     # {'item', 'xyz', 'abc', 'world' (TCP), 'q' or None}
    unreachable: int = 0
    over: dict = field(default_factory=dict)            # axis number -> (lowest, highest) angle reached
    ranges: List[Tuple[float, float]] = field(default_factory=list)   # reached (lowest, highest) per axis
    min_a5: Optional[float] = None
    stretch: float = 0.0                                # largest share of the full arm length used
    start_st: Optional[Tuple[int, int]] = None          # Status / Turn the model finds for the first point
    head: Optional[Head] = None
    hits: dict = field(default_factory=dict)            # kind of collision -> (how deep in mm, index of the pose)
    messages: List[str] = field(default_factory=list)   # what to look at (empty = nothing found)

    @property
    def ok(self):
        return not self.messages

    def summary(self):
        """One line: the range of every axis over the program."""
        if not self.ranges:
            return "%s: no point could be solved." % self.robot.name
        return "%s axes:  " % self.robot.name + "   ".join(
            "A%d %.0f…%.0f°" % (k + 1, lo, hi) for k, (lo, hi) in enumerate(self.ranges))


def program_poses(items, step=10.0, max_poses=MAX_POSES):
    """The TCP poses along a program: every move's end, and points in between at most `step` mm
    apart (wider for a long program, so there are at most about max_poses). A, B, C go evenly from
    a move's start to its end (A the short way), which is how the apps' programs turn the head.
    Returns [{'item': index, 'xyz': (x, y, z), 'abc': (a, b, c), 's': S, 't': T}, ...]."""
    start, moves = pm.path_3d(items)
    length = pm.path_length(moves)
    n_ends = sum(1 for i in items if isinstance(i, (pm.Lin, pm.Circ)))
    stride = max(1, int(math.ceil(n_ends / float(max_poses))))     # very long program: every n-th move only
    budget = max(max_poses - n_ends // stride, 1)
    step = max(step, length / budget)
    out, pos, abc, n_move = [], None, None, 0

    def angles(t, last):
        vals = tuple(v if v is not None else (last[k] if last else 0.0)
                     for k, v in enumerate((t.a, t.b, t.c)))
        return vals

    for idx, item in enumerate(items):
        if isinstance(item, pm.Raw) and item.text.strip() != item.text:
            item = pm.parse_line(item.text.strip())
        if isinstance(item, pm.Ptp):
            pos, abc = item.target.xyz, angles(item.target, abc)
            out.append({'item': idx, 'xyz': pos, 'abc': abc, 's': item.target.s, 't': item.target.t, 'ptp': True})
            continue
        if not isinstance(item, (pm.Lin, pm.Circ)) or pos is None:
            continue
        end, abc_end = item.target.xyz, angles(item.target, abc)
        fr = pm._arc_frame(pos, item.via.xyz, end) if isinstance(item, pm.Circ) else None
        if fr is not None:
            c, rad, e1, e2, sweep = fr
            dist = abs(sweep) * rad
        else:
            d = _sub(end, pos)
            dist = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
        n = max(1, int(math.ceil(dist / step)))
        n_move += 1
        da = pm.angle_diff(abc[0], abc_end[0])
        for k in range(1, n + 1 if n_move % stride == 0 or n_move == n_ends else 1):
            f = k / float(n)
            if k == n:
                p = end
            elif fr is not None:
                t = sweep * f
                p = tuple(c[j] + rad * (e1[j] * math.cos(t) + e2[j] * math.sin(t)) for j in range(3))
            else:
                p = tuple(pos[j] + (end[j] - pos[j]) * f for j in range(3))
            o = (abc[0] + da * f, abc[1] + (abc_end[1] - abc[1]) * f, abc[2] + (abc_end[2] - abc[2]) * f)
            out.append({'item': idx, 'xyz': p, 'abc': o, 's': None, 't': None, 'ptp': False})
        pos, abc = end, abc_end
    return out


BED_SIZE = None              # (x, y) of the bed plate in mm, for 'arm touches the bed' (set by the main app)
HEAD_CLEAR = 0.5             # mm: a head part this far into the bed is reported
WRIST_FREE = 130.0           # mm of the forearm next to the wrist that the head may come close to


def _collisions(rep, k, robot, head, base_inv, pose_frame, q):
    """Collision warning for one pose: head parts in the bed, arm in the bed, head against
    the arm. Records the deepest case of each kind in rep.hits and returns True if any."""
    hit = False

    def note(kind, depth):
        if kind not in rep.hits or depth > rep.hits[kind][0]:
            rep.hits[kind] = (depth, k)
    pts = joint_points(robot, q)
    world = frame_mul(frame_inv(base_inv), pose_frame)          # the TCP frame in the robot's world
    arm = ((pts[0], pts[1], ARM_RADIUS["column"]), (pts[2], pts[3], ARM_RADIUS["upper"]))
    fore = _sub(pts[5], pts[4])
    fl = math.sqrt(fore[0] ** 2 + fore[1] ** 2 + fore[2] ** 2)
    if fl > WRIST_FREE:                                         # the forearm without its end at the wrist
        f = (fl - WRIST_FREE) / fl
        arm += ((pts[4], _add(pts[4], (fore[0] * f, fore[1] * f, fore[2] * f)), ARM_RADIUS["forearm"]),)
    for box in head.boxes:
        label, touches = box[0], box[5]
        for corner in box_corners(box):
            if not touches:
                z = frame_point(pose_frame, corner)[2]          # height over the bed (base frame)
                if z < -HEAD_CLEAR:
                    note("The %s of the head would go %%.1f mm into the bed" % label, -z)
                    hit = True
            w = frame_point(world, corner)
            for a, b, r in arm:
                d = r - _seg_dist(w, a, b)
                if d > 0:
                    note("The %s of the head would touch the robot's own arm (by %%.0f mm)" % label, d)
                    hit = True
    if BED_SIZE:                                                # elbow, forearm and wrist against the bed plate
        for p, r in ((pts[3], ARM_RADIUS["upper"]), (pts[4], ARM_RADIUS["forearm"]), (pts[5], ARM_RADIUS["wrist"])):
            b = frame_point(base_inv, p)
            if b[2] < r and -r < b[0] < BED_SIZE[0] + r and -r < b[1] < BED_SIZE[1] + r:
                note("The robot's arm would touch the bed plate (by %.0f mm)", r - b[2])
                hit = True
    return hit


def analyse(items, settings, robot=None, step=10.0, max_poses=MAX_POSES, head=None):
    """Put a program on the robot: `settings` gives the BASE and TOOL frames the program uses
    (krl_export.ExportSettings). robot / head: default = the active ones (set_active).
    Returns a Report."""
    robot = robot or ACTIVE["robot"]
    head = head or ACTIVE["head"]
    rep = Report(robot)
    rep.head = head
    base_inv = frame_inv(frame(*settings.base))
    base = frame(*settings.base)
    tool_inv = frame_inv(frame(*settings.tool))
    full = robot.upper_arm + math.hypot(robot.forearm, robot.elbow)
    prev, first_bad = None, None
    lows, highs = [None] * 6, [None] * 6
    near_axis1 = False
    for ps in program_poses(items, step, max_poses):
        pose_frame = frame(*(ps['xyz'] + ps['abc']))
        tcp = frame_mul(base, pose_frame)
        fl = frame_mul(tcp, tool_inv)
        sols = inverse(robot, fl)
        if ps['ptp'] or prev is None:
            q = pick(robot, sols, None, ps['s'], ps['t'])
            if q is not None and rep.start_st is None:
                rep.start_st = (status_of(robot, q), turn_of(q))
        else:
            q = pick(robot, sols, prev)
        entry = {'item': ps['item'], 'xyz': ps['xyz'], 'abc': ps['abc'], 'world': tcp[1], 'q': q}
        rep.poses.append(entry)
        if q is None:
            rep.unreachable += 1
            if first_bad is None:
                first_bad = ps
            continue
        prev = q
        for k in range(6):
            lows[k] = q[k] if lows[k] is None else min(lows[k], q[k])
            highs[k] = q[k] if highs[k] is None else max(highs[k], q[k])
        a5 = abs(q[4])
        rep.min_a5 = a5 if rep.min_a5 is None else min(rep.min_a5, a5)
        pts = joint_points(robot, q)
        w = _sub(pts[5], pts[2])
        rep.stretch = max(rep.stretch, math.sqrt(w[0] * w[0] + w[1] * w[1] + w[2] * w[2]) / full)
        near_axis1 = near_axis1 or math.hypot(pts[5][0], pts[5][1]) < OVERHEAD_WARN
        if head.boxes or BED_SIZE:
            entry['hit'] = _collisions(rep, len(rep.poses) - 1, robot, head, base_inv, pose_frame, q)
    if lows[0] is not None:
        rep.ranges = list(zip(lows, highs))
        for k in range(6):
            lo, hi = robot.limits[k]
            if (k == 5 and robot.a6_endless) or (lows[k] >= lo - 1e-6 and highs[k] <= hi + 1e-6):
                continue
            rep.over[k + 1] = (lows[k], highs[k])

    name, msgs = robot.name, rep.messages
    if rep.unreachable:
        p = first_bad['xyz']
        msgs.append("The robot (%s, reach %.0f mm) cannot reach %d of the %d checked points; the first one is "
                    "X %.0f, Y %.0f, Z %.0f. Suggestion: move the part nearer to the robot (Centre X / Y), "
                    "or check TOOL and BASE in Export Settings."
                    % (name, robot.reach, rep.unreachable, len(rep.poses), p[0], p[1], p[2]))
    for axis, (lo, hi) in sorted(rep.over.items()):
        l0, l1 = robot.limits[axis - 1]
        extra = (" The head turns the same way on every loop, so axis 6 keeps turning: fewer loops, or a robot "
                 "with an endless axis 6.") if axis == 6 else ""
        msgs.append("Axis %d would go from %.0f to %.0f deg; its limits are %.0f to %.0f deg (%s).%s"
                    % (axis, lo, hi, l0, l1, name, extra))
    if rep.min_a5 is not None and rep.min_a5 < A5_WARN:
        msgs.append("Axis 5 comes within %.1f deg of 0 (wrist singularity): axes 4 and 6 may spin fast there "
                    "and the robot may stop with an error. Suggestion: tilt the head a little (B / Tilt) or "
                    "move the part." % rep.min_a5)
    if near_axis1:
        msgs.append("The wrist passes almost over the robot's own axis 1 (overhead singularity). Suggestion: "
                    "move the part away from the robot foot.")
    if not rep.unreachable and rep.stretch > STRETCH_WARN:
        msgs.append("The arm is stretched to %.0f %% of its length: this is the edge of the reach, where the "
                    "robot moves badly. Suggestion: move the part nearer to the robot." % (100.0 * rep.stretch))
    for text, (depth, k) in sorted(rep.hits.items()):
        p = rep.poses[k]['xyz']
        extra = ""
        if "into the bed" in text:
            extra = " Suggestion: less tilt (B / Tilt), or a higher Start Z."
        elif "own arm" in text:
            extra = " Suggestion: move the part further from the robot foot, or turn it."
        msgs.append((text % depth) + " at X %.0f, Y %.0f, Z %.0f (the head shape is %s).%s"
                    % (p[0], p[1], p[2], head.note or "a simple model", extra)
                    if "head" in text else (text % depth) + " at X %.0f, Y %.0f, Z %.0f. Suggestion: move the part "
                    "nearer to the middle of the bed, or raise it." % (p[0], p[1], p[2]))
    return rep


def pose_of(robot, q, settings=None):
    """What the smartPAD should show for axis angles q: the flange (no settings) or the TCP in the
    program's base, as (X, Y, Z, A, B, C). To confirm the model on the real robot: read the axis
    angles and the Cartesian position at one pose (tool and base as in Export Settings) and
    compare with pose_of(robot, those angles, krl_export.active_settings()[0])."""
    fl = forward(robot, q)
    if settings is not None:
        fl = frame_mul(frame_inv(frame(*settings.base)), frame_mul(fl, frame(*settings.tool)))
    return tuple(fl[1]) + abc_of(fl[0])
