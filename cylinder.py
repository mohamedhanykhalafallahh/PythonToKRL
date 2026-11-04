"""Cylinder (tube) path generator (no tkinter).

generate(params) -> (items, info): the KRL motion body as path_model items, plus a summary.

Path
  - Ring t of every layer is a circle of radius R_t = inner_diameter/2 + E*t around (xc, yc),
    travelled counter-clockwise, starting at angle 0 (the +X side).
  - A ring is 4 quarter CIRCs (via at 45 deg). The LAST quarter (270 -> 360 deg) is special:
      * lane change to the next ring: two tangent 45-deg arcs from R_t to R_t+-E (exact
        tangency, see _lane_change), or
      * on the last ring of a layer: the climb to the next layer (Z rises along the quarter),
      * on the very last ring: a normal flat quarter (the print ends at angle 0).
  - Layers alternate like App6: even layers go outward (ring 0 -> N-1), odd layers inward.
  - Helix option (only with 1 turn per layer): the climb is spread over the whole loop
    (H/4 per quarter) instead of the last quarter. The last loop is flat in both modes.
  - Exactly `turns` rings per layer and `layers` layers (not N+1).

Orientation (auto-orient on): A = travel direction (heading) at each CIRC end, so it rotates
90 deg per quarter, exactly matching the tangent; B and C from the interface. The PTP start
already points along the travel direction. Auto-orient off: A/B/C from the interface.
"""
import math
from dataclasses import dataclass

import path_model as pm

MIN_RADIUS_WARN = 20.0      # mm: smallest arc radius the head is known to follow well
PTP_S, PTP_T = 2, 43        # Status / Turn on the start PTP (same as App6)
_K = 2 ** -0.5


@dataclass
class CylinderParams:
    xc: float
    yc: float
    z0: float
    inner_diameter: float
    step: float            # E: distance between rings (mm)
    layer_height: float    # H: Z step between layers (mm)
    turns: int             # rings per layer (wall thickness = turns * E)
    layers: int
    a: float = 180.0
    b: float = 20.0
    c: float = 180.0
    auto_orient: bool = True
    helix: bool = False


# ------------------------------------------------------------------ small helpers

def normalize_angle(angle):
    """To the range [-180, 180] (same rule as App6)."""
    while angle > 180.0:
        angle -= 360.0
    while angle < -180.0:
        angle += 360.0
    return angle


def a1(v):
    """Angle rounded to 0.1 deg (as App6 writes computed angles)."""
    return round(float(v), 1)


def _cs(deg):
    """(cos, sin) of an angle in degrees, exact for multiples of 90 and 45."""
    d = deg % 360.0
    exact = {0.0: (1.0, 0.0), 90.0: (0.0, 1.0), 180.0: (-1.0, 0.0), 270.0: (0.0, -1.0),
             45.0: (_K, _K), 135.0: (-_K, _K), 225.0: (-_K, -_K), 315.0: (_K, -_K)}
    if d in exact:
        return exact[d]
    r = math.radians(d)
    return math.cos(r), math.sin(r)


def _rot(v, cs):
    return (v[0] * cs[0] - v[1] * cs[1], v[0] * cs[1] + v[1] * cs[0])


# ------------------------------------------------------------------ lane change geometry

def _lane_change(r1, r2, theta_a_deg, span_deg=90.0):
    """Tangent path from the circle r1 at angle theta_a to the circle r2 at theta_a + span
    (both around the origin, travelling counter-clockwise) as TWO circular arcs.

    Arc 1 starts tangent to circle r1, arc 2 ends tangent to circle r2, and the arcs are
    tangent to each other at the joint J. With a symmetric choice (both centres offset by s
    along the radial lines of the end points) the tangency condition gives
        s = (r2 - r1) * (1 + cos(beta)) / (2 * sin(beta)**2),   beta = span / 2,
    and each arc sweeps exactly beta. Moving outward the first arc is flatter (r1 + s) and
    the second sharper (r2 - s); inward it is the other way round.

    Returns [(via, end, radius, centre), (via, end, radius, centre)] in XY around the origin."""
    beta = math.radians(span_deg / 2.0)
    cb, sb = math.cos(beta), math.sin(beta)
    s = (r2 - r1) * (1 + cb) / (2 * sb * sb)
    # local frame: the span is symmetric around the +X axis (A at -beta, B at +beta)
    uA, uB = (cb, -sb), (cb, sb)
    A = (r1 * uA[0], r1 * uA[1])
    C1, rho1 = (-s * uA[0], -s * uA[1]), r1 + s
    C2, rho2 = (s * uB[0], s * uB[1]), r2 - s
    d = math.hypot(C2[0] - C1[0], C2[1] - C1[1])
    ux, uy = (C2[0] - C1[0]) / d, (C2[1] - C1[1]) / d
    # joint: on the line of centres, on circle 1 and circle 2 (pick the right side)
    cands = [(C1[0] + sg * rho1 * ux, C1[1] + sg * rho1 * uy) for sg in (1, -1)]
    J = min(cands, key=lambda q: abs(math.hypot(q[0] - C2[0], q[1] - C2[1]) - rho2))
    B = (r2 * uB[0], r2 * uB[1])

    def mid(C, P, sweep):
        return (C[0] + _rot((P[0] - C[0], P[1] - C[1]), (math.cos(sweep / 2), math.sin(sweep / 2)))[0],
                C[1] + _rot((P[0] - C[0], P[1] - C[1]), (math.cos(sweep / 2), math.sin(sweep / 2)))[1])

    arcs = [(mid(C1, A, beta), J, rho1, C1), (mid(C2, J, beta), B, rho2, C2)]
    # rotate the local frame so that the span starts at theta_a
    cs = _cs(theta_a_deg + span_deg / 2.0)
    out = [(_rot(v, cs), _rot(e, cs), rho, _rot(c, cs)) for v, e, rho, c in arcs]
    # the end lies exactly on circle r2 at theta_a + span: use the exact value there
    ce = _cs(theta_a_deg + span_deg)
    v2, _, rho2_, c2 = out[1]
    out[1] = (v2, (r2 * ce[0], r2 * ce[1]), rho2_, c2)
    return out


def _heading_on_arc(centre, p):
    """Travel direction (deg) at p on a counter-clockwise arc around centre."""
    return math.degrees(math.atan2(p[1] - centre[1], p[0] - centre[0])) + 90.0


# ------------------------------------------------------------------ validation

def validate(p):
    """Returns (errors, warnings) as lists of strings."""
    errors, warnings = [], []
    if p.inner_diameter <= 0:
        errors.append("Inner diameter must be greater than 0.")
    if p.step <= 0:
        errors.append("Ring step E must be greater than 0.")
    if p.layer_height <= 0:
        errors.append("Layer height must be greater than 0.")
    if p.turns < 1 or p.layers < 1:
        errors.append("Turns and layers must be at least 1.")
    if p.helix and p.turns != 1:
        errors.append("The helix option needs exactly 1 turn per layer (single-wall tube).")
    if errors:
        return errors, warnings
    r0 = p.inner_diameter / 2.0
    min_r = r0 - _K * p.step if p.turns > 1 else r0      # tightest lane-change arc
    if min_r <= 0:
        errors.append("Inner diameter too small for this ring step E.")
    elif min_r < MIN_RADIUS_WARN:
        warnings.append("Smallest arc radius is %.1f mm (below %g mm): the head may not follow it well."
                        % (min_r, MIN_RADIUS_WARN))
    return errors, warnings


# ------------------------------------------------------------------ generator

def generate(p):
    """Build the motion body. Returns (items, info). Raises ValueError on invalid params."""
    errors, warnings = validate(p)
    if errors:
        raise ValueError(" ".join(errors))

    r0 = p.inner_diameter / 2.0
    radius = lambda t: r0 + p.step * t
    z_of = lambda layer: p.z0 + p.layer_height * layer
    items = []
    radii_used = set()

    def ori(heading):
        if p.auto_orient:
            return (a1(normalize_angle(heading)), p.b, p.c)
        return (p.a, p.b, p.c)

    def pt(R, deg, z):
        c, s = _cs(deg)
        return (p.xc + R * c, p.yc + R * s, z)

    def quarter(R, deg0, za, zb):
        """CIRC from angle deg0 to deg0 + 90 on radius R, Z linear from za to zb."""
        items.append(pm.Circ(pm.pose(pt(R, deg0 + 45.0, (za + zb) / 2.0)),
                             pm.pose(pt(R, deg0 + 90.0, zb), ori(deg0 + 90.0 + 90.0))))
        radii_used.add(R)

    def lane_change(R1, R2, z):
        for via, end, rho, centre in _lane_change(R1, R2, 270.0):
            items.append(pm.Circ(pm.pose((p.xc + via[0], p.yc + via[1], z)),
                                 pm.pose((p.xc + end[0], p.yc + end[1], z), ori(_heading_on_arc(centre, end)))))
            radii_used.add(rho)

    # start: PTP at angle 0 on the first ring, already pointing along the travel (+Y = 90 deg)
    start = pt(radius(0), 0.0, z_of(0))
    items.append(pm.Ptp(pm.pose(start, (a1(90.0), p.b, p.c) if p.auto_orient else (p.a, p.b, p.c),
                                PTP_S, PTP_T)))

    for layer in range(p.layers):
        outward = layer % 2 == 0
        last_layer = layer == p.layers - 1
        z = z_of(layer)
        kind = "SINGLE RING" if p.turns == 1 else ("OUTWARD SPIRAL" if outward else "INWARD SPIRAL")
        items.append(pm.Comment("===== LAYER %d ===== (%s%s)" % (layer, kind, ", HELIX" if p.helix else "")))
        order = list(range(p.turns)) if outward else list(range(p.turns - 1, -1, -1))
        for idx, t in enumerate(order):
            R = radius(t)
            items.append(pm.Comment("L%d T%d%s" % (layer, t, " - START" if layer == 0 and idx == 0 else "")))
            if p.helix and not last_layer:
                # single ring per layer: Z rises H/4 per quarter, reaching the next layer at 360 deg
                for q in range(4):
                    quarter(R, 90.0 * q, p.z0 + p.layer_height * (layer + q / 4.0),
                            p.z0 + p.layer_height * (layer + (q + 1) / 4.0))
                continue
            for q in range(3):
                quarter(R, 90.0 * q, z, z)
            if idx < len(order) - 1:
                nxt = order[idx + 1]
                items.append(pm.Comment("L%d T%d -> T%d TRANSITION (2 moves)" % (layer, t, nxt)))
                lane_change(R, radius(nxt), z)
            elif not last_layer and not p.helix:
                items.append(pm.Comment("L%d -> L%d TRANSITION (1 move)" % (layer, layer + 1)))
                quarter(R, 270.0, z, z_of(layer + 1))
            else:
                quarter(R, 270.0, z, z)

    start3, moves = pm.path_3d(items)
    info = {
        "moves": len(moves),
        "length_mm": pm.path_length(moves),
        "min_arc_radius": min(radii_used),
        "max_arc_radius": max(radii_used),
        "z_range": (z_of(0), z_of(p.layers - 1)),
        "wall_thickness": p.turns * p.step,
        "warnings": warnings,
    }
    return items, info
