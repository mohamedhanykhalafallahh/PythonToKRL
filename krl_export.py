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
import os
import re
from dataclasses import asdict, dataclass, field, fields
from typing import List, Optional, Tuple

import path_model as pm

PROFILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "export_profiles.json")

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


# NouvTete head (2026-11-04). TOOL value is ASSUMED (from the print variants), not yet
# verified against NouvTete15.src / the controller. BASE Z 200 is an estimate.
NOUVTETE = ExportSettings(
    profile="NouvTete",
    base_no=1,
    base=(0.0, 0.0, 200.0, 0.0, 0.0, 0.0),
    base_comment="Define base with Tool 3 - Optimized for comfortable robot positioning",
    tool_no=3,
    tool=(10.0, 0.0, 205.0, 180.0, 0.0, 0.0),
    tool_comments=[
        "Define Tool 3: NouvTete head TCP (value from the print variants, NOT yet verified - check later)",
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
      - lines that already carry an approximation (so re-exporting is safe)."""
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
        if _APPROX_RE.search(code):
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


def build_program(name, body, settings=DEFAULT_SETTINGS, approximate=True):
    """Complete .src text: header + motion body (+ C_DIS if approximate) + END.

    `body` is the generated motion text (PTP/LIN/CIRC lines and ';' comments)."""
    if not is_valid_program_name(name):
        raise ValueError("'{}' is not a valid KRL program name. {}".format(name, PROGRAM_NAME_RULE))
    if settings.decimals is not None:
        # re-write the motion lines rounded (comments and other lines stay as they are)
        body = pm.program_to_krl(pm.parse_krl(body), decimals=settings.decimals)
    if approximate:
        body = add_c_dis(body)
    return build_header(name, settings) + body + "END"


__all__ = ["ExportSettings", "NOUVTETE", "DEFAULT_SETTINGS", "PROGRAM_NAME_RULE", "PROFILES_PATH",
           "is_valid_program_name", "add_c_dis", "build_header", "build_program",
           "settings_to_dict", "settings_from_dict", "builtin_profiles", "load_profiles",
           "save_profiles", "active_settings"]
