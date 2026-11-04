"""Cuboid (rounded rectangle) path generator (no tkinter).

Moved out of PythonApplication6 (Automate) so the cuboid app and the main app run the SAME
code. Two entry points:

  generate_from_loop(...)  any base loop (Auto-Generate, manual, imported) -> moves.
                           Exact counts: n_turns rings per layer, n_layers layers
                           (App6 passes N+1 to keep its old "N gives N+1" behaviour).
  generate(params)         parametric rounded rectangle (CuboidParams) -> (items, info),
                           exact N, used by the main app.

Path (the alternating spiral, see Sequence.txt):
  - Turn t of a layer = the base loop moved outward by E*t (shapes.offset_loop: edges shift,
    fillets keep their centre and grow, stay tangent).
  - Even layers go outward (T0 -> Tn), odd layers inward (Tn -> T0); layer l at Z + H*l.
  - Turn and layer changes: exact tangent fillet transition (LIN + CIRC or CIRC + LIN),
    falling back to the old single CIRC with a 20 % via offset if the geometry does not allow it.

Orientation with auto-orient (the "pen-like" rule the app always used):
  - PTP start: A from the interface, B = tilt, C from the interface; current A = 180.
  - LIN: keeps the current A (no rotation on a straight edge); B, C rounded to 0.1.
  - CIRC end: A = direction of the next edge (towards the next LIN point; the last CIRC of a
    turn looks at the turn's start point); transitions: A = outgoing direction.
  Auto-orient off: A/B/C from the interface on every move (the transitions still use the
  computed A, as before).
"""
import copy
import math
from dataclasses import dataclass
from typing import Optional

import path_model as pm
import shapes

PTP_S, PTP_T = 2, 43
MIN_RADIUS_WARN = 20.0       # mm, same warning level as the cylinder


def normalize_angle(angle):
    """To the range [-180, 180]."""
    while angle > 180.0:
        angle -= 360.0
    while angle < -180.0:
        angle += 360.0
    return angle


def a1(v):
    """Angle rounded to 0.1 deg (how computed angles are written)."""
    return round(float(v), 1)


def heading(dx, dy):
    return normalize_angle(math.degrees(math.atan2(dy, dx)))


def _last_two_points(points, points_circ, motion_commands):
    """(start, end) of the final move of a loop: the travel direction arriving at a transition."""
    i, j, prev, last = 1, 0, None, points[0]
    for k in motion_commands:
        prev = last
        if k == "LIN":
            last = points[i]
            i += 1
        elif k == "CIRC":
            last = points_circ[j + 1]
            j += 2
    return prev, last


class _Writer:
    """Collects the items and carries the current A (what App6 kept in a global)."""

    def __init__(self):
        self.items = []
        self.a = 180.0

    def comment(self, text):
        self.items.append(pm.Comment(text))

    def ptp(self, xyz, abc):
        self.items.append(pm.Ptp(pm.pose(xyz, abc, PTP_S, PTP_T)))

    def lin(self, xyz, abc):
        self.items.append(pm.Lin(pm.pose(xyz, abc)))

    def circ(self, via, end, abc):
        self.items.append(pm.Circ(pm.pose(via), pm.pose(end, abc)))


def _fillet_transition(w, prev_point, from_point, to_point, next_point, c, tilt):
    """Exact tangent transition between two turns (or layers).

    The path arrives at from_point travelling along (prev_point -> from_point) and must
    leave to_point travelling along (to_point -> next_point). The two lines meet at a
    corner K. A round fillet tangent to both lines needs the same distance to K on both
    sides, but from_point and to_point usually lie on different rings (one E apart), so the
    distances differ. The shorter distance L is used for the fillet and the difference is
    filled with a straight LIN along the longer side:
        [LIN from_point -> F1]   CIRC F1 -> via -> F2   [LIN F2 -> to_point]
    Every join is tangent (0 deg kink). Returns False if the geometry does not allow it."""
    if prev_point is None or next_point is None:
        return False
    sx, sy = from_point[0], from_point[1]
    tx, ty = to_point[0], to_point[1]
    uix, uiy = sx - prev_point[0], sy - prev_point[1]
    uox, uoy = next_point[0] - tx, next_point[1] - ty
    li, lo = math.hypot(uix, uiy), math.hypot(uox, uoy)
    if li < 1e-9 or lo < 1e-9:
        return False
    uix, uiy, uox, uoy = uix / li, uiy / li, uox / lo, uoy / lo

    cross = uix * uoy - uiy * uox          # >0: left (CCW) turn, <0: right turn
    dot = uix * uox + uiy * uoy
    turn = math.atan2(cross, dot)          # signed turning angle
    if abs(cross) < 1e-6 or abs(turn) > math.radians(170):
        return False                       # parallel / U-turn: no sensible fillet

    # Corner K: from_point + a*u_in == to_point - b*u_out
    dx, dy = tx - sx, ty - sy
    a_len = (dx * uoy - dy * uox) / cross  # distance from from_point to K
    b_len = (uix * dy - uiy * dx) / cross  # distance from K to to_point
    if a_len <= 1e-6 or b_len <= 1e-6:
        return False                       # corner lies behind us: not a simple corner
    kx, ky = sx + a_len * uix, sy + a_len * uiy

    L = min(a_len, b_len)                  # tangent length of the fillet
    R = L / math.tan(abs(turn) / 2)        # fillet radius
    f1x, f1y = kx - L * uix, ky - L * uiy  # fillet start (on incoming line)
    f2x, f2y = kx + L * uox, ky + L * uoy  # fillet end   (on outgoing line)
    side = 1.0 if cross > 0 else -1.0
    cx_, cy_ = f1x - side * uiy * R, f1y + side * uix * R   # fillet centre
    kcx, kcy = kx - cx_, ky - cy_
    kc = math.hypot(kcx, kcy)
    vx, vy = cx_ + R * kcx / kc, cy_ + R * kcy / kc         # via = arc midpoint

    # Z: rise linearly with path length (layer transitions change Z)
    lin1, arc, lin2 = a_len - L, R * abs(turn), b_len - L
    total = lin1 + arc + lin2
    z0, z1 = from_point[2], to_point[2]

    def z_at(s):
        return z0 + (z1 - z0) * (s / total if total > 0 else 1.0)
    zf1, zv, zf2 = z_at(lin1), z_at(lin1 + arc / 2), z_at(lin1 + arc)

    if lin1 > 1e-6:
        # Straight continuation of the incoming edge: A stays as it is
        w.lin((f1x, f1y, zf1), (a1(w.a), tilt, c))
    w.a = heading(uox, uoy)                                 # A at arc end = outgoing direction
    if lin2 > 1e-6:
        w.circ((vx, vy, zv), (f2x, f2y, zf2), (a1(w.a), tilt, c))
        w.lin((tx, ty, to_point[2]), (a1(w.a), tilt, c))
    else:
        # Arc ends exactly on to_point: write to_point itself (no rounding drift)
        w.circ((vx, vy, zv), (tx, ty, to_point[2]), (a1(w.a), tilt, c))
    return True


def _transition(w, from_point, to_point, next_point, c, tilt, prev_point=None):
    """Tangent fillet transition, or the old single CIRC with a 20 %-of-chord via offset."""
    if _fillet_transition(w, prev_point, from_point, to_point, next_point, c, tilt):
        return
    mid_x = (from_point[0] + to_point[0]) / 2
    mid_y = (from_point[1] + to_point[1]) / 2
    mid_z = (from_point[2] + to_point[2]) / 2
    dx = to_point[0] - from_point[0]
    dy = to_point[1] - from_point[1]
    distance = math.sqrt(dx * dx + dy * dy)
    if distance == 0:
        return                             # same point: no transition needed
    dx_norm, dy_norm = dx / distance, dy / distance
    perp_x, perp_y = dy_norm, -dx_norm     # 90 deg clockwise
    offset_distance = distance * 0.2
    via = (mid_x + perp_x * offset_distance, mid_y + perp_y * offset_distance, mid_z)
    w.a = heading(next_point[0] - to_point[0], next_point[1] - to_point[1])
    w.circ(via, to_point, (a1(w.a), tilt, c))


def _turn_path(w, pts, circ, mc, a, b, c, tilt, auto_orient):
    """The moves of one turn (the loop after its start point)."""
    i, j = 1, 0
    for k in mc:
        if k == "LIN":
            if auto_orient:
                w.lin(pts[i], (a1(w.a), a1(tilt), a1(c)))   # A kept, B/C rounded (as before)
            else:
                w.lin(pts[i], (a, b, c))
            i += 1
        elif k == "CIRC":
            end = circ[j + 1]
            nxt = pts[i] if i < len(pts) else pts[0]       # next LIN point, or the turn start
            w.a = heading(nxt[0] - end[0], nxt[1] - end[1])
            if auto_orient:
                w.circ(circ[j], end, (a1(w.a), tilt, c))
            else:
                w.circ(circ[j], end, (a, b, c))
            j += 2


def generate_from_loop(points, points_circ, motion_commands, step, layer_height, n_turns, n_layers,
                       a, b, c, tilt, auto_orient=True):
    """Alternating spiral over a base loop. Returns (items, final_a).

    points/points_circ/motion_commands: the base loop (see shapes.py). step = E (mm, outward
    per turn), layer_height = H (mm). n_turns rings per layer and n_layers layers, EXACT.
    a, b, c: interface orientation; tilt: B used with auto-orient. final_a = the current A
    after the last move (App6 keeps it for its preview)."""
    w = _Writer()
    base_p = [list(p) for p in points]
    base_c = [list(p) for p in points_circ]
    mc = list(motion_commands)

    # every turn of every layer (the loop moved out by E*t, raised by H*l)
    saved = {}
    for layer in range(n_layers):
        lp, lc = copy.deepcopy(base_p), copy.deepcopy(base_c)
        if layer > 0:
            m, n = 1, 0
            for k in mc:
                if k == "LIN":
                    lp[m][2] += layer_height * layer
                    m += 1
                elif k == "CIRC":
                    lc[n][2] += layer_height * layer
                    lc[n + 1][2] += layer_height * layer
                    n += 2
            lp[0][2] += layer_height * layer
        saved[layer] = {}
        for turn in range(n_turns):
            if turn > 0:
                tp, tc = shapes.offset_loop(lp, lc, mc, step * turn)
            else:
                tp, tc = copy.deepcopy(lp), copy.deepcopy(lc)
            saved[layer][turn] = (tp, tc)

    order_of = lambda layer: list(range(n_turns)) if layer % 2 == 0 else list(range(n_turns - 1, -1, -1))
    for layer in range(n_layers):
        w.comment("===== LAYER %d ===== (%s SPIRAL)" % (layer, "OUTWARD" if layer % 2 == 0 else "INWARD"))
        order = order_of(layer)
        for idx, turn in enumerate(order):
            w.comment("L%d T%d - %s" % (layer, turn, "START" if idx == 0 else "TRANSITION from T%d" % order[idx - 1]))
            tp, tc = saved[layer][turn]
            if idx == 0 and layer == 0:
                if auto_orient:
                    w.a = 180.0
                    w.ptp(tp[0], (a, tilt, c))
                else:
                    w.a = float(a)
                    w.ptp(tp[0], (a, b, c))
            elif idx == 0:
                w.comment("L%d -> L%d TRANSITION" % (layer - 1, layer))
                pp, pc = saved[layer - 1][order_of(layer - 1)[-1]]
                before, last = _last_two_points(pp, pc, mc)
                _transition(w, last, tp[0], tp[1], c, tilt, prev_point=before)
            else:
                pp, pc = saved[layer][order[idx - 1]]
                before, last = _last_two_points(pp, pc, mc)
                _transition(w, last, tp[0], tp[1], c, tilt, prev_point=before)
            _turn_path(w, tp, tc, mc, a, b, c, tilt, auto_orient)
    return w.items, w.a


# ------------------------------------------------------------------ parametric (main app)

@dataclass
class CuboidParams:
    xc: float
    yc: float
    z0: float                       # height of the first layer (App6: Zr + tool height)
    length: float                   # X
    width: float                    # Y
    corner_radius: Optional[float]  # None = automatic (shapes.auto_corner_radius)
    step: float                     # E: distance between turns (mm)
    layer_height: float             # H (mm)
    turns: int                      # exact
    layers: int                     # exact
    a: float = 180.0
    b: float = 20.0                 # B / tilt (used as B in both modes, no clamp)
    c: float = 180.0
    auto_orient: bool = True


def radius_of(p):
    return shapes.auto_corner_radius(p.length, p.width) if p.corner_radius is None else p.corner_radius


def validate(p):
    """(errors, warnings) as lists of strings."""
    errors, warnings = [], []
    if p.length <= 0 or p.width <= 0:
        errors.append("Length and width must be greater than 0.")
    if p.step <= 0:
        errors.append("Turn step E must be greater than 0.")
    if p.layer_height <= 0:
        errors.append("Layer height must be greater than 0.")
    if p.turns < 1 or p.layers < 1:
        errors.append("Turns and layers must be at least 1.")
    if errors:
        return errors, warnings
    r, r_max = radius_of(p), min(p.length, p.width) / 2
    if not (0 < r <= r_max):
        errors.append("Corner radius must be greater than 0 and at most half the shorter side (%g mm)." % r_max)
    elif r < MIN_RADIUS_WARN:
        warnings.append("Corner radius is %.1f mm (below %g mm): the head may not follow it well."
                        % (r, MIN_RADIUS_WARN))
    return errors, warnings


def generate(p):
    """Parametric rounded-rectangle print. Returns (items, info); raises ValueError if invalid."""
    errors, warnings = validate(p)
    if errors:
        raise ValueError(" ".join(errors))
    r = radius_of(p)
    pts, circ, mc = shapes.rounded_rect_base(p.xc, p.yc, p.z0, p.length, p.width, r)
    items, _ = generate_from_loop(pts, circ, mc, p.step, p.layer_height, p.turns, p.layers,
                                  p.a, p.b, p.c, p.b, p.auto_orient)
    start, moves = pm.path_3d(items)
    info = {
        "moves": len(moves),
        "length_mm": pm.path_length(moves),
        "corner_radius": r,
        "outer_size": (p.length + 2 * p.step * (p.turns - 1), p.width + 2 * p.step * (p.turns - 1)),
        "wall_thickness": p.turns * p.step,
        "z_range": (p.z0, p.z0 + p.layer_height * (p.layers - 1)),
        "warnings": warnings,
    }
    return items, info
