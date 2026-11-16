"""Shared KRL (.src) export for all PythonToKRL generators.

One place for everything that is written around the generated moves:
  - the standard KUKA header (INI folds, PTP HOME),
  - BASE / TOOL data, approximation distance, velocities and accelerations,
  - C_DIS approximation on the moves,
  - the DEF-name rule (must match the file name and be a valid KRL identifier).

The generator apps only produce the motion lines (PTP / LIN / CIRC and ';' comments)
and call build_program(). Fixing a TCP, a speed or a header line here fixes it for
every app.

Export profiles: the header values live in named profiles (one per head / setup) in
export_profiles.json next to this file (synced through git). The apps edit them with the
Export Settings dialog (export_settings_dialog.py) and export with active_settings().
If the file is missing, the built-in NOUVTETE profile is used.

No tkinter in this module, so it can be tested and reused on its own.
"""
import json
import math
import os
import re
import sys
from dataclasses import asdict, dataclass, field, fields
from typing import List, Optional, Tuple

import path_model as pm

def app_dir():
    """Folder of the program: next to the .exe when packaged (PyInstaller, sys.frozen), else
    next to this file. User files (export_profiles.json) live here, never in the temporary
    folder a one-file exe unpacks itself into."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


PROFILES_PATH = os.path.join(app_dir(), "export_profiles.json")

Frame = Tuple[float, float, float, float, float, float]   # X, Y, Z, A, B, C


@dataclass(frozen=True)
class ExportSettings:
    """Everything written into the header. Numbers are written with str(), so an int
    stays an int ('50') and a float stays a float ('5.0') in the .src."""
    profile: str
    base_no: int
    base: Frame
    base_comment: str
    tool_no: int
    tool: Frame
    tool_comments: List[str] = field(default_factory=list)
    cdis: float = 5.0          # $APO.CDIS, mm: blending distance used by C_DIS
    cptp: int = 50             # $APO.CPTP, %
    vel_ptp: int = 100         # BAS(#VEL_PTP), %
    vel_cp: float = 2          # BAS(#VEL_CP), m/s (!) - 2 m/s; real speed comes from the override for now
    acc_cp: int = 100          # BAS(#ACC_CP), %
    acc_axis: int = 100        # $ACC_AXIS[1..6], %
    decimals: Optional[int] = None   # round coordinates/angles of the moves to n decimals (None = full)


# NouvTete head. Measured on 2026-11-12: TOOL by the 4-point XYZ method on the roller contact point
# (error 1.959 mm), BASE 1 by the 3-point method on the bed plate (origin = lower-left corner,
# Z 0 = roller first contact). Keep this fallback equal to export_profiles.json, so a missing
# profile file never writes the old estimates (base Z 200 / TCP X 10 Z 205).
NOUVTETE = ExportSettings(
    profile="NouvTete",
    base_no=1,
    base=(390.204, -211.408, 295.221, 0.0, -0.559, -0.196),
    base_comment="Define base 1 = bed plate (3-point with tool 3 on 2026-11-12: origin lower-left corner, X along the front edge; Z 0 = roller first contact). Old estimate was Z 200",
    tool_no=3,
    tool=(-13.941, 3.247, 186.124, 180.0, 0.0, 0.0),
    tool_comments=[
        "Define Tool 3: NouvTete head TCP = roller contact point, XYZ 4-point on 2026-11-12 (error 1.959 mm)",
        "Previous assumed value: X 10, Y 0, Z 205, A 180 (about 24 mm ahead of the roller)",
        "Old MHK head was: X -5.711, Y 128.569, Z 204.993, A 0.0, B 0.0, C 0.0",
    ],
    decimals=3,      # 0.001 mm: far below the robot's resolution; also avoids '1e-07' style numbers
)

DEFAULT_SETTINGS = NOUVTETE


# ---------------------------------------------------------------- profiles (JSON)

def settings_to_dict(s):
    d = asdict(s)
    d["base"], d["tool"] = list(s.base), list(s.tool)
    return d


def settings_from_dict(d):
    """ExportSettings from a dict (e.g. JSON). Unknown keys are an error; missing optional
    keys take their defaults. Raises ValueError with a readable message."""
    known = {f.name for f in fields(ExportSettings)}
    unknown = set(d) - known
    if unknown:
        raise ValueError("unknown setting(s): %s" % ", ".join(sorted(unknown)))
    d = dict(d)
    try:
        for key in ("base", "tool"):
            if key in d:
                frame = tuple(float(v) for v in d[key])
                if len(frame) != 6:
                    raise ValueError("%s needs 6 values (X, Y, Z, A, B, C)" % key)
                d[key] = frame
        if "tool_comments" in d:
            d["tool_comments"] = [str(c) for c in d["tool_comments"]]
        s = ExportSettings(**d)
    except TypeError as ex:
        raise ValueError(str(ex))
    if not (1 <= int(s.tool_no) <= 16) or not (1 <= int(s.base_no) <= 32):
        raise ValueError("tool number must be 1..16 and base number 1..32")
    if s.decimals is not None and not (0 <= int(s.decimals) <= 6):
        raise ValueError("decimals must be 0..6 (or empty for full precision)")
    return s


def builtin_profiles():
    """(active name, {name: ExportSettings}) used when no profile file exists."""
    return NOUVTETE.profile, {NOUVTETE.profile: NOUVTETE}


def load_profiles(path=None):
    """Read the profile file. Returns (active_name, profiles, error). On any problem the
    built-in profiles are returned and `error` says what was wrong (None if all is well;
    a missing file is not an error)."""
    path = path or PROFILES_PATH
    if not os.path.exists(path):
        active, profiles = builtin_profiles()
        return active, profiles, None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        profiles = {}
        for name, d in data["profiles"].items():
            d = dict(d)
            d["profile"] = name
            profiles[name] = settings_from_dict(d)
        if not profiles:
            raise ValueError("the file has no profiles")
        active = data.get("active")
        if active not in profiles:
            active = sorted(profiles)[0]
        return active, profiles, None
    except Exception as ex:
        active, profiles = builtin_profiles()
        return active, profiles, "Could not read %s (%s). Using the built-in %s profile." % (
            os.path.basename(path), ex, active)


def save_profiles(active, profiles, path=None):
    """Write the profile file (pretty JSON). `profiles` maps name -> ExportSettings."""
    path = path or PROFILES_PATH
    data = {"active": active,
            "profiles": {name: {k: v for k, v in settings_to_dict(s).items() if k != "profile"}
                         for name, s in sorted(profiles.items())}}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def active_settings(path=None):
    """(ExportSettings of the active profile, error message or None)."""
    active, profiles, error = load_profiles(path)
    return profiles[active], error


# ---------------------------------------------------------------- program name

PROGRAM_NAME_RULE = ("Use only letters, digits and '_' (no spaces or '-'), "
                     "start with a letter, max 24 characters.")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,23}")


def is_valid_program_name(name):
    """The DEF name must match the file name AND be a valid KRL identifier
    (letters, digits, underscore; not starting with a digit; max 24 chars)."""
    return bool(_NAME_RE.fullmatch(name))


# ---------------------------------------------------------------- approximation

_MOTION_RE = re.compile(r"^\s*(PTP|LIN|CIRC)\s*\{")
_APPROX_RE = re.compile(r"\bC_(DIS|PTP|VEL|ORI)\b")


def add_c_dis(krl_code):
    """Append ' C_DIS' to every LIN/CIRC motion line so the robot blends through the
    points instead of stopping at each one (distance set by $APO.CDIS in the header).

    Not approximated:
      - PTP lines (the start must be reached exactly before printing begins),
      - the very last motion of the program (the print ends exactly on its last point),
      - lines that already carry an approximation (so re-exporting is safe),
      - lines with the comment '; exact stop' (the touch-down and the end of the print, when the
        approach / retract moves are added)."""
    lines = krl_code.split("\n")
    motion_idx = [i for i, ln in enumerate(lines) if _MOTION_RE.match(ln)]
    if not motion_idx:
        return krl_code
    last = motion_idx[-1]
    for i in motion_idx:
        ln = lines[i]
        if i == last or ln.lstrip().startswith("PTP"):
            continue
        # Keep any trailing ';' comment after the approximation keyword
        code, sep, comment = ln.partition(";")
        if _APPROX_RE.search(code) or "exact stop" in comment.lower():
            continue
        lines[i] = code.rstrip() + " C_DIS" + ((" " + sep + comment) if sep else "")
    return "\n".join(lines)


# ---------------------------------------------------------------- header / program

def _frame(f):
    return "X {}, Y {}, Z {}, A {}, B {}, C {}".format(*(float(v) for v in f))


def build_header(name, settings=DEFAULT_SETTINGS):
    """Header from &ACCESS down to the last setting line (ends with a newline)."""
    s = settings
    lines = [
        "&ACCESS RVP",
        "&REL 299",
        "&PARAM EDITMASK = *",
        "&PARAM TEMPLATE = C:\\KRC\\Roboter\\Template\\vorgabe",
        "&PARAM DISKPATH = KRC:\\R1\\Program",
        "DEF {}( )".format(name),
        ";FOLD INI;%{PE}",
        "  ;FOLD BASISTECH INI",
        "    GLOBAL INTERRUPT DECL 3 WHEN $STOPMESS==TRUE DO IR_STOPM ( )",
        "    INTERRUPT ON 3 ",
        "    BAS (#INITMOV,0 )",
        "  ;ENDFOLD (BASISTECH INI)",
        "  ;FOLD SPOTTECH INI",
        "    USERSPOT(#INIT)",
        "  ;ENDFOLD (SPOTTECH INI)",
        "  ;FOLD GRIPPERTECH INI",
        "    USER_GRP(0,DUMMY,DUMMY,GDEFAULT)",
        "  ;ENDFOLD (GRIPPERTECH INI)",
        "  ;FOLD USER INI",
        "    ;Make your modifications here",
        "  ;ENDFOLD (USER INI)",
        ";ENDFOLD (INI)",
        ";FOLD PTP HOME  Vel= 100 % DEFAULT;%{PE}%MKUKATPBASIS,%CMOVE,%VPTP,%P 1:PTP, 2:HOME, 3:, 5:100, 7:DEFAULT",
        "$BWDSTART = FALSE",
        "PDAT_ACT=PDEFAULT",
        "FDAT_ACT=FHOME",
        "BAS (#PTP_PARAMS,100 )",
        "$H_POS=XHOME",
        "PTP  XHOME",
        ";ENDFOLD",
        "; Export profile: " + s.profile,
        "; " + s.base_comment,
        "BASE_DATA[{}] = {{{}}}".format(s.base_no, _frame(s.base)),
        "$BASE = BASE_DATA[{}]".format(s.base_no),
    ]
    lines += ["; " + c for c in s.tool_comments]
    lines += [
        "TOOL_DATA[{}] = {{{}}}".format(s.tool_no, _frame(s.tool)),
        "$TOOL = TOOL_DATA[{}]".format(s.tool_no),
        "; Set frame data for proper tool usage",
        "FDAT_ACT = {{TOOL_NO {}, BASE_NO {}, IPO_FRAME #BASE}}".format(s.tool_no, s.base_no),
        "; Set approximation for smooth motion",
        "$APO.CDIS = {}".format(s.cdis),
        "$APO.CPTP = {}".format(s.cptp),
        "; Velocities and accelerations",
        "BAS (#VEL_PTP, {})".format(s.vel_ptp),
        "BAS (#VEL_CP, {})".format(s.vel_cp),
        "BAS (#ACC_CP, {})".format(s.acc_cp),
    ]
    lines += ["$ACC_AXIS[{}]={}".format(i, s.acc_axis) for i in range(1, 7)]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- spline motion (optional)

SPLINE_ARC_STEP = 15.0     # deg: an arc becomes SPL points at most this far apart ...
SPLINE_MAX_STEP = 25.0     # mm:  ... and at most this far apart along the arc
SPLINE_MIN_SLIN = 10.0     # mm:  a straight at least this long stays an exact straight (SLIN)
SPLINE_SMOOTH = (0.5, 15.0)   # deg: two straights meeting between these angles are part of a curve (SPL)
SPLINE_NOTE = "Spline motion: SLIN = exact straights, SPL = points on the curves (KSS 8.2 or newer)"


def to_spline(body, decimals=None):
    """The same path written as KUKA spline blocks instead of LIN / CIRC with C_DIS.

        SPLINE
          SLIN {...}        a straight
          SPL {...}         a point the curve passes through
        ENDSPLINE

    Why: inside a spline block the controller plans ONE smooth path through all points and keeps
    the programmed speed along it; nothing is rounded off as C_DIS does. KUKA's rule for it is
    followed here: straights are SLIN, everything curved is a row of SPL points. (Chains of SLIN
    and SCIRC would be exact too, but the robot slows down or stops at every joint between them,
    so arcs are written as SPL points ON the arc, at most 15 deg and 25 mm apart, with A, B, C
    going evenly from the start to the end of the arc.)

      - a LIN stays a straight (SLIN) if it is 10 mm or longer and does not meet another LIN at a
        small angle (0.5 .. 15 deg: then both are pieces of a curve and become SPL points); a
        real corner (above 15 deg) keeps its two SLIN, and the robot stops in the corner.
      - PTP lines, the approach from above and the lift at the end stay as they are; the block
        ends on the last point of the print (an exact stop).
      - comments stay where they are; any other line ends the block before it.

    NOT TRIED ON THE ROBOT. Run a new program without fiber first."""
    items = pm.parse_krl(body)
    # the moves, with where they start and their directions, to decide SLIN or SPL
    moves, pos = {}, None
    order = []
    for k, item in enumerate(items):
        if isinstance(item, pm.Ptp):
            pos = item.target
        elif isinstance(item, (pm.Lin, pm.Circ)) and pos is not None:
            t = pm.move_tangents(pos.xyz, item)
            moves[k] = (pos, t)
            order.append(k)
            pos = item.target
    aux = set()                                           # approach / lift LINs: left as plain LIN
    mark = False
    for k, item in enumerate(items):
        if isinstance(item, pm.Comment) and ("APPROACH:" in item.text or "RETRACT:" in item.text):
            mark = True
        elif isinstance(item, pm.Lin) and mark:
            aux.add(k)
            mark = False

    def kink(k_a, k_b):
        """Angle (deg) between the end of move k_a and the start of move k_b."""
        ta, tb = moves[k_a][1], moves[k_b][1]
        if not ta or not tb:
            return 0.0
        a, b = ta[1], tb[0]
        cr = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
        return math.degrees(math.atan2(math.sqrt(sum(c * c for c in cr)), sum(x * y for x, y in zip(a, b))))

    def is_straight(k):
        start, item = moves[k][0], items[k]
        if math.sqrt(sum((p - q) ** 2 for p, q in zip(start.xyz, item.target.xyz))) < SPLINE_MIN_SLIN:
            return False
        i = order.index(k)
        for other, first in ((order[i - 1] if i > 0 else None, True), (order[i + 1] if i + 1 < len(order) else None, False)):
            if other is None or other in aux or not isinstance(items[other], pm.Lin):
                continue
            ang = kink(other, k) if first else kink(k, other)
            if SPLINE_SMOOTH[0] < ang < SPLINE_SMOOTH[1]:
                return False
        return True

    def lerp_pose(a, b, f, xyz):
        def mix(u, v, angle=False):
            if u is None or v is None:
                return v
            return u + (pm.angle_diff(u, v) if angle else (v - u)) * f
        ang = mix(a.a, b.a, True)
        if ang is not None:
            ang = (ang + 180.0) % 360.0 - 180.0
        return pm.Pose(xyz[0], xyz[1], xyz[2], ang, mix(a.b, b.b, True), mix(a.c, b.c, True))

    out, in_block, noted = [], False, False

    def close():
        if out and in_block:
            out.append("ENDSPLINE")
        return False
    for k, item in enumerate(items):
        if k in moves and k not in aux:
            start = moves[k][0]
            if not in_block:
                if not noted:
                    out.append("; " + SPLINE_NOTE)
                    noted = True
                out.append("SPLINE")
                in_block = True
            end = pm.Pose(item.target.x, item.target.y, item.target.z, item.target.a, item.target.b, item.target.c)
            if isinstance(item, pm.Lin):
                out.append("  %s %s" % ("SLIN" if is_straight(k) else "SPL", end.to_krl(decimals)))
            else:
                fr = pm._arc_frame(start.xyz, item.via.xyz, item.target.xyz)
                if fr is None:                            # three points on a line: a straight
                    out.append("  SPL %s" % end.to_krl(decimals))
                else:
                    c, rad, e1, e2, sweep = fr
                    n = max(1, int(math.ceil(abs(math.degrees(sweep)) / SPLINE_ARC_STEP - 1e-9)),
                            int(math.ceil(rad * abs(sweep) / SPLINE_MAX_STEP - 1e-9)))
                    for j in range(1, n + 1):
                        t = sweep * j / n
                        xyz = tuple(c[i] + rad * (e1[i] * math.cos(t) + e2[i] * math.sin(t)) for i in range(3))
                        pose_j = end if j == n else lerp_pose(start, end, j / float(n), xyz)
                        out.append("  SPL %s" % pose_j.to_krl(decimals))
            if (item.note or "").strip().lower() == "exact stop":
                in_block = close()
            continue
        line = item.to_krl(decimals)
        if in_block and not (isinstance(item, pm.Comment) or line.strip() == "" or line.lstrip().startswith(";")):
            in_block = close()                            # PTP, the lift, or a hand-written statement
        out.append(("  " + line) if in_block and line.strip() else line)
    if in_block:                                          # close before trailing blank lines
        tail = []
        while out and out[-1].strip() == "":
            tail.append(out.pop())
        out.append("ENDSPLINE")
        out.extend(tail)
    return "\n".join(out)


def build_program(name, body, settings=DEFAULT_SETTINGS, approximate=True, spline=False):
    """Complete .src text: header + motion body (+ C_DIS if approximate) + END.

    `body` is the generated motion text (PTP/LIN/CIRC lines and ';' comments). With `spline`
    the moves are written as spline blocks (to_spline) and C_DIS is not used."""
    if not is_valid_program_name(name):
        raise ValueError("'{}' is not a valid KRL program name. {}".format(name, PROGRAM_NAME_RULE))
    if spline:
        return build_header(name, settings) + to_spline(body, settings.decimals) + "END"
    if settings.decimals is not None:
        # re-write the motion lines rounded (comments and other lines stay as they are)
        body = pm.program_to_krl(pm.parse_krl(body), decimals=settings.decimals)
    if approximate:
        body = add_c_dis(body)
    return build_header(name, settings) + body + "END"


__all__ = ["ExportSettings", "NOUVTETE", "DEFAULT_SETTINGS", "PROGRAM_NAME_RULE", "PROFILES_PATH",
           "is_valid_program_name", "add_c_dis", "to_spline", "build_header", "build_program",
           "settings_to_dict", "settings_from_dict", "builtin_profiles", "load_profiles",
           "save_profiles", "active_settings"]
