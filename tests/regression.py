"""Regression test for PythonApplication6.py (Cuboid KRL generator).

Drives the real app headlessly (hidden window, dialogs patched out):
Auto-Generate Base -> Automate -> Export .src (+ Save Points), for a set of cases,
and compares the results byte-for-byte with the reference files in tests/golden/.

Usage (from the repo root or anywhere):
    python tests/regression.py            # compare against golden files
    python tests/regression.py --update   # (re)write the golden files - only when a
                                          # change of output is INTENDED and checked
Exit code 0 = all identical, 1 = differences/errors.
"""
import contextlib
import io
import math
import os
import re
import runpy
import sys
import tempfile
import tkinter as tk
from tkinter import messagebox, filedialog

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
APP = os.path.join(REPO, "PythonApplication6.py")
GOLDEN = os.path.join(HERE, "golden")
FIXTURES = os.path.join(HERE, "fixtures")   # files made by retired apps (App7 project + its export)
sys.path.insert(0, REPO)   # the app imports its sibling modules (krl_export, ...)

# name: base (Xr, Yr, Zr, L, W, tool height), automation (E, W, turns, layers),
#       tilt angle, auto-orient on/off, C_DIS on/off
CASES = {
    "REG_300x150":      dict(base=(535, 10, 65, 300, 150, 0), auto=(2, 2, 2, 1), tilt=20, orient=True,  cdis=True),
    "REG_150x300_5T":   dict(base=(535, 10, 65, 150, 300, 0), auto=(2, 2, 5, 2), tilt=20, orient=True,  cdis=True),
    "REG_20x20_E3":     dict(base=(500, 0, 50, 20, 20, 5),    auto=(3, 1, 3, 2), tilt=10, orient=True,  cdis=True),
    "REG_600x80_moved": dict(base=(450, -120, 30, 600, 80, 2), auto=(1, 1.5, 4, 1), tilt=15, orient=True, cdis=True),
    "REG_tilt_off":     dict(base=(535, 10, 65, 300, 150, 0), auto=(2, 2, 2, 1), tilt=20, orient=False, cdis=True),
    "REG_cdis_off":     dict(base=(535, 10, 65, 300, 150, 0), auto=(2, 2, 2, 1), tilt=20, orient=True,  cdis=False),
    # base may carry a 7th value: the corner radius (blank = automatic 15%)
    "REG_r40":          dict(base=(535, 10, 65, 300, 150, 0, 40), auto=(2, 2, 3, 1), tilt=20, orient=True, cdis=True),
}


# Cylinder cases (made with PythonApplication7, now run through the main app): fields + checkboxes
CYL_CASES = {
    "CYL_default":    dict(fields={}, orient=True, helix=False, cdis=True),
    "CYL_thick_5T":   dict(fields=dict(step="3", turns="5", layers="3", layer_height="1"), orient=True, helix=False, cdis=True),
    "CYL_D200_moved": dict(fields=dict(xc="400", yc="-50", z0="30", inner_diameter="200", step="2.5", turns="4",
                                       layers="2", layer_height="1.5", b="-3"), orient=True, helix=False, cdis=True),
    "CYL_helix":      dict(fields=dict(turns="1", layers="4", inner_diameter="150"), orient=True, helix=True, cdis=True),
    "CYL_orient_off": dict(fields=dict(a="170", b="5", c="175"), orient=False, helix=False, cdis=False),
}


class AppError(Exception):
    pass


# The CYL_CASES were made with the cylinder app (PythonApplication7, retired in step 5d);
# these were its defaults. They are filled in so the cases keep meaning the same print.
APP7_DEFAULTS = dict(xc="535", yc="10", z0="65", inner_diameter="100", step="2", layer_height="2",
                     turns="3", layers="2", a="180", b="20", c="180")
CYL_SHAPE_KEYS = ("xc", "yc", "z0", "inner_diameter")


def cyl_case_fields(case):
    """(cylinder shape fields, common fields) for the main app, App7 defaults filled in."""
    allf = dict(APP7_DEFAULTS, **case["fields"])
    return ({k: allf[k] for k in CYL_SHAPE_KEYS}, {k: v for k, v in allf.items() if k not in CYL_SHAPE_KEYS})


def run_cyl_case(case, tmpdir, name):
    """Cylinder cases through the main app (KRL_Generator): fields, Generate, Export -> {'src': text}."""
    errors = []
    messagebox.showerror = lambda title, msg, **k: errors.append("%s: %s" % (title, msg))
    messagebox.showwarning = lambda title, msg, **k: errors.append("WARNING %s: %s" % (title, msg))
    messagebox.showinfo = lambda *a, **k: None
    root, app = _new_main_app()
    try:
        fields, common = cyl_case_fields(case)
        src = run_main_case(app, "cylinder", fields, common,
                            dict(orient=case["orient"], helix=case["helix"], cdis=case["cdis"]), tmpdir, name)
    finally:
        root.destroy()
    if errors:
        raise AppError("; ".join(errors))
    return {"src": src}


def check_cylinder():
    """cylinder.generate on several parameter sets: every flat join tangent, climbs only kink
    by their slope, arc radii = rings or the lane-change radii, exact move/transition counts,
    Z on the layer levels and monotone, A = travel direction. Returns failure messages."""
    import cylinder as cy
    import path_model as pm
    sets = [
        dict(xc=535, yc=10, z0=65, inner_diameter=100, step=2, layer_height=2, turns=1, layers=3),
        dict(xc=535, yc=10, z0=65, inner_diameter=100, step=3, layer_height=1, turns=5, layers=4),
        dict(xc=400, yc=-50, z0=30, inner_diameter=200, step=2.5, layer_height=1.5, turns=8, layers=3),
        dict(xc=535, yc=10, z0=65, inner_diameter=150, step=2, layer_height=2, turns=1, layers=4, helix=True),
        dict(xc=0, yc=0, z0=0, inner_diameter=30, step=3, layer_height=1, turns=2, layers=2),
    ]
    bad = []
    for kw in sets:
        p = cy.CylinderParams(**kw)
        label = "D%g E%g N%d M%d%s" % (p.inner_diameter, p.step, p.turns, p.layers, " helix" if p.helix else "")
        items, info = cy.generate(p)
        motions = [i for i in items if isinstance(i, (pm.Lin, pm.Circ))]
        if len(motions) != p.layers * (5 * p.turns - 1):
            bad.append("%s: %d moves, expected %d" % (label, len(motions), p.layers * (5 * p.turns - 1)))
        pos, climb = items[0].target.xyz, []
        for m in motions:
            climb.append(abs(m.target.z - pos[2]) > 1e-12)
            pos = m.target.xyz
        for k, ang in pm.tangent_kinks(items):
            limit = 3.0 if (climb[k] or climb[k - 1]) else 1e-9
            if ang > limit:
                bad.append("%s: kink %.3g deg at move %d" % (label, ang, k))
                break
        rings = [p.inner_diameter / 2 + p.step * t for t in range(p.turns)]
        s = p.step * (1 + math.cos(math.pi / 4))          # lane-change centre offset for beta = 45 deg
        allowed = rings + [r + s for r in rings] + [r - s for r in rings] + \
                  [r + p.step - s for r in rings] + [r - p.step + s for r in rings]
        pos, worst_a = items[0].target.xyz, 0.0
        for m, cl in zip(motions, climb):
            a, b = pm._v_sub(pos, m.target.xyz), pm._v_sub(m.via.xyz, m.target.xyz)
            axb = pm._v_cross(a, b)
            centre = pm._v_add(m.target.xyz, pm._v_mul(pm._v_cross(pm._v_sub(pm._v_mul(b, pm._v_dot(a, a)),
                               pm._v_mul(a, pm._v_dot(b, b))), axb), 1.0 / (2 * pm._v_dot(axb, axb))))
            R = math.sqrt(pm._v_dot(pm._v_sub(pos, centre), pm._v_sub(pos, centre)))
            if not cl and min(abs(R - x) for x in allowed) > 1e-6 * max(1.0, R):
                bad.append("%s: unexpected arc radius %.6f" % (label, R))
                break
            t_end = pm.move_tangents(pos, m)[1]
            heading = math.degrees(math.atan2(t_end[1], t_end[0]))
            worst_a = max(worst_a, abs((m.target.a - heading + 180) % 360 - 180))
            pos = m.target.xyz
        if worst_a > 0.051:
            bad.append("%s: A off the travel direction by %.3f deg" % (label, worst_a))
        zs = [m.target.z for m in motions]
        if any(b2 < a2 - 1e-12 for a2, b2 in zip(zs, zs[1:])):
            bad.append("%s: Z not monotone" % label)
        levels = [p.z0 + p.layer_height * l for l in range(p.layers)]
        if not p.helix and any(min(abs(z - L) for L in levels) > 1e-9 for z in zs):
            bad.append("%s: an end point is off the layer levels" % label)
        n_tr = sum(m['transition'] for m in pm.path_3d(items)[1])
        exp_tr = p.layers * (p.turns - 1) * 2 + (0 if p.helix else p.layers - 1)
        if n_tr != exp_tr:
            bad.append("%s: %d transition moves in the 3D view, expected %d" % (label, n_tr, exp_tr))
        if (p.inner_diameter / 2 - p.step * 2 ** -0.5 < cy.MIN_RADIUS_WARN) != bool(info["warnings"]):
            bad.append("%s: min-radius warning wrong" % label)
    errs = cy.validate(cy.CylinderParams(0, 0, 0, 100, 2, 2, 3, 2, helix=True))[0]
    if not errs:
        bad.append("helix with 3 turns was accepted")
    return bad


def _set(entry, value):
    entry.delete(0, tk.END)
    entry.insert(0, str(value))


def run_case(case, tmpdir, name):
    """Run one case in a fresh app instance. Returns dict of output name -> text."""
    errors = []
    save_path = {"v": None}

    # Patch dialogs (the app imports the same module objects)
    messagebox.showerror = lambda title, msg, **k: errors.append("%s: %s" % (title, msg))
    messagebox.showwarning = lambda *a, **k: None
    messagebox.showinfo = lambda *a, **k: None
    filedialog.asksaveasfilename = lambda **k: save_path["v"]
    filedialog.askopenfilename = lambda **k: save_path["v"]
    tk.Tk.mainloop = lambda self, n=0: None

    with contextlib.redirect_stdout(io.StringIO()):
        g = runpy.run_path(APP, run_name="__app__")
    G = g["automate"].__globals__          # live globals (run_path returns a copy)
    root = G["root"]
    root.withdraw()
    try:
        G["tilt_along_travel_var"].set(case["orient"])
        G["c_dis_var"].set(case["cdis"])
        _set(G["tilt_entry"], case["tilt"])

        # --- Auto-Generate Base via its popup ---
        before = set(root.winfo_children())
        G["open_generate_popup"]()
        popup = [w for w in root.winfo_children() if w not in before][0]
        entries = [w for w in popup.winfo_children() if isinstance(w, tk.Entry)]
        entries.sort(key=lambda w: int(w.grid_info()["row"]))
        for entry, value in zip(entries, case["base"]):
            _set(entry, value)
        button = [w for w in popup.winfo_children() if isinstance(w, tk.Button)][0]
        button.invoke()

        out = {}
        # Save Points of the base (file format must stay stable)
        save_path["v"] = os.path.join(tmpdir, name + "_points.txt")
        G["save_points"]()
        with open(save_path["v"]) as f:
            out["points.txt"] = f.read()

        # --- Automate (twice: must be idempotent) ---
        E, W, turns, layers = case["auto"]
        _set(G["E_entry"], E)
        _set(G["W_entry"], W)
        _set(G["NumberofTurns_entry"], turns)
        _set(G["NumberofLayers_entry"], layers)
        with contextlib.redirect_stdout(io.StringIO()):
            G["automate"]()
            first = G["output_text"].get("1.0", tk.END)
            G["automate"]()
        second = G["output_text"].get("1.0", tk.END)
        if first != second:
            errors.append("Automate is not idempotent (2nd run differs)")

        # --- Export .src ---
        G["file_format_var"].set("KRL (.src)")
        save_path["v"] = os.path.join(tmpdir, name + ".src")
        G["save_krl_code"]()
        with open(save_path["v"]) as f:
            out["src"] = f.read()

        # --- Import the saved points back and regenerate the base preview ---
        G["clear_all"]()
        save_path["v"] = os.path.join(tmpdir, name + "_points.txt")
        G["import_points"]()
        out["import_preview.txt"] = G["output_text"].get("1.0", tk.END)
    finally:
        root.destroy()

    if errors:
        raise AppError("; ".join(errors))
    return out


def check_krl_export():
    """Unit checks of the shared export module. Returns a list of failure messages."""
    import krl_export as kx
    bad = []
    for name in ("REG_1", "_a", "A" * 24):
        if not kx.is_valid_program_name(name):
            bad.append("valid name rejected: %r" % name)
    for name in ("1abc", "my prog", "a-b", "", "A" * 25, "ä"):
        if kx.is_valid_program_name(name):
            bad.append("invalid name accepted: %r" % name)
    try:
        kx.build_program("bad name", "")
        bad.append("build_program accepted an invalid name")
    except ValueError:
        pass
    body = ("PTP {X 1, Y 2, Z 3}\n; comment\nLIN {X 1, Y 2, Z 3} ; keep\n"
            "CIRC {X 1, Y 1, Z 1},{X 2, Y 2, Z 2}\nLIN {X 4, Y 5, Z 6}\n")
    once = kx.add_c_dis(body)
    expected = ("PTP {X 1, Y 2, Z 3}\n; comment\nLIN {X 1, Y 2, Z 3} C_DIS ; keep\n"
                "CIRC {X 1, Y 1, Z 1},{X 2, Y 2, Z 2} C_DIS\nLIN {X 4, Y 5, Z 6}\n")
    if once != expected:
        bad.append("add_c_dis output unexpected:\n%s" % once)
    if kx.add_c_dis(once) != once:
        bad.append("add_c_dis is not idempotent")
    return bad


def check_path_model():
    """path_model: exact text round trip of every golden file, and a continuous 3D path
    with one move per LIN/CIRC line. Returns a list of failure messages."""
    import glob
    import path_model as pm
    bad = []
    files = sorted(glob.glob(os.path.join(GOLDEN, "*")))
    if not files:
        return ["no golden files to check"]
    for path in files:
        with open(path) as f:
            text = f.read()
        items = pm.parse_krl(text)
        if pm.program_to_krl(items) != text:
            bad.append("round trip changed %s" % os.path.basename(path))
        start, moves = pm.path_3d(items)
        n_lin_circ = sum(isinstance(i, (pm.Lin, pm.Circ)) for i in items)
        if len(moves) != n_lin_circ:
            bad.append("%s: %d 3D moves for %d LIN/CIRC lines" % (os.path.basename(path), len(moves), n_lin_circ))
        pos = start
        for k, m in enumerate(moves):
            # arcs start at centre + radius vector: equal to the start up to float noise
            if max(abs(u - v) for u, v in zip(m['pts'][0], pos)) > 1e-9:
                bad.append("%s: 3D path not continuous at move %d" % (os.path.basename(path), k))
                break
            pos = m['pts'][-1]
    # Hand edits in the output box are still understood (KRL is case-insensitive)
    hand = ("PTP {X 0, Y 0, Z 0, A 1, B 2, C 3, S 2., T 43.}\n   LIN {X 10, Y 0, Z 0}\n"
            "lin {x 10, y 10, z 0, a 1, b 2, c 3} c_dis\nLIN {X 0, Y 10, Z 0} ; note\n")
    if len(pm.path_3d(pm.parse_krl(hand))[1]) != 3:
        bad.append("hand-edited lines not all read")
    return bad


def _reverse_loop(points, points_circ, motion_commands):
    """Same loop travelled the other way (clockwise), starting at the old last point."""
    seq, i, j = [("P", points[0])], 1, 0
    for k in motion_commands:
        if k == "LIN":
            seq.append(("L", points[i])); i += 1
        else:
            seq += [("V", points_circ[j]), ("E", points_circ[j + 1])]; j += 2
    seq.reverse()
    P, C, M, idx = [seq[0][1]], [], [], 1
    while idx < len(seq):
        if seq[idx][0] == "V":
            C += [seq[idx][1], seq[idx + 1][1]]; M.append("CIRC"); idx += 2
        else:
            P.append(seq[idx][1]); M.append("LIN"); idx += 1
    return P, C, M


def check_shapes():
    """shapes.offset_loop: for CCW and CW rounded rectangles (incl. the r = L/2 stadium)
    every side moves out by exactly d and every arc keeps its centre with radius r + d."""
    import shapes
    bad = []
    for (L, W, r) in ((300, 150, 22.5), (150, 300, None), (20, 20, None), (4, 633, None), (600, 80, 40)):
        r = shapes.auto_corner_radius(L, W) if r is None else r
        base = shapes.rounded_rect_base(535, 10, 65, L, W, r)
        for label, loop in (("CCW", base), ("CW", _reverse_loop(*base))):
            P0, C0, M = loop
            for d in (1.0, 2.0, 7.5):
                P, C = shapes.offset_loop(P0, C0, M, d)
                xs0 = [p[0] for p in P0 + C0]; ys0 = [p[1] for p in P0 + C0]
                xs = [p[0] for p in P + C]; ys = [p[1] for p in P + C]
                shifts = (min(xs0) - min(xs), max(xs) - max(xs0), min(ys0) - min(ys), max(ys) - max(ys0))
                if max(abs(s - d) for s in shifts) > 1e-9:
                    bad.append("%dx%d %s d=%g: sides moved by %s" % (L, W, label, d, shifts))
                # arcs: start = previous point; radius must be r + d
                prev, i, j = P[0], 1, 0
                for k in M:
                    if k == "LIN":
                        prev = P[i]; i += 1
                        continue
                    c = shapes._circumcentre(prev, C[j], C[j + 1])
                    R = math.hypot(prev[0] - c[0], prev[1] - c[1])
                    if abs(R - (r + d)) > 1e-9:
                        bad.append("%dx%d %s d=%g: arc radius %.9f, expected %g" % (L, W, label, d, R, r + d))
                    prev = C[j + 1]; j += 2
    return bad


def check_profiles(tmpdir):
    """Export profiles: JSON round trip, broken-file fallback, validation, rounding precision,
    and the Export Settings dialog (edit + Save, Save as New, Delete) driven headlessly."""
    import glob
    import json
    import krl_export as kx
    import path_model as pm
    bad = []
    path = os.path.join(tmpdir, "profiles_test.json")
    # round trip (incl. decimals and a second profile)
    other = kx.settings_from_dict(dict(kx.settings_to_dict(kx.NOUVTETE), profile="Other",
                                       tool=[1, 2, 3, 4, 5, 6], decimals=3, vel_cp=0.01))
    kx.save_profiles("Other", {"NouvTete": kx.NOUVTETE, "Other": other}, path)
    active, profiles, err = kx.load_profiles(path)
    if err or active != "Other" or profiles.get("Other") != other or profiles.get("NouvTete") != kx.NOUVTETE:
        bad.append("profile JSON round trip failed (%s)" % err)
    # the built-in profile written to JSON and read back gives the identical header
    kx.save_profiles("NouvTete", {"NouvTete": kx.NOUVTETE}, path)
    if kx.build_header("X", kx.active_settings(path)[0]) != kx.build_header("X", kx.NOUVTETE):
        bad.append("header from the saved NouvTete profile differs from the built-in one")
    # broken / invalid files fall back to the built-in profile with a message
    for content in ("{not json", json.dumps({"profiles": {"P": {"tool_no": 99}}}),
                    json.dumps({"profiles": {"P": {"colour": "red"}}}), json.dumps({"profiles": {}})):
        with open(path, "w") as f:
            f.write(content)
        s, err = kx.active_settings(path)
        if not err or s != kx.NOUVTETE:
            bad.append("bad profile file not reported / no fallback: %r" % content[:30])
    if kx.active_settings(os.path.join(tmpdir, "missing.json")) != (kx.NOUVTETE, None):
        bad.append("missing profile file is not the silent built-in default")
    # rounding: same lines, every number within half a unit of the 3rd decimal
    rounded = dict(kx.settings_to_dict(kx.NOUVTETE), decimals=3)
    s3 = kx.settings_from_dict(rounded)
    num = re.compile(r"[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?")
    for f in sorted(glob.glob(os.path.join(GOLDEN, "*.src"))):
        text = open(f).read()
        body = text[text.index("$ACC_AXIS[6]=100\n") + len("$ACC_AXIS[6]=100\n"):-len("END")]
        a = kx.build_program("X", body, kx.NOUVTETE, approximate=False)
        b = kx.build_program("X", body, s3, approximate=False)
        la, lb = a.split("\n"), b.split("\n")
        if len(la) != len(lb) or [num.sub("#", x) for x in la] != [num.sub("#", y) for y in lb]:
            bad.append("%s: rounding changed more than numbers" % os.path.basename(f))
            continue
        worst = max([abs(float(x) - float(y)) for p, q in zip(la, lb) for x, y in zip(num.findall(p), num.findall(q))] or [0])
        if worst > 0.0005 + 1e-12:
            bad.append("%s: rounding moved a value by %g" % (os.path.basename(f), worst))
    # dialog: edit the TCP + decimals, Save; Save as New; Delete
    import export_settings_dialog as esd
    from tkinter import simpledialog
    msgs = []
    messagebox.showinfo = lambda *a, **k: msgs.append(("info", a[1] if len(a) > 1 else ""))
    messagebox.showerror = lambda *a, **k: msgs.append(("error", a[1] if len(a) > 1 else ""))
    messagebox.showwarning = lambda *a, **k: msgs.append(("warning", a[1] if len(a) > 1 else ""))
    messagebox.askyesno = lambda *a, **k: True
    simpledialog.askstring = lambda *a, **k: "  Test   Head "
    os.remove(path)
    root = tk.Tk()
    root.withdraw()
    try:
        d = esd.open_dialog(root, path=path)
        d.vars["tool_X"].set("12.5")
        d.vars["decimals"].set("3")
        d.save()
        active, profiles, err = kx.load_profiles(path)
        if err or profiles["NouvTete"].tool[0] != 12.5 or profiles["NouvTete"].decimals != 3:
            bad.append("dialog Save did not store the edited profile")
        d.save_as_new()
        active, profiles, err = kx.load_profiles(path)
        if active != "Test Head" or set(profiles) != {"NouvTete", "Test Head"}:
            bad.append("dialog Save as New failed: %s / %s" % (active, sorted(profiles)))
        d.vars["cdis"].set("abc")
        d.save()
        if not msgs or msgs[-1][0] != "error":
            bad.append("dialog accepted a non-number")
        d._load("Test Head")
        d.delete()
        active, profiles, err = kx.load_profiles(path)
        if set(profiles) != {"NouvTete"} or active != "NouvTete":
            bad.append("dialog Delete failed: %s" % sorted(profiles))
        d.delete()          # the last profile must stay
        if set(kx.load_profiles(path)[1]) != {"NouvTete"}:
            bad.append("the last profile was deleted")
    finally:
        root.destroy()
    return bad


def check_cuboid_params():
    """cuboid.generate (parametric, exact N, used by the main app) reproduces every auto-orient
    App6 golden .src from the parameters alone (App6's N+1 -> N, its tilt clamp applied).
    With auto-orient off the new API uses B everywhere (App6 wrote the tilt on transitions)."""
    import cuboid
    import krl_export as kx
    import path_model as pm
    bad = []
    for name, case in CASES.items():
        Xr, Yr, Zr, L, W, Th = case["base"][:6]
        r = case["base"][6] if len(case["base"]) > 6 else None
        E, H, turns, layers = case["auto"]
        tilt = max(5.0, min(float(case["tilt"]), 20.0))
        p = cuboid.CuboidParams(xc=Xr, yc=Yr, z0=float(Zr) + float(Th), length=L, width=W,
                                corner_radius=None if r is None else float(r), step=float(E), layer_height=float(H),
                                turns=turns + 1, layers=layers + 1, a=180.0, b=tilt if case["orient"] else 0.0,
                                c=180.0, auto_orient=case["orient"])
        items, info = cuboid.generate(p)
        body = pm.program_to_krl(items) + "\n" + "\n"      # as App6 exports the text box
        src = kx.build_program(name, body, kx.NOUVTETE, approximate=case["cdis"])
        golden = open(os.path.join(GOLDEN, name + ".src")).read()
        if case["orient"]:
            if src != golden:
                bad.append("%s: parametric output differs from the App6 golden (%s)" % (name, first_diff(golden, src)))
        else:
            # same moves, but B = 0 also on the transition moves
            fix = lambda t: t.replace("B 20.0", "B 0.0")
            if fix(src) != fix(golden) or "B 20.0" in src:
                bad.append("%s: orientation-off output not as expected" % name)
    return bad


def _new_main_app():
    import KRL_Generator
    root = tk.Tk()
    root.withdraw()
    return root, KRL_Generator.MainApp(root)


def run_main_case(app, shape, fields, common, opts, tmpdir, name):
    """Fill the main app like a user, Generate, export; returns the .src text."""
    app.set_shape(shape)
    for k, v in fields.items():
        app.shape_vars[shape][k].set(str(v))
    for k, v in common.items():
        app.vars[k].set(str(v))
    app.auto_orient_var.set(opts.get("orient", True))
    app.helix_var.set(opts.get("helix", False))
    app.c_dis_var.set(opts.get("cdis", True))
    if not app.generate():
        raise AppError("main app: Generate failed")
    path = os.path.join(tmpdir, name + ".src")
    if not app.export_to(path):
        raise AppError("main app: export failed")
    return open(path).read()


def check_main_app(tmpdir):
    """The all-in-one app: produces exactly the App6 (auto-orient) and App7 goldens from the
    same inputs (App6's N+1 entered as N), and its own functions work: shape switching keeps
    the values, undo/redo, comment / approach at the cursor, projects, input errors."""
    import json
    bad = []
    msgs = []
    messagebox.showinfo = lambda *a, **k: msgs.append(("info", a[1] if len(a) > 1 else ""))
    messagebox.showwarning = lambda *a, **k: msgs.append(("warning", a[1] if len(a) > 1 else ""))
    messagebox.showerror = lambda *a, **k: msgs.append(("error", a[1] if len(a) > 1 else ""))
    root, app = _new_main_app()
    try:
        # ---- same output as the old apps
        for name, case in CASES.items():
            if not case["orient"]:
                continue
            Xr, Yr, Zr, L, W, Th = case["base"][:6]
            r = case["base"][6] if len(case["base"]) > 6 else ""
            E, H, turns, layers = case["auto"]
            fields = dict(xc=Xr, yc=Yr, z0=float(Zr) + float(Th), length=L, width=W, corner_radius=r)
            common = dict(step=E, layer_height=H, turns=turns + 1, layers=layers + 1, a=180,
                          b=max(5.0, min(float(case["tilt"]), 20.0)), c=180)
            src = run_main_case(app, "cuboid", fields, common, dict(cdis=case["cdis"]), tmpdir, name)
            if src != open(os.path.join(GOLDEN, name + ".src")).read():
                bad.append("main app cuboid %s differs from the App6 golden" % name)
        for name, case in CYL_CASES.items():          # same app instance, after the cuboid cases
            fields, common = cyl_case_fields(case)
            src = run_main_case(app, "cylinder", fields, common,
                                dict(orient=case["orient"], helix=case["helix"], cdis=case["cdis"]), tmpdir, name)
            if src != open(os.path.join(GOLDEN, name + ".src")).read():
                bad.append("main app cylinder %s differs from the App7 golden" % name)
        if any(m[0] == "error" for m in msgs):
            bad.append("main app: errors while reproducing the goldens: %s" % [m for m in msgs if m[0] == "error"])

        # ---- shape switching keeps each shape's values; helix only for the cylinder
        app.set_shape("cuboid"); app.shape_vars["cuboid"]["length"].set("222")
        app.set_shape("cylinder"); app.shape_vars["cylinder"]["inner_diameter"].set("123")
        helix_shown = app.helix_check.winfo_manager() != ""
        app.set_shape("cuboid")
        if app.shape_vars["cuboid"]["length"].get() != "222" or app.shape_vars["cylinder"]["inner_diameter"].get() != "123" \
                or not helix_shown or app.helix_check.winfo_manager() != "":
            bad.append("main app: shape switching lost values or shows the wrong options")

        # ---- undo / redo
        app.undo_stack.clear(); app.redo_stack.clear()
        app.output_text.delete("1.0", tk.END)
        app.vars["turns"].set("2"); app.vars["layers"].set("1")
        app.generate()
        gen_text = app.output_text.get("1.0", "end-1c")
        app.clear()
        app.undo()
        if app.output_text.get("1.0", "end-1c") != gen_text or not app.canvas.find_all():
            bad.append("main app: undo of Clear did not restore output + top view")
        app.undo()
        if app.output_text.get("1.0", "end-1c").strip():
            bad.append("main app: undo of Generate did not restore the empty output")
        app.redo(); app.redo()
        if app.output_text.get("1.0", "end-1c").strip():
            bad.append("main app: redo did not re-apply Clear")
        app.undo()

        # ---- comment and approach at the cursor (undoable)
        app.output_text.mark_set("insert", "2.0")
        win = app.add_comment(); win.children[[k for k in win.children if "entry" in k][0]].insert(0, "my note")
        win.children[[k for k in win.children if "button" in k][0]].invoke()
        if app.output_text.get("2.0", "2.end") != "; my note":
            bad.append("main app: comment not inserted at the cursor line (%r)" % app.output_text.get("2.0", "2.end"))
        app.output_text.mark_set("insert", "1.0")
        win = app.add_approach()
        for k, v in zip("XYZ", (500, 0, 150)):
            win.vars[k].set(str(v))
        win.ok()
        abc = tuple(float(app.vars[k].get()) for k in "abc")      # pre-filled from the Orientation fields
        if app.output_text.get("1.0", "1.end") != "PTP {X 500.0, Y 0.0, Z 150.0, A %s, B %s, C %s, S 2., T 43.}" % abc:
            bad.append("main app: approach PTP wrong: %r" % app.output_text.get("1.0", "1.end"))
        app.undo(); app.undo()
        if app.output_text.get("1.0", "end-1c") != gen_text:
            bad.append("main app: undo of comment + approach failed")

        # ---- projects: own format round trip, hand edit kept, wrong app refused
        p = os.path.join(tmpdir, "main_project.json")
        app.save_project_to(p)
        root2, app2 = tk.Toplevel(root), None
        import KRL_Generator
        app2 = KRL_Generator.MainApp(root2)
        msgs.clear()
        app2.open_project_from(p)
        if app2.state() != app.state() or msgs:
            bad.append("main app: project round trip differs or gave messages (%s)" % msgs)
        app.output_text.insert("1.0", "; edited by hand\n")
        p2 = os.path.join(tmpdir, "main_project_edited.json")
        app.save_project_to(p2)
        msgs.clear()
        app2.open_project_from(p2)
        if not app2.output_text.get("1.0", "1.end").startswith("; edited by hand") or [m[0] for m in msgs] != ["info"]:
            bad.append("main app: hand-edited project output not kept / no notice")
        msgs.clear()
        before = app2.state()
        p_bad = os.path.join(tmpdir, "not_a_project.json")
        open(p_bad, "w").write('{"something": 1}')
        if app2.open_project_from(p_bad) or app2.state() != before or [m[0] for m in msgs] != ["error"]:
            bad.append("main app: a non-project JSON file was not refused cleanly")

        # ---- input errors leave everything unchanged
        before = app.state()
        for key, value in (("turns", "2.5"), ("step", "abc"), ("layers", "0")):
            old = app.vars[key].get(); app.vars[key].set(value)
            msgs.clear()
            if app.generate() or [m[0] for m in msgs] != ["error"]:
                bad.append("main app: bad %s=%r not refused" % (key, value))
            app.vars[key].set(old)
        if app.state() != before:
            bad.append("main app: a refused Generate changed the state")
    finally:
        root.destroy()
    return bad


def check_box_rounding(tmpdir):
    """Main app text box shows the values rounded like the export (profile decimals), the
    export is unchanged by that, and a change of the profile's decimals re-renders the box
    from the full-precision values unless the text was edited by hand."""
    import cuboid
    import krl_export as kx
    import path_model as pm
    bad = []
    messagebox.showinfo = messagebox.showwarning = messagebox.showerror = lambda *a, **k: None
    num = re.compile(r"-?\d+\.(\d+)")
    max_dec = lambda text: max([len(m.group(1)) for ln in text.splitlines() if ln.startswith(("LIN", "CIRC", "PTP"))
                                for m in num.finditer(ln)] or [0])
    saved_path = kx.PROFILES_PATH
    root, app = _new_main_app()
    try:
        app.generate()
        box = app.output_text.get("1.0", "end-1c")
        if max_dec(box) > 3:
            bad.append("box shows %d decimals, profile has 3" % max_dec(box))
        if kx.build_program("X", box + "\n", kx.NOUVTETE) != kx.build_program(
                "X", pm.program_to_krl(app._generated[0]) + "\n\n", kx.NOUVTETE):
            bad.append("export of the rounded box differs from the export of the full-precision text")
        # profile with 5 decimals -> re-render from the full-precision items
        five = dict(kx.settings_to_dict(kx.NOUVTETE), decimals=5)
        kx.PROFILES_PATH = os.path.join(tmpdir, "five_decimals.json")
        kx.save_profiles("NouvTete", {"NouvTete": kx.settings_from_dict(five)}, kx.PROFILES_PATH)
        app.on_profile_saved()
        box5 = app.output_text.get("1.0", "end-1c")
        p = app.read_params()
        expected = pm.program_to_krl(cuboid.generate(p)[0], decimals=5) + "\n"
        if box5 != expected or max_dec(box5) != 5:
            bad.append("box not re-rendered with 5 decimals from the full-precision values")
        if "5 decimals" not in app.info.cget("text"):
            bad.append("info line does not say how the values are shown")
        # hand edit -> no re-render
        app.output_text.insert("1.0", "; by hand\n")
        kx.save_profiles("NouvTete", {"NouvTete": kx.NOUVTETE}, kx.PROFILES_PATH)
        app.on_profile_saved()
        if not app.output_text.get("1.0", "1.end").startswith("; by hand") or max_dec(app.output_text.get("1.0", tk.END)) != 5:
            bad.append("hand-edited box was re-rendered")
    finally:
        kx.PROFILES_PATH = saved_path
        root.destroy()
    return bad


def check_frozen_mode():
    """Packaged-exe behaviour, simulated with sys.frozen: profiles next to the .exe, the
    editors started as 'exe --tool ...', and App6's Back restarting the exe."""
    import subprocess as _sp
    import sys as _sys
    import krl_export as kx
    import KRL_Generator as K
    bad = []
    fake_exe = os.path.join("C:\\", "Lab", "KRL_Generator.exe")
    saved = (_sys.executable, getattr(_sys, "frozen", None), _sys.argv, _sp.Popen)
    started = []
    try:
        _sys.frozen, _sys.executable = True, fake_exe
        if kx.app_dir() != os.path.dirname(fake_exe):
            bad.append("frozen: profiles not next to the exe (%s)" % kx.app_dir())
        if K.tool_command("PythonApplication6.py") != [fake_exe, "--tool", "manual"] or \
                K.tool_command("PythonApplication5.py") != [fake_exe, "--tool", "freeform"]:
            bad.append("frozen: wrong tool commands")
        _sys.executable = saved[0]                  # App6 must start with the real Python
        _sys.argv = ["PythonApplication6.py"]
        G = _new_app6()
        _sys.executable = fake_exe
        _sp.Popen = lambda args, **k: started.append(args)
        G["go_back_to_selector"]()
        if started != [[fake_exe]]:
            bad.append("frozen: App6 Back did not restart the exe (%s)" % started)
    finally:
        _sys.executable, frozen, _sys.argv, _sp.Popen = saved
        if frozen is None:
            del _sys.frozen
        else:
            _sys.frozen = frozen
    if K.tool_command("PythonApplication6.py")[1:] != [os.path.join(REPO, "PythonApplication6.py")]:
        bad.append("not frozen: tool command should be python + script")
    return bad


def check_old_projects(tmpdir):
    """5c: the main app opens the projects of the old apps (made by check_projects):
    App7 cylinder and App6 Auto-Generate cuboid projects reproduce their saved output exactly
    (no notice) and export the same .src; a base-only App6 project loads with a notice; a
    hand-made base is handed to the manual editor (App6 started with the project path).
    The text box shows the values rounded like the export, so it equals the saved output
    rounded the same way (the old projects were saved at full precision)."""
    import json
    import KRL_Generator
    bad = []
    msgs = []
    messagebox.showinfo = lambda *a, **k: msgs.append(("info", a[1] if len(a) > 1 else ""))
    messagebox.showwarning = lambda *a, **k: msgs.append(("warning", a[1] if len(a) > 1 else ""))
    messagebox.showerror = lambda *a, **k: msgs.append(("error", a[1] if len(a) > 1 else ""))
    root, app = _new_main_app()
    try:
        # App7 cylinder project (fixture made by App7 before it was retired) + App7's export
        msgs.clear()
        p = os.path.join(FIXTURES, "app7_cylinder_project.json")
        saved = json.load(open(p))["output"]
        if not app.open_project_from(p) or msgs or app.shape_var.get() != "cylinder" or \
                app.output_text.get("1.0", "end-1c") != app.round_text(saved):
            bad.append("old cylinder project: not opened identically (%s)" % msgs)
        app.export_to(os.path.join(tmpdir, "APP7_CYLINDER.src"))
        if open(os.path.join(tmpdir, "APP7_CYLINDER.src")).read() != open(os.path.join(FIXTURES, "APP7_CYLINDER.src")).read():
            bad.append("old cylinder project: export differs from App7's export")
        app.generate()
        if app.output_text.get("1.0", "end-1c") != app.round_text(saved):
            bad.append("old cylinder project: Generate after opening differs")
        # App6 Auto-Generate cuboid project (r 30, 250 x 120, E 2, W 1.5, turns 3 -> 4, layers 1 -> 2, tilt 15)
        msgs.clear()
        p = os.path.join(tmpdir, "cub_project.json")
        saved = json.load(open(p))["output"]
        if not app.open_project_from(p) or msgs or app.shape_var.get() != "cuboid" or \
                app.output_text.get("1.0", "end-1c") != app.round_text(saved):
            bad.append("old cuboid project: not opened identically (%s)" % msgs)
        st = app.state()
        if (st["inputs"]["cuboid"]["length"], st["inputs"]["cuboid"]["corner_radius"], st["inputs"]["common"]["turns"],
                st["inputs"]["common"]["layers"], st["inputs"]["common"]["b"]) != ("250", "30", "4", "2", "15"):
            bad.append("old cuboid project: converted values wrong: %s" % st["inputs"])
        app.generate()
        if app.output_text.get("1.0", "end-1c") != app.round_text(saved):
            bad.append("old cuboid project: Generate after opening differs")
        if "from the Cuboid" not in root.title():
            bad.append("old cuboid project: title does not say it was converted (%r)" % root.title())
        # base-only App6 project: loaded with a notice, output kept
        msgs.clear()
        p = os.path.join(tmpdir, "cub_base_only.json")
        if not app.open_project_from(p) or [m[0] for m in msgs] != ["info"] or \
                app.output_text.get("1.0", "end-1c") != json.load(open(p))["output"]:
            bad.append("base-only cuboid project: not loaded with a notice (%s)" % msgs)
        # hand-made base: offered to the manual editor
        data = json.load(open(os.path.join(tmpdir, "cub_project.json")))
        data["base_params"] = None
        p = os.path.join(tmpdir, "cub_manual_base.json")
        json.dump(data, open(p, "w"))
        started = []
        orig_popen = KRL_Generator.subprocess.Popen
        KRL_Generator.subprocess.Popen = lambda args, **k: started.append(args)
        try:
            before = app.state()
            messagebox.askyesno = lambda *a, **k: False
            if app.open_project_from(p) or app.state() != before or started:
                bad.append("manual-base project: 'No' changed something or started the editor")
            messagebox.askyesno = lambda *a, **k: True
            app.open_project_from(p)
            if len(started) != 1 or started[0][-1] != p or not started[0][1].endswith("PythonApplication6.py") \
                    or "--from-main" not in started[0]:
                bad.append("manual-base project: editor not started with the project (%s)" % started)
            started.clear()
            app.open_free_form_editor()
            if len(started) != 1 or not started[0][1].endswith("PythonApplication5.py") or "--from-main" not in started[0]:
                bad.append("free-form editor not started correctly (%s)" % started)
        finally:
            KRL_Generator.subprocess.Popen = orig_popen
    finally:
        root.destroy()
    # App6 'Back': opened from the main app -> only closes; started alone -> starts the main app
    import subprocess as _sp
    import sys as _sys
    saved_argv, orig_popen = _sys.argv, _sp.Popen
    try:
        for argv, expect_start in ((["PythonApplication6.py", "--from-main"], False), (["PythonApplication6.py"], True)):
            _sys.argv = argv
            started = []
            G = _new_app6()
            _sp.Popen = lambda args, **k: started.append(args)
            G["go_back_to_selector"]()          # closes the window
            _sp.Popen = orig_popen
            if bool(started) != expect_start or (started and not started[0][-1].endswith("KRL_Generator.py")):
                bad.append("App6 Back with argv %s: started %s" % (argv[1:], started))
    finally:
        _sys.argv, _sp.Popen = saved_argv, orig_popen
    # App6 started with a project path (as the main app does it) opens it
    _sys.argv = ["PythonApplication6.py", "--from-main", os.path.join(tmpdir, "cub_project.json")]
    try:
        G = _new_app6()
        r = G["root"]
        # run exactly the callbacks App6 scheduled at start-up (no update(): it would also run
        # stale events of earlier test windows)
        pending = r.tk.splitlist(r.tk.call("after", "info"))
        with contextlib.redirect_stdout(io.StringIO()):
            for aid in pending:
                r.tk.call(r.tk.splitlist(r.tk.call("after", "info", aid))[0])
        if not pending or not G["points"] or "===== LAYER" not in G["output_text"].get("1.0", tk.END):
            bad.append("App6 started with a project path did not open it (%d callbacks)" % len(pending))
        G["root"].destroy()
    finally:
        _sys.argv = saved_argv
    return bad


def check_heading():
    """path_model.heading_checks: auto-orient outputs keep A within 1 deg of the travel direction
    (mid and end of every move); orientation-off outputs are flagged; the chamfer-like corner of
    the old NouvTete15 print (via at 0.536 r) is flagged at about 37 deg; the 3D view draws the arrows."""
    import glob
    import path_model as pm
    bad = []
    for f in sorted(glob.glob(os.path.join(GOLDEN, "*.src"))):
        name = os.path.basename(f)
        hc = pm.heading_checks(pm.parse_krl(open(f).read()))
        worst = max(h['dev'] for h in hc)
        off = "tilt_off" in name or "orient_off" in name
        if (off and worst <= 20) or (not off and worst > 1.0):
            bad.append("%s: largest A deviation %.2f deg" % (name, worst))
    r, k = 22.5, 2 ** -0.9
    items = [pm.Ptp(pm.pose((300, 100, 0), (180, 0, 180))), pm.Lin(pm.pose((100 + r, 100, 0), (180, 0, 180))),
             pm.Circ(pm.pose((100 + r - r * k, 100 - r + r * k, 0)), pm.pose((100, 100 - r, 0), (-90, 0, 180)))]
    dev = [h['dev'] for h in pm.heading_checks(items) if h['move'] == 1 and h['where'] == 'end']
    if not dev or abs(dev[0] - 36.8) > 0.5:
        bad.append("old chamfer-like corner not flagged correctly (%s)" % dev)
    # the 3D view draws one arrow per check, in the right colours
    import view3d
    text = open(os.path.join(GOLDEN, "REG_tilt_off.src")).read()
    root = tk.Tk(); root.withdraw()
    try:
        v = view3d.View3D(root, lambda: text)
        v.arrows_var.set(True)
        v.redraw()      # no update(): it would also run stale events of the earlier test windows
        arrows = v.canvas.find_withtag("head_arrow")
        if len(arrows) != len(v.headings) or "77 red" not in v.info.cget("text"):
            bad.append("3D view: %d arrows for %d checks" % (len(arrows), len(v.headings)))
    finally:
        root.destroy()
    return bad


def _new_app6():
    tk.Tk.mainloop = lambda self, n=0: None
    with contextlib.redirect_stdout(io.StringIO()):
        g = runpy.run_path(APP, run_name="__app__")
    G = g["automate"].__globals__
    G["root"].withdraw()
    return G


def _canvas_moves(G):
    """App6 canvas content in mm: lines as (colour, start, end), dots as (colour, centre)."""
    c = G["canvas"]
    s = G["scaling_factor"] * G["view_zoom"]
    out = []
    for i in c.find_all():
        co = c.coords(i)
        if c.type(i) == "line":
            out.append((c.itemcget(i, "fill"), co[0] / s, -co[1] / s, co[-2] / s, -co[-1] / s))
        elif c.type(i) == "oval":
            out.append((c.itemcget(i, "fill"), (co[0] + co[2]) / 2 / s, -(co[1] + co[3]) / 2 / s))
    return out


def _same_drawing(a, b, tol=0.05):
    """True if every shape of a has a partner in b and vice versa (same colour, points within tol mm)."""
    def covered(x, y):
        return all(any(p[0] == q[0] and len(p) == len(q) and max(abs(u - v) for u, v in zip(p[1:], q[1:])) <= tol
                       for q in y) for p in x)
    return covered(a, b) and covered(b, a)


def check_projects(tmpdir):
    """Project files in both apps: save -> open in a fresh app gives the same output and the
    same .src; hand edits are kept (with a notice); wrong app / damaged files are refused
    without changing anything; a different export profile gives a warning; undo after open."""
    import json
    bad = []
    msgs = []
    messagebox.showinfo = lambda *a, **k: msgs.append(("info", a[1] if len(a) > 1 else ""))
    messagebox.showwarning = lambda *a, **k: msgs.append(("warning", a[1] if len(a) > 1 else ""))
    messagebox.showerror = lambda *a, **k: msgs.append(("error", a[1] if len(a) > 1 else ""))
    kinds = lambda: [m[0] for m in msgs]

    # ---------------- main app (cylinder) ----------------
    root, a = _new_main_app()
    try:
        fields, common = cyl_case_fields({"fields": dict(step="3", turns="5", layers="3", layer_height="1", b="-3")})
        run_main_case(a, "cylinder", fields, common, dict(cdis=False), tmpdir, "CYL_A")
        p1 = os.path.join(tmpdir, "main_cyl_project.json")
        a.save_project_to(p1)
        b = __import__("KRL_Generator").MainApp(tk.Toplevel(root))
        msgs.clear()
        if not b.open_project_from(p1) or kinds():
            bad.append("main cylinder: open gave messages %s" % msgs)
        if b.state() != a.state() or b.c_dis_var.get() is not False:
            bad.append("main cylinder: reopened project differs")
        b.export_to(os.path.join(tmpdir, "CYL_B.src"))
        if open(os.path.join(tmpdir, "CYL_A.src")).read().replace("CYL_A", "X") != \
                open(os.path.join(tmpdir, "CYL_B.src")).read().replace("CYL_B", "X"):
            bad.append("main cylinder: export after reopening differs")
        # hand edit is kept
        a.output_text.insert("3.0", "; my hand-written note\n")
        p2 = os.path.join(tmpdir, "main_cyl_project_edited.json")
        a.save_project_to(p2)
        msgs.clear()
        b.open_project_from(p2)
        if "; my hand-written note" not in b.output_text.get("1.0", tk.END) or kinds() != ["info"]:
            bad.append("main cylinder: hand-edited output not kept / no notice (%s)" % msgs)
        # different export profile -> warning
        data = json.load(open(p1))
        data["export_profile"]["tool"][0] = 99.0
        p3 = os.path.join(tmpdir, "main_cyl_project_profile.json")
        json.dump(data, open(p3, "w"))
        msgs.clear()
        b.open_project_from(p3)
        if kinds() != ["warning"] or "tool" not in msgs[0][1].lower():
            bad.append("main cylinder: no profile warning (%s)" % msgs)
        # damaged file: refused, nothing changed
        before = b.state()
        p4 = os.path.join(tmpdir, "damaged.json")
        open(p4, "w").write("{ not json")
        msgs.clear()
        if b.open_project_from(p4) or kinds() != ["error"] or b.state() != before:
            bad.append("main cylinder: damaged file not refused cleanly")
    finally:
        root.destroy()

    # ---------------- cuboid app ----------------
    G = _new_app6()
    try:
        before = set(G["root"].winfo_children())
        G["open_generate_popup"]()
        pop = [w for w in G["root"].winfo_children() if w not in before][0]
        ents = sorted([w for w in pop.winfo_children() if isinstance(w, tk.Entry)], key=lambda w: int(w.grid_info()["row"]))
        for e, v in zip(ents, (500, 20, 60, 250, 120, 0, 30)):
            _set(e, v)
        [w for w in pop.winfo_children() if isinstance(w, tk.Button)][0].invoke()
        base_preview = G["output_text"].get("1.0", "end-1c")
        p5 = os.path.join(tmpdir, "cub_base_only.json")
        G["save_project_to"](p5)
        for name, v in (("E_entry", 2), ("W_entry", 1.5), ("NumberofTurns_entry", 3), ("NumberofLayers_entry", 1)):
            _set(G[name], v)
        _set(G["tilt_entry"], 15)
        with contextlib.redirect_stdout(io.StringIO()):
            G["automate"]()
        out_a = G["output_text"].get("1.0", "end-1c")
        drawing_a = _canvas_moves(G)
        p6 = os.path.join(tmpdir, "cub_project.json")
        G["save_project_to"](p6)
        # Clear All -> Undo must bring back the whole automated drawing, not only the base
        G["clear_all"]()
        G["undo_action"]()
        if not _same_drawing(_canvas_moves(G), drawing_a):
            bad.append("cuboid: canvas after Clear All + Undo is not the automated drawing")
        G["output_text"].insert("2.0", "; approach / note added by hand\n")
        p7 = os.path.join(tmpdir, "cub_project_edited.json")
        G["save_project_to"](p7)
        points_a = list(G["points"])
    finally:
        G["root"].destroy()

    G = _new_app6()
    try:
        msgs.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            ok = G["open_project_from"](p6)
        if not ok or kinds() or G["output_text"].get("1.0", "end-1c") != out_a:
            bad.append("cuboid: reopened automated project differs or gave messages (%s)" % msgs)
        if [tuple(p) for p in G["points"]] != [tuple(p) for p in points_a] or \
                G["base_params"] is None or G["base_params"]["r"] != 30.0 or G["tilt_entry"].get() != "15" or \
                G["generate_popup_values"]["L"] != "250":
            bad.append("cuboid: base / parameters / fields not restored")
        if not _same_drawing(_canvas_moves(G), drawing_a):
            bad.append("cuboid: canvas after Open Project is not the automated drawing")
        G["undo_action"]()
        if G["points"] or G["output_text"].get("1.0", "end-1c").strip() or G["canvas"].find_all():
            bad.append("cuboid: undo after open did not return to the empty state")
        G["redo_action"]()       # the reported problem: Redo showed only the 11 base points
        if G["output_text"].get("1.0", "end-1c") != out_a or not _same_drawing(_canvas_moves(G), drawing_a):
            bad.append("cuboid: Redo after Undo of Open does not restore the automated drawing")
        G["undo_action"]()
        msgs.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            G["open_project_from"](p7)
        if "; approach / note added by hand" not in G["output_text"].get("1.0", tk.END) or kinds() != ["info"]:
            bad.append("cuboid: hand-edited output not kept / no notice (%s)" % msgs)
        msgs.clear()
        G["open_project_from"](p5)
        if G["output_text"].get("1.0", "end-1c") != base_preview or kinds():
            bad.append("cuboid: base-only project not restored as saved")
        before = G["output_text"].get("1.0", tk.END)
        msgs.clear()
        if G["open_project_from"](os.path.join(FIXTURES, "app7_cylinder_project.json")) or kinds() != ["error"] or \
                "Cylinder" not in msgs[0][1] or G["output_text"].get("1.0", tk.END) != before:
            bad.append("cuboid: cylinder project not refused cleanly (%s)" % msgs)
    finally:
        G["root"].destroy()
    return bad


def check_invalid_name_not_saved(tmpdir):
    """Exporting to an invalid KRL name must show an error and write nothing."""
    errors = []
    messagebox.showerror = lambda title, msg, **k: errors.append(title)
    target = os.path.join(tmpdir, "bad name.src")
    filedialog.asksaveasfilename = lambda **k: target
    tk.Tk.mainloop = lambda self, n=0: None
    with contextlib.redirect_stdout(io.StringIO()):
        g = runpy.run_path(APP, run_name="__app__")
    G = g["automate"].__globals__
    G["root"].withdraw()
    try:
        G["output_text"].insert(tk.END, "PTP {X 1, Y 2, Z 3}\n")
        G["save_krl_code"]()
    finally:
        G["root"].destroy()
    bad = []
    if errors != ["Invalid File Name"]:
        bad.append("expected one 'Invalid File Name' error, got %r" % errors)
    if os.path.exists(target):
        bad.append("a file was written for an invalid name")
    return bad


def first_diff(a, b):
    la, lb = a.splitlines(), b.splitlines()
    for i in range(max(len(la), len(lb))):
        x = la[i] if i < len(la) else "<missing>"
        y = lb[i] if i < len(lb) else "<missing>"
        if x != y:
            return "line %d\n      expected: %s\n      got:      %s" % (i + 1, x, y)
    return "(line endings / trailing whitespace only)"


def main():
    update = "--update" in sys.argv
    os.makedirs(GOLDEN, exist_ok=True)
    failed = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        # Never use the user's export_profiles.json: the apps export with the built-in profile
        import krl_export
        krl_export.PROFILES_PATH = os.path.join(tmpdir, "no_profiles_here.json")
        runs =[(n, c, run_case) for n, c in CASES.items()] + [(n, c, run_cyl_case) for n, c in CYL_CASES.items()]
        for name, case, runner in runs:
            try:
                out = runner(case, tmpdir, name)
            except Exception as ex:
                print("ERROR  %s: %s" % (name, ex))
                failed += 1
                continue
            for kind, text in out.items():
                fname = name + (".src" if kind == "src" else "_" + kind)
                path = os.path.join(GOLDEN, fname)
                if update:
                    with open(path, "w", newline="") as f:
                        f.write(text)
                    print("wrote  %s" % fname)
                    continue
                if not os.path.exists(path):
                    print("MISSING %s (run with --update first)" % fname)
                    failed += 1
                    continue
                # Default newline handling: git may check the goldens out with CRLF
                # (core.autocrlf), so line endings must not count as a difference.
                with open(path) as f:
                    expected = f.read()
                if expected == text:
                    print("ok     %s" % fname)
                else:
                    print("DIFF   %s: %s" % (fname, first_diff(expected, text)))
                    failed += 1
        for label, check in (("krl_export unit checks", check_krl_export),
                             ("path_model round trip / 3D path", check_path_model),
                             ("shapes offset (CCW + CW, exact sides and radii)", check_shapes),
                             ("cylinder geometry (tangent, radii, counts, A, Z)", check_cylinder),
                             ("export profiles + settings dialog", lambda: check_profiles(tmpdir)),
                             ("project files (both apps)", lambda: check_projects(tmpdir)),
                             ("head direction A vs travel + 3D arrows", check_heading),
                             ("cuboid.py parametric API reproduces the App6 goldens", check_cuboid_params),
                             ("main app (KRL_Generator): same output + its functions", lambda: check_main_app(tmpdir)),
                             ("main app opens old App6 / App7 projects", lambda: check_old_projects(tmpdir)),
                             ("main app text box rounded like the export", lambda: check_box_rounding(tmpdir)),
                             ("packaged-exe behaviour (simulated sys.frozen)", check_frozen_mode),
                             ("invalid file name not saved", lambda: check_invalid_name_not_saved(tmpdir))):
            problems = check()
            if problems:
                failed += len(problems)
                for p in problems:
                    print("FAIL   %s: %s" % (label, p))
            else:
                print("ok     %s" % label)
    print("\n%s" % ("ALL IDENTICAL" if not failed else "%d PROBLEM(S)" % failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
