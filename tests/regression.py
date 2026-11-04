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


# Cylinder app (PythonApplication7): input fields as typed in the GUI, plus checkboxes
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


def run_cyl_case(case, tmpdir, name):
    """Cylinder app: set the fields, Generate, Export. Returns {'src': text}."""
    errors = []
    messagebox.showerror = lambda title, msg, **k: errors.append("%s: %s" % (title, msg))
    messagebox.showwarning = lambda title, msg, **k: errors.append("WARNING %s: %s" % (title, msg))
    messagebox.showinfo = lambda *a, **k: None
    import PythonApplication7 as app7
    root = tk.Tk()
    root.withdraw()
    try:
        app = app7.CylinderApp(root)
        for key, value in case["fields"].items():
            app.vars[key].set(value)
        app.auto_orient_var.set(case["orient"])
        app.helix_var.set(case["helix"])
        app.c_dis_var.set(case["cdis"])
        if not app.generate():
            raise AppError("Generate failed")
        path = os.path.join(tmpdir, name + ".src")
        if not app.export_to(path):
            raise AppError("Export failed")
        with open(path) as f:
            out = {"src": f.read()}
    finally:
        root.destroy()
    if errors:
        raise AppError("; ".join(errors))
    return out


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
