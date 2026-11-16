"""Checks for the free-form import and the robot transfer (used by regression.py).

    IMPORT_CASES / run_import_case     design file -> main app -> .src, against tests/golden/IMP_*.src
    check_contours()                   offsets, corner rounding, LIN / CIRC fitting (exact shapes)
    check_import_formats()             SVG / DXF / STL readers, units, error messages
    check_freeform()                   the generator: connected, tangent, A along the travel, Z rising
    check_main_import(tmpdir)          the main app: import, project round trip, undo, errors
    check_robot_link(tmpdir)           transfer folder: settings, checks, send + read back, app flow
Each check returns a list of problems (empty = ok).
"""
import math
import os
import tkinter as tk
from tkinter import messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
DESIGNS = os.path.join(HERE, "fixtures", "designs")

# name: design file, import fields, common fields, options
IMPORT_CASES = {
    "IMP_svg_blob":      dict(file="blob.svg", fields={}, common={}, opts={}),
    "IMP_dxf_plate_in":  dict(file="plate.dxf", fields=dict(rotation="30", scale="1.2", xc="140", yc="200"),
                              common=dict(turns="2", layers="2", step="2.5"), opts=dict(inward=True)),
    "IMP_stl_cone":      dict(file="cone.stl", fields=dict(z0="5"), common=dict(turns="2", layers="4"), opts={}),
    "IMP_svg_orient_off": dict(file="corners_px.svg", fields=dict(corner_radius="25"),
                              common=dict(a="170", b="5", c="175", layers="2"), opts=dict(orient=False, cdis=False)),
}


def design(name):
    return os.path.join(DESIGNS, name)


def _quiet():
    msgs = []
    messagebox.showinfo = lambda *a, **k: msgs.append(("info", a[1] if len(a) > 1 else ""))
    messagebox.showwarning = lambda *a, **k: msgs.append(("warning", a[1] if len(a) > 1 else ""))
    messagebox.showerror = lambda *a, **k: msgs.append(("error", a[1] if len(a) > 1 else ""))
    return msgs


def _new_main_app(approach=False):
    import KRL_Generator
    root = tk.Tk()
    root.withdraw()
    app = KRL_Generator.MainApp(root)
    app.approach_var.set(approach)  # the goldens are the bare print (no approach / retract moves)
    return root, app


def run_import_case(case, tmpdir, name):
    """Design file through the main app: fields, Generate, Export -> {'src': text}."""
    msgs = _quiet()
    root, app = _new_main_app()
    try:
        app.set_shape("import")
        app.shape_vars["import"]["file"].set(design(case["file"]))
        for k, v in case["fields"].items():
            app.shape_vars["import"][k].set(v)
        for k, v in case["common"].items():
            app.vars[k].set(v)
        app.auto_orient_var.set(case["opts"].get("orient", True))
        app.c_dis_var.set(case["opts"].get("cdis", True))
        app.inward_var.set(case["opts"].get("inward", False))
        if not app.generate():
            raise RuntimeError("Generate failed: %s" % msgs)
        path = os.path.join(tmpdir, name + ".src")
        if not app.export_to(path):
            raise RuntimeError("export failed: %s" % msgs)
        with open(path) as f:
            return {"src": f.read()}
    finally:
        root.destroy()


# ---------------------------------------------------------------------- geometry

def _rrect(L, W, r):
    import contours as ct
    pts = []
    for cx, cy, a0 in ((L / 2 - r, W / 2 - r, 0), (-L / 2 + r, W / 2 - r, 90), (-L / 2 + r, -W / 2 + r, 180),
                       (L / 2 - r, -W / 2 + r, 270)):
        pts += ct.flatten_arc((cx, cy), r, math.radians(a0), math.pi / 2)
    return ct.normalize(pts)


def check_contours():
    import contours as ct
    bad = []

    def near(what, got, want, tol):
        if abs(got - want) > tol:
            bad.append("%s: %.5f, expected %.5f" % (what, got, want))

    rr = _rrect(150, 300, 22.5)
    for d in (2.0, 4.0, 10.0, -2.0, -10.0, -30.0):
        loops = ct.offset(rr, d)
        if len(loops) != 1:
            bad.append("rounded rectangle offset %g: %d outlines" % (d, len(loops)))
            continue
        r = 22.5 + d
        exact = (150 + 2 * d) * (300 + 2 * d) - ((4 - math.pi) * r * r if r > 0 else 0.0)
        near("rounded rectangle offset %g area" % d, ct.area(loops[0]), exact, 0.4)
        dists = [ct.closest_point(rr, p)[3] for p in loops[0][::7]]
        if min(dists) < abs(d) - 0.005 or max(dists) > abs(d) + 0.005:
            bad.append("rounded rectangle offset %g: distance %.4f..%.4f" % (d, min(dists), max(dists)))
    if ct.offset(rr, -80.0):
        bad.append("an inward offset larger than the shape must give nothing")
    sq = ct.normalize([(0, 0), (100, 0), (100, 60), (0, 60)])
    near("square + 5 area (round corners)", ct.area(ct.offset_one(sq, 5.0)), 6000 + 2 * 5 * 160 + math.pi * 25, 0.1)
    near("square - 5 area (sharp corners)", ct.area(ct.offset_one(sq, -5.0)), 90 * 50, 1e-6)
    near("clockwise input is turned counter-clockwise", ct.area(ct.normalize(sq[::-1])), 6000, 1e-9)
    # a U whose slot (40 wide) closes when the offset is larger than 20; an L; inward split / vanish
    U = ct.normalize([(0, 0), (100, 0), (100, 100), (70, 100), (70, 30), (30, 30), (30, 100), (0, 100)])
    for d in (5.0, 19.0, 21.0, 40.0):
        loops = ct.offset(U, d)
        if not loops:
            bad.append("U offset %g gave nothing" % d)
            continue
        dists = [ct.closest_point(U, p)[3] for p in loops[0][::5]]
        if min(dists) < d - 0.01:
            bad.append("U offset %g comes as close as %.4f to the outline" % (d, min(dists)))
        want_slot = d < 20
        has_slot = any(40 < p[0] < 60 and 30 < p[1] < 100 for p in loops[0])
        if want_slot != has_slot:
            bad.append("U offset %g: slot %s" % (d, "missing" if want_slot else "should be closed"))
    if ct.offset(U, -16.0):
        bad.append("U - 16 must vanish (arms are 30 wide)")
    try:
        ct.offset_one(U, -16.0)
        bad.append("offset_one must raise when nothing is left")
    except ct.GeometryError:
        pass
    # corner rounding
    near("round_corners square r 10 area", ct.area(ct.round_corners(sq, 10.0)), 6000 - (4 - math.pi) * 100, 0.3)
    # points -> LIN / CIRC: exact pieces come back
    for d, radius in ((0.0, 22.5), (2.0, 24.5), (6.0, 28.5)):
        poly = ct.reseam(rr if d == 0 else ct.offset_one(rr, d), (75 + d, 0))
        moves = ct.fit_moves(poly + [poly[0]])
        kinds = "".join(m[0] for m in moves)
        if kinds != "LCLCLCLCL":
            bad.append("fit of the rounded rectangle + %g: %s" % (d, kinds))
        for m in moves:
            if m[0] == 'C' and abs(m[4] - radius) > 0.01:
                bad.append("fit radius %.4f, expected %.4f" % (m[4], radius))
    circle = ct.normalize(ct.flatten_arc((10, 20), 50, 0, 2 * math.pi))
    moves = ct.fit_moves(circle + [circle[0]])
    if any(m[0] != 'C' or abs(m[4] - 50) > 0.01 for m in moves) or len(moves) != 4:
        bad.append("fit of a circle: %s" % [(m[0], round(m[-1], 3) if m[0] == 'C' else None) for m in moves])
    if "".join(m[0] for m in ct.fit_moves(sq + [sq[0]])) != "LLLL":
        bad.append("fit of a square must be 4 LIN")
    # loose pieces -> outlines
    closed, opened = ct.chain_segments([[(0, 0), (10, 0)], [(10, 10), (10, 0)], [(10, 10), (0, 10)], [(0, 0), (0, 10)],
                                        [(50, 50), (60, 50)], [(60, 50), (60, 60)]])
    if len(closed) != 1 or len(closed[0]) != 4 or len(opened) != 1 or len(opened[0]) != 3:
        bad.append("chain_segments: %d closed, %d open" % (len(closed), len(opened)))
    return bad


# ---------------------------------------------------------------------- file readers

def check_import_formats(tmpdir):
    import contours as ct
    import import_formats as imf
    bad = []

    def near(what, got, want, tol=0.01):
        if abs(got - want) > tol:
            bad.append("%s: %.4f, expected %.4f" % (what, got, want))

    d = imf.load_design(design("blob.svg"))
    if d.kind != "2d" or len(d.outlines) != 2 or d.open_paths or d.notes:
        bad.append("blob.svg: %s, notes %s" % (d.describe(), d.notes))
    else:
        near("blob.svg circle area (2nd outline)", ct.area(d.outlines[1]), math.pi * 25, 0.05)
        if ct.area(d.outlines[0]) < 10000 or any(ct.area(o) <= 0 for o in d.outlines):
            bad.append("blob.svg: outlines must be counter-clockwise, largest first")
    d = imf.load_design(design("corners_px.svg"))
    px = 25.4 / 96.0
    if len(d.outlines) != 2 or len(d.open_paths) != 1 or not any("96 px" in n for n in d.notes):
        bad.append("corners_px.svg: %s, notes %s" % (d.describe(), d.notes))
    else:
        near("corners_px.svg rectangle area (px -> mm)", ct.area(d.outlines[0]), 400 * 300 * px * px, 0.01)
        near("corners_px.svg path with an arc", ct.area(d.outlines[1]),
             (70 * 60 - (1 - math.pi / 4) * 400) * px * px, 0.05)
    d = imf.load_design(design("plate.dxf"))
    if len(d.outlines) != 2 or d.open_paths:
        bad.append("plate.dxf: %s" % d.describe())
    else:
        near("plate.dxf stadium area (lines + arcs joined)", ct.area(d.outlines[0]), 100 * 60 + math.pi * 900, 0.4)
        near("plate.dxf hole area", ct.area(d.outlines[1]), math.pi * 144, 0.15)
        near("plate.dxf width", d.size[0], 160.0, 0.005)
    d = imf.load_design(design("rounded_inch.dxf"))
    if len(d.outlines) != 1 or not any("mm" in n for n in d.notes):
        bad.append("rounded_inch.dxf: %s, notes %s" % (d.describe(), d.notes))
    else:
        near("rounded_inch.dxf size (inch -> mm)", d.size[0], 101.6, 0.001)
        near("rounded_inch.dxf area (bulges)", ct.area(d.outlines[0]),
             (16 - (4 - math.pi) * 0.64) * 25.4 * 25.4, 0.3)
    d = imf.load_design(design("cone.stl"))
    if d.kind != "3d" or len(d.triangles) != 256 or abs(d.height - 12.0) > 1e-6:
        bad.append("cone.stl: %s" % d.describe())
    else:
        for h, r in ((1.0, 58.75), (6.0, 52.5), (11.0, 46.25)):
            loops = imf.slice_mesh(d, [h])[0]
            if len(loops) != 1 or len(loops[0]) != 64:
                bad.append("cone.stl slice at %g: %d outlines" % (h, len(loops)))
            else:
                near("cone.stl slice radius at %g" % h, max(math.hypot(*p) for p in loops[0]), r, 1e-3)
    d = imf.load_design(design("box_ascii.stl"))
    loops = imf.slice_mesh(d, [3.0])[0] if d.kind == "3d" else []
    if len(loops) != 1 or len(loops[0]) != 4 or abs(ct.area(loops[0]) - 9600) > 1e-6:
        bad.append("box_ascii.stl: slice %s" % [len(l) for l in loops])
    # files that cannot be used: a clear message, never a crash
    cases = {"empty.svg": '<svg xmlns="http://www.w3.org/2000/svg"></svg>',
             "broken.svg": '<svg><path d="M 0 0 L',
             "nothing.dxf": "0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n",
             "text.dxf": "this is not a dxf\nat all\n",
             "bad.stl": "hello",
             "part.step": "ISO-10303-21;",
             "drawing.pdf": "x"}
    for name, text in cases.items():
        path = os.path.join(tmpdir, name)
        with open(path, "w") as f:
            f.write(text)
        try:
            imf.load_design(path)
            bad.append("%s should be refused" % name)
        except imf.ImportError_ as ex:
            if len(str(ex)) < 15:
                bad.append("%s: message too short: %s" % (name, ex))
        except Exception as ex:
            bad.append("%s: %s instead of a readable message: %s" % (name, type(ex).__name__, ex))
    try:
        imf.load_design(os.path.join(tmpdir, "missing.svg"))
        bad.append("a missing file should be refused")
    except imf.ImportError_:
        pass
    return bad


# ---------------------------------------------------------------------- generator

def check_freeform():
    import freeform as ff
    import import_formats as imf
    import path_model as pm
    bad = []
    base = dict(xc=150, yc=225, z0=10, step=2, layer_height=2, turns=3, layers=3)
    cases = [("blob.svg", {}, 2.5, 1.5), ("blob.svg", dict(inward=True, turns=5), 3.0, 2.0),
             ("plate.dxf", {}, 2.0, 1.5), ("plate.dxf", dict(inward=True, turns=4, rotation=40.0, scale=1.5), 2.5, 1.5),
             ("rounded_inch.dxf", dict(turns=1, layers=5), 2.0, 1.5),
             ("corners_px.svg", dict(corner_radius=25.0), 2.0, 1.5),
             ("cone.stl", dict(layers=6), 6.5, 3.5), ("box_ascii.stl", dict(corner_radius=22.5), 4.5, 3.0)]
    for fname, extra, max_kink, max_dev in cases:
        label = "%s %s" % (fname, extra)
        d = imf.load_design(design(fname))
        args = dict(base, design=d)
        args.update(extra)
        p = ff.FreeformParams(**args)
        if ff.validate(p)[0]:
            bad.append("%s: validate: %s" % (label, ff.validate(p)[0]))
            continue
        try:
            items, info = ff.generate(p)
        except ValueError as ex:
            bad.append("%s: %s" % (label, ex))
            continue
        text = pm.program_to_krl(items)
        if pm.program_to_krl(pm.parse_krl(text)) != text:
            bad.append("%s: text does not round-trip" % label)
        start, moves = pm.path_3d(items)
        pos, zs = start, []
        for m in moves:
            if math.sqrt(sum((a - b) ** 2 for a, b in zip(pos, m['pts'][0]))) > 1e-9:
                bad.append("%s: path not connected" % label)
                break
            pos = m['pts'][-1]
            zs.append(pos[2])
        if any(b < a - 1e-9 for a, b in zip(zs, zs[1:])):
            bad.append("%s: Z goes down" % label)
        n_layers = info["layers"]
        if abs(zs[-1] - (10 + 2 * (n_layers - 1))) > 1e-9 or abs(start[2] - 10) > 1e-9:
            bad.append("%s: Z range %.3f..%.3f for %d layers" % (label, start[2], zs[-1], n_layers))
        if info["max_kink_deg"] > max_kink:
            bad.append("%s: corner of %.2f deg (limit %.1f)" % (label, info["max_kink_deg"], max_kink))
        dev = max(h['dev'] for h in pm.heading_checks(items))
        if dev > max_dev:
            bad.append("%s: A is %.2f deg off the travel direction (limit %.1f)" % (label, dev, max_dev))
        n_loops = n_layers * p.turns
        n_tr = sum(1 for i in items if isinstance(i, pm.Comment) and "TRANSITION" in i.text)
        n_layer_c = sum(1 for i in items if isinstance(i, pm.Comment) and i.text.startswith("===== LAYER"))
        if n_tr != n_loops - 1 or n_layer_c != n_layers:
            bad.append("%s: %d transitions for %d loops, %d layer comments" % (label, n_tr, n_loops, n_layer_c))
        if not any(m['transition'] for m in moves) and n_loops > 1:
            bad.append("%s: no transition moves marked for the views" % label)
        # the wall: every turn keeps its distance E from the previous one (checked on layer 0)
        if d.kind == "2d" and not p.corner_radius:
            import contours as ct
            src = ff.layer_outlines(p)[0][0]
            sign = -1 if p.inward else 1
            far = [ct.closest_point(src, q[:2])[3] for m in moves if m['layer'] == 0 and not m['transition']
                   for q in m['pts']]
            want = p.step * (p.turns - 1)
            if abs(max(far) - want) > 0.05:
                bad.append("%s: outermost turn is %.3f from the outline, expected %.3f" % (label, max(far), want))
            inside = [ff._inside(src, q[:2]) for m in moves if m['layer'] == 0 and not m['transition']
                      for q in m['pts'] if ct.closest_point(src, q[:2])[3] > 0.1]
            if inside and (all(inside) if sign > 0 else not any(inside)):
                bad.append("%s: turns grow to the wrong side" % label)
    # the STL follows the model: each layer of the cone is smaller than the one below
    d = imf.load_design(design("cone.stl"))
    p = ff.FreeformParams(**dict(base, design=d, turns=1, layers=6))
    items, info = ff.generate(p)
    _, moves = pm.path_3d(items)
    for layer, r in ((0, 58.75), (5, 46.25)):
        rs = [math.hypot(q[0] - 150, q[1] - 225) for m in moves if m['layer'] == layer and not m['transition']
              for q in m['pts']]
        if abs(max(rs) - r) > 0.06 or min(rs) < r - 0.6:
            bad.append("cone layer %d radius %.3f..%.3f, expected about %.2f" % (layer, min(rs), max(rs), r))
    # more layers than the model is high: limited, with a note
    items, info = ff.generate(ff.FreeformParams(**dict(base, design=d, layers=40)))
    if info["layers"] != 6 or not any("6 layers" in w for w in info["warnings"]):
        bad.append("cone with 40 layers: %d layers, notes %s" % (info["layers"], info["warnings"]))
    # sharp corners and tight arcs are reported; impossible requests give a readable error
    d = imf.load_design(design("corners_px.svg"))
    items, info = ff.generate(ff.FreeformParams(**dict(base, design=d)))
    if not any("sharp corner" in w for w in info["warnings"]) or not any("radius" in w for w in info["warnings"]):
        bad.append("sharp corners not reported: %s" % info["warnings"])
    for extra, word in ((dict(inward=True, turns=30), "turn"), (dict(corner_radius=60.0), "Corner radius")):
        try:
            ff.generate(ff.FreeformParams(**dict(base, design=d, **extra)))
            bad.append("%s should be refused" % extra)
        except ValueError as ex:
            if word not in str(ex):
                bad.append("%s: unclear message: %s" % (extra, ex))
    errs = ff.validate(ff.FreeformParams(**dict(base, design=None)))[0]
    if not errs or "design file" not in errs[0]:
        bad.append("no design file: %s" % errs)
    for extra in (dict(outline=4), dict(scale=0.0), dict(step=0.0), dict(turns=0), dict(smoothing=5.0),
                  dict(corner_radius=-1.0)):
        if not ff.validate(ff.FreeformParams(**dict(base, design=d, **extra)))[0]:
            bad.append("validate accepted %s" % extra)
    return bad


# ---------------------------------------------------------------------- main app

def check_main_import(tmpdir):
    import json
    bad = []
    msgs = _quiet()
    root, app = _new_main_app()
    try:
        app.generate()                                     # a cuboid first: undo must bring it back
        cuboid_out = app.state()["output"]
        if not app.import_design(design("blob.svg")):
            bad.append("import_design(blob.svg) failed: %s" % msgs)
            return bad
        st = app.state()
        if st["shape"] != "import" or "FREE-FORM" not in st["output"] or not st["output"].startswith("PTP"):
            bad.append("import did not switch to Import and generate")
        if str(app.seg_buttons["import"].cget("style")) != "SegOn.TButton":
            bad.append("the Import button is not highlighted")
        if not app.inward_check.winfo_manager() or app.helix_check.winfo_manager():
            bad.append("Import must show 'Turns grow inward' and hide Helix")
        if "blob.svg" not in app.shape_hint.cget("text") or "2 closed outlines" not in app.shape_hint.cget("text"):
            bad.append("file line: %r" % app.shape_hint.cget("text"))
        app.undo()
        if app.state()["shape"] != "cuboid" or app.state()["output"] != cuboid_out:
            bad.append("undo after import did not restore the cuboid")
        app.redo()
        if app.state()["output"] != st["output"]:
            bad.append("redo after import did not restore the import")
        # the second outline, inward; a wrong outline number is refused without changing the output
        app.shape_vars["import"]["outline"].set("2")
        app.vars["turns"].set("1")
        if not app.generate():
            bad.append("outline 2 failed: %s" % msgs[-1:])
        before = app.state()["output"]
        app.shape_vars["import"]["outline"].set("7")
        if app.generate() or app.state()["output"] != before:
            bad.append("outline 7 of 2 must be refused and leave the output")
        app.shape_vars["import"]["outline"].set("1")
        app.vars["turns"].set("3")
        app.inward_var.set(True)
        app.generate()
        inward_out = app.state()["output"]
        if inward_out == st["output"]:
            bad.append("'Turns grow inward' did not change the path")
        # project round trip: same output, no notice; the options come back
        proj = os.path.join(tmpdir, "import_project.json")
        app.save_project_to(proj)
        with open(proj) as f:
            data = json.load(f)
        if data["shape"] != "import" or data["inputs"]["import"]["file"] != design("blob.svg") or \
                not data["options"]["inward"]:
            bad.append("project file does not hold the import inputs")
        app.set_shape("cuboid")
        app.inward_var.set(False)
        app.clear()
        del msgs[:]
        if not app.open_project_from(proj):
            bad.append("could not reopen the import project: %s" % msgs)
        if app.state()["output"] != inward_out or app.shape_var.get() != "import" or not app.inward_var.get():
            bad.append("reopened import project differs")
        if any("differs" in m[1] for m in msgs):
            bad.append("reopening an unchanged import project gave a notice")
        # the design file is gone: the saved output is kept, with a notice
        data["inputs"]["import"]["file"] = os.path.join(tmpdir, "gone.svg")
        moved = os.path.join(tmpdir, "import_project_moved.json")
        with open(moved, "w") as f:
            json.dump(data, f)
        del msgs[:]
        app.clear()
        if not app.open_project_from(moved) or app.state()["output"] != inward_out:
            bad.append("project with a missing design file must keep the saved output")
        if not any("SAVED output was kept" in m[1] for m in msgs):
            bad.append("missing design file: no notice (%s)" % msgs)
        del msgs[:]
        if app.generate() or not any(m[0] == "error" and "not found" in m[1] for m in msgs):
            bad.append("Generate with a missing design file: %s" % msgs)
        # unreadable file / STEP: message, nothing changes; no file chosen: message
        before = app.state()
        del msgs[:]
        if app.import_design(os.path.join(tmpdir, "part.step")) or app.state() != before or \
                not any("STL" in m[1] for m in msgs):
            bad.append("STEP file: must be refused with advice (%s)" % msgs)
        app.shape_vars["import"]["file"].set("")
        del msgs[:]
        if app.generate() or not any("Choose a design file" in m[1] for m in msgs):
            bad.append("no design file chosen: %s" % msgs)
        # STL through the app, with the note about the model's height; export works
        del msgs[:]
        app.inward_var.set(False)
        app.vars["layers"].set("30")
        app.shape_vars["import"]["scale"].set("3")
        if not app.import_design(design("cone.stl")) or msgs:
            bad.append("an import must not pop up anything: %s" % msgs)
        if app.vars["layers"].get() != "6" or app.shape_vars["import"]["scale"].get() != "1":
            bad.append("a new STL must set Layers to the model height (6) and start 1 : 1 (%s, %s)"
                       % (app.vars["layers"].get(), app.shape_vars["import"]["scale"].get()))
        app.vars["layers"].set("30")
        del msgs[:]
        app.generate()
        if msgs or not any("6 layers" in w for w in app.warnings) or "to check" not in app.checks_chip.cget("text"):
            bad.append("more layers than the model: no pop-up, a line behind the checks chip (%s, %s)"
                       % (msgs, app.warnings))
        out = os.path.join(tmpdir, "IMPORT_CONE.src")
        if not app.export_to(out) or " C_DIS" not in open(out).read() or not open(out).read().endswith("END"):
            bad.append("export of an imported path failed")
        # the other shapes are untouched by the new options
        app.set_shape("cuboid")
        if app.inward_check.winfo_manager() or app.shape_hint.cget("text").find("corner radius") < 0:
            bad.append("cuboid panel after Import is not as before")
    finally:
        root.destroy()
    return bad


# ---------------------------------------------------------------------- robot transfer

def check_robot_link(tmpdir):
    import json
    import krl_export
    import robot_link as rl
    import ui_theme
    bad = []
    settings = os.path.join(tmpdir, "robot_settings.json")
    with open(settings, "w") as f:
        json.dump({"theme": "dark"}, f)
    if rl.load_settings(settings) != {"folder": "", "last_name": ""}:
        bad.append("settings: defaults expected when nothing is stored")
    rl.save_settings(settings, {"folder": r"\\172.31.1.147\transfer", "last_name": "PART_1"})
    with open(settings) as f:
        data = json.load(f)
    if data.get("theme") != "dark" or rl.load_settings(settings)["folder"] != r"\\172.31.1.147\transfer":
        bad.append("settings: must be stored next to the theme, not replace it")
    if rl.load_settings(os.path.join(tmpdir, "none.json"))["folder"] != "":
        bad.append("settings: a missing file must give the defaults")
    for folder, host in ((r"\\172.31.1.147\transfer\x", "172.31.1.147"), ("//robot/share", "robot"),
                         (r"Z:\transfer", None), (r"C:\x", None), ("", None)):
        if rl.unc_host(folder) != host:
            bad.append("unc_host(%r) = %r" % (folder, rl.unc_host(folder)))
    ok, msg = rl.reachable("127.0.0.1", port=1, timeout=1.0)
    if ok or "127.0.0.1" not in msg:
        bad.append("reachable() on a closed port: %s %s" % (ok, msg))
    folder = os.path.join(tmpdir, "transfer")
    os.makedirs(folder)
    for f_, want in ((folder, True), (os.path.join(tmpdir, "no_such_folder"), False), ("", False)):
        ok, msg = rl.check_folder(f_)
        if ok != want or not msg:
            bad.append("check_folder(%r): %s %s" % (f_, ok, msg))
    if os.listdir(folder):
        bad.append("check_folder left a file behind")
    code = "DEF X( )\nLIN {X 1.0}\nEND"
    path = rl.send_program(folder, "X", code)
    if os.path.basename(path) != "X.src" or open(path).read() != code or os.listdir(folder) != ["X.src"]:
        bad.append("send_program did not write exactly X.src")
    try:
        rl.send_program(folder, "X", code + " ")
        bad.append("an existing program must not be replaced silently")
    except rl.ProgramExists:
        pass
    rl.send_program(folder, "X", code + " ", overwrite=True)
    if open(path).read() != code + " ":
        bad.append("overwrite did not replace the program")
    try:
        rl.send_program(os.path.join(tmpdir, "no_such_folder"), "X", code)
        bad.append("sending into a missing folder must fail")
    except rl.RobotLinkError:
        pass
    # through the main app: the sent file is exactly the exported one
    msgs = _quiet()
    asked = []
    messagebox.askyesno = lambda *a, **k: asked.append(a[1]) or True
    root, app = _new_main_app()
    try:
        if app.send_to_robot() is not None or not any("Nothing to send" in m[1] for m in msgs):
            bad.append("Send with an empty program: %s" % msgs)
        app.generate()
        del msgs[:]
        win = app.send_to_robot()                          # no folder yet: opens the connection dialog
        if win is None or not hasattr(win, "test") or not any("transfer folder" in m[1] for m in msgs):
            bad.append("Send without a transfer folder must open Robot Connection")
        else:
            win.var.set(os.path.join(tmpdir, "no_such_folder"))
            if win.test() or "not found" not in win.status.cget("text"):
                bad.append("connection test on a missing folder: %r" % win.status.cget("text"))
            win.var.set(folder)
            if not win.test():
                bad.append("connection test on a good folder: %r" % win.status.cget("text"))
            win.save()
        if app.robot_settings()["folder"] != folder or ui_theme.load_theme() not in ui_theme.THEMES:
            bad.append("the transfer folder was not saved")
        exported = os.path.join(tmpdir, "SENT_1.src")
        app.export_to(exported)
        win = app.send_to_robot()
        if win is None or not hasattr(win, "ok"):
            bad.append("Send with a folder must ask for the program name")
        else:
            del msgs[:]
            win.var.set("bad name")
            win.ok()
            if not win.winfo_exists() or not any(m[0] == "error" for m in msgs) or \
                    os.path.exists(os.path.join(folder, "bad name.src")):
                bad.append("an invalid program name must be refused and keep the dialog open")
            win.var.set("SENT_1")
            win.ok()
            sent = os.path.join(folder, "SENT_1.src")
            if not os.path.exists(sent) or open(sent).read() != open(exported).read():
                bad.append("the sent program differs from the exported one")
            if win.winfo_exists():
                bad.append("the Send dialog should close after sending")
        if app.robot_settings()["last_name"] != "SENT_1":
            bad.append("the last program name was not remembered")
        del asked[:]
        if not app.send_program_to("SENT_1", folder) or len(asked) != 1:
            bad.append("sending the same name again must ask before replacing (%s)" % asked)
        messagebox.askyesno = lambda *a, **k: False
        before = open(os.path.join(folder, "SENT_1.src")).read()
        app.clear()
        app.vars["turns"].set("1")
        app.generate()
        if app.send_program_to("SENT_1", folder) or open(os.path.join(folder, "SENT_1.src")).read() != before:
            bad.append("answering No must keep the program in the transfer folder")
        del msgs[:]
        if app.send_program_to("SENT_2", os.path.join(tmpdir, "no_such_folder")) or \
                not any(m[0] == "error" for m in msgs):
            bad.append("sending into a missing folder must show an error")
        if not krl_export.is_valid_program_name("SENT_1"):
            bad.append("test name invalid")
    finally:
        root.destroy()
    return bad


# ---------------------------------------------------------------------- mesh outlines (found on real parts)

def check_mesh_outlines():
    import contours as ct
    import freeform as ff
    import import_formats as imf
    bad = []
    # simplify must never move the outline by more than its tolerance, also on dense points
    # (an older version removed a whole corner arc when points came in close pairs)
    arc = ct.flatten_arc((40.0, 20.0), 20.0, -math.pi / 2, math.pi / 2, 0.0005)
    dense = []
    for q in arc:
        dense += [q, (q[0] + 0.002, q[1] + 0.0005)]
    poly = [(-60.0, 0.0)] + [(x * 1.0, 0.0) for x in range(-59, 40)] + dense + [(60.0, 155.0), (-60.0, 155.0)]
    simple = ct.simplify(poly, 0.005)
    worst = max(ct.closest_point(simple, q)[3] for q in poly)
    if worst > 0.0051 or abs(ct.area(simple) - ct.area(ct.normalize(poly))) > 2.0 or len(simple) > 80:
        bad.append("simplify: moved the outline by %.4f mm, %d points, area %.1f vs %.1f"
                   % (worst, len(simple), ct.area(simple), ct.area(ct.normalize(poly))))
    if len(ct.simplify([(0, 0), (5, 0), (10, 0), (10, 10), (5, 10.00001), (0, 10)], 0.001)) != 4:
        bad.append("simplify: points on a straight line must go")
    # an inside fillet whose radius is the offset distance (the offset collapses to a corner there),
    # with tiny zigzag edges as a fine STL gives them
    r = 2.0
    fillet = ct.flatten_arc((20.0 + r, 20.0 + r), r, math.pi, math.pi / 2, 0.01)       # inside corner of an L
    L = [(0.0, 0.0), (60.0, 0.0), (60.0, 20.0)] + fillet[::-1] + [(20.0, 60.0), (0.0, 60.0)]
    L = ct.normalize(L)
    for d in (1.0, 2.0, 2.5, 4.0):
        loops = ct.offset(L, d)
        if not loops:
            bad.append("L with an inside fillet of radius 2, offset %g: nothing" % d)
            continue
        dists = [ct.closest_point(L, q)[3] for q in loops[0][::3]]
        if min(dists) < d - 0.05 or max(dists) > d * 1.42 or ct.area(loops[0]) <= ct.area(L):
            bad.append("L with an inside fillet, offset %g: distance %.3f..%.3f" % (d, min(dists), max(dists)))
    # layer tracking: a block with a thin post on one side and a bigger block floating beside it
    def box(x0, y0, z0, x1, y1, z1):
        v = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
        quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (1, 5, 7, 3), (3, 7, 6, 2), (2, 6, 4, 0)]
        return [t for a, b, c, e in quads for t in ((v[a], v[b], v[c]), (v[a], v[c], v[e]))]
    d = imf.Design("test.stl", "3d")
    imf._finish_3d(d, box(0, 0, 0, 40, 40, 4) + box(5, 5, 4, 25, 25, 12) + box(100, 0, 6, 180, 60, 12))
    p = ff.FreeformParams(design=d, xc=0, yc=0, z0=0, step=2, layer_height=2, turns=1, layers=6)
    outlines, notes = ff.layer_outlines(p)
    areas = [round(ct.area(o)) for o in outlines]
    if areas != [1600, 1600, 400, 400, 400, 400]:
        bad.append("layer tracking: areas %s (the post over the block must be followed, not the big island)" % areas)
    if not any("separate parts" in n for n in notes):
        bad.append("layer tracking: no note about the separate part (%s)" % notes)
    return bad


# ---------------------------------------------------------------------- polish items

def check_polish(tmpdir):
    import KRL_Generator as K
    import krl_export
    import path_model as pm
    bad = []
    # approach / retract on plain items
    items = [pm.Ptp(pm.pose((10, 20, 5), (90, -3, 180), 2, 43)), pm.Comment("===== LAYER 0 ====="),
             pm.Lin(pm.pose((10, 80, 5), (90, -3, 180))),
             pm.Circ(pm.pose((40, 110, 5)), pm.pose((70, 80, 5), (-90, -3, 180)))]
    out = pm.add_approach_retract(items, 30)
    text = pm.program_to_krl(out)
    lines = text.split("\n")
    want = ["; APPROACH: 30.0 mm above the start, then straight down",
            "PTP {X 10.0, Y 20.0, Z 35.0, A 90.0, B -3.0, C 180.0, S 2., T 43.}",
            "LIN {X 10.0, Y 20.0, Z 5.0, A 90.0, B -3.0, C 180.0} ; exact stop"]
    if lines[:3] != want or lines[-1] != "LIN {X 70.0, Y 80.0, Z 35.0, A -90.0, B -3.0, C 180.0}" or \
            not lines[-3].endswith("; exact stop") or lines[-2] != "; RETRACT: straight up":
        bad.append("approach / retract lines: %s ... %s" % (lines[:3], lines[-3:]))
    if pm.program_to_krl(pm.parse_krl(text)) != text:
        bad.append("approach / retract text does not round-trip")
    blended = krl_export.add_c_dis(text).split("\n")
    if "C_DIS" in blended[2] or "C_DIS" in blended[-3] or "C_DIS" in blended[-1] or "C_DIS" not in blended[4]:
        bad.append("C_DIS: the touch-down, the end of the print and the lift must stay exact: %s" % blended)
    if pm.add_approach_retract([pm.Comment("x")], 30) != [pm.Comment("x")]:
        bad.append("approach / retract on a text without moves must change nothing")
    _, moves = pm.path_3d(out)
    if [m['line'] for m in moves] != [2, 4, 5, 7]:
        bad.append("path_3d 'line' of each move: %s" % [m['line'] for m in moves])
    # checks
    if K.path_warnings(items):
        bad.append("a small path on the bed should give no warnings: %s" % K.path_warnings(items))
    off = [pm.Ptp(pm.pose((290, 20, -8), (0, 0, 180))), pm.Lin(pm.pose((320, 20, -8), (0, 0, 180))),
           pm.Lin(pm.pose((320, 60, -8), (0, 0, 180))),
           pm.Circ(pm.pose((317, 67, -8)), pm.pose((310, 70, -8), (180, 0, 180)))]
    w = " | ".join(K.path_warnings(off))
    for word in ("leaves the bed", "below the bed", "arc radius", "sharp corner", "off the travel"):
        if word not in w:
            bad.append("path_warnings: '%s' missing in: %s" % (word, w))
    if K.to_number(" 2,5 ", "x") != 2.5:
        bad.append("decimal comma not accepted")
    # through the app
    msgs = _quiet()
    answers = []
    messagebox.askyesnocancel = lambda *a, **k: answers.pop(0)
    root, app = _new_main_app(approach=True)
    try:
        if not app.approach_var.get() or app.lift_var.get() != "30":
            bad.append("approach must be on by default with 30 mm")
        app.vars["step"].set("2,5")
        if not app.generate():
            bad.append("Generate with a decimal comma failed: %s" % msgs)
        text = app.state()["output"]
        rows = text.split("\n")
        k = next((i for i, r_ in enumerate(rows) if r_.startswith("; APPROACH")), None)
        if k is None or not rows[k + 1].startswith("PTP") or "Z 40.0" not in rows[k + 1] or \
                not rows[k + 2].endswith("; exact stop") or "; RETRACT" not in text:
            bad.append("the app did not add the approach / retract moves")
        if str(app.generate_btn.cget("text")) != "Generate":
            bad.append("the Generate button must be plain right after Generate")
        app.vars["turns"].set("2")
        if "inputs changed" not in str(app.generate_btn.cget("text")):
            bad.append("changing an input must be shown on the Generate button")
        app.generate()
        if "inputs changed" in str(app.generate_btn.cget("text")):
            bad.append("Generate must clear the 'inputs changed' note")
        del msgs[:]
        app.lift_var.set("-5")
        before = app.state()["output"]
        if app.generate() or app.state()["output"] != before or not any("approach height" in m[1] for m in msgs):
            bad.append("a negative approach height must be refused")
        app.lift_var.set("30")
        del msgs[:]
        app.vars["layers"].set("abc")
        if app.generate() or not any("Layers" in m[1] for m in msgs):
            bad.append("the error must name the wrong field: %s" % msgs)
        app.vars["layers"].set("3")
        app.generate()
        if app.warnings or "checks OK" not in app.checks_chip.cget("text"):
            bad.append("default cuboid: checks should be OK (%s)" % app.warnings)
        app.shape_vars["cuboid"]["xc"].set("280")
        app.generate()
        if not any("leaves the bed" in w_ for w_ in app.warnings) or "to check" not in app.checks_chip.cget("text"):
            bad.append("a cuboid off the bed must be reported (%s)" % app.warnings)
        del msgs[:]
        src = os.path.join(tmpdir, "POLISH_1.src")
        app.export_to(src)
        if not any("leaves the bed" in m[1] for m in msgs):
            bad.append("the export message must list the checks: %s" % msgs)
        code = open(src).read()
        if "; exact stop C_DIS" in code or " C_DIS ; exact stop" in code or code.count("exact stop") != 2:
            bad.append("exported approach / retract: exact stops wrong")
        app.shape_vars["cuboid"]["xc"].set("150")
        app.generate()
        # click to find the line
        app.redraw()
        line, coords = app._screen_moves[5]

        class Ev(object):
            x, y = (coords[0] + coords[2]) / 2.0, (coords[1] + coords[3]) / 2.0
        app._press(Ev)
        app._release(Ev)
        got = app.output_text.tag_ranges("picked")
        if app._sel_line != line or not got or str(got[0]) != "%d.0" % (line + 1):
            bad.append("a click on a move must mark its line (%s, %s)" % (app._sel_line, [str(g) for g in got]))
        app.output_text.mark_set("insert", "%d.3" % (app._screen_moves[9][0] + 1))
        app._text_clicked()
        if app._sel_line != app._screen_moves[9][0]:
            bad.append("a click on a line must mark its move")
        # Save / unsaved work
        proj = os.path.join(tmpdir, "polish_project.json")
        if not app.is_dirty():
            bad.append("a generated, unsaved program must count as unsaved work")
        app.save_project_to(proj)
        if app.is_dirty() or app.project_path != proj:
            bad.append("after Save there must be no unsaved work")
        app.vars["turns"].set("4")
        app.generate()
        stamp = open(proj).read()
        if not app.is_dirty() or not app.save() or app.is_dirty() or open(proj).read() == stamp:
            bad.append("File > Save must write into the open project file")
        app.vars["turns"].set("5")
        answers[:] = [None]
        if app.on_close() or not app.root.winfo_exists():
            bad.append("Cancel must keep the app open")
        # reopening gives the same output with the approach moves, without a notice
        del msgs[:]
        app.vars["turns"].set("4")
        saved_out = app.state()["output"]
        app.clear()
        if not app.open_project_from(proj) or app.state()["output"] != saved_out or \
                any("differs" in m[1] for m in msgs) or not app.approach_var.get():
            bad.append("reopening a project with approach moves: %s" % msgs)
        # robot guide opens and names the honest status
        win = app.show_robot_guide()
        if "NOT BEEN TRIED ON THE ROBOT" not in win.text.get("1.0", "end"):
            bad.append("the robot guide must say that the robot side is untested")
        win.destroy()
        answers[:] = [False]
        app.vars["turns"].set("2")
        app.generate()
        if not app.on_close():
            bad.append("answering No must close without saving")
            root.destroy()
    except Exception:
        try:
            root.destroy()
        except tk.TclError:
            pass
        raise
    return bad


# ---------------------------------------------------------------------- import: as drawn, nothing to fill in

def check_import_auto(tmpdir):
    import contours as ct
    import freeform as ff
    import import_formats as imf
    import path_model as pm
    import view3d
    bad = []

    def write(name, text):
        path = os.path.join(tmpdir, name)
        with open(path, "w") as f:
            f.write(text)
        return path
    pts = " ".join("%.4f,%.4f" % (100 + 90 * math.sin(2 * math.pi * k / 400),
                                  60 + 110 * math.sin(2 * math.pi * k / 400) * math.cos(2 * math.pi * k / 400))
                   for k in range(400))
    infinity = write("infinity.svg", '<svg xmlns="http://www.w3.org/2000/svg" width="200mm" height="120mm" '
                     'viewBox="0 0 200 120"><polygon points="%s"/></svg>' % pts)
    wave = write("wave.svg", '<svg xmlns="http://www.w3.org/2000/svg" width="200mm" height="100mm" '
                 'viewBox="0 0 200 100"><path d="M 10 50 C 40 0 70 0 100 50 S 160 100 190 50"/></svg>')
    base = dict(xc=150, yc=225, z0=10, step=2, layer_height=2, turns=3, layers=3)
    # which kind of path is it?
    d = imf.load_design(infinity)
    if [k for k, _ in d.paths] != ["crossing"] or "self-crossing" not in d.describe():
        bad.append("infinity.svg: %s" % d.describe())
    dw = imf.load_design(wave)
    if [k for k, _ in dw.paths] != ["open"]:
        bad.append("wave.svg: %s" % dw.describe())
    dc = imf.load_design(design("corners_px.svg"))
    if [k for k, _ in dc.paths] != ["outline", "outline", "open"]:
        bad.append("corners_px.svg paths: %s" % [k for k, _ in dc.paths])
    if ct.crosses_itself([(0, 0), (10, 0), (10, 10), (0, 10)]) or not ct.crosses_itself([(0, 0), (10, 10), (10, 0), (0, 10)]):
        bad.append("crosses_itself is wrong on a square / a bow tie")
    # the infinity shape: followed as drawn, every layer on the same curve, smooth, through the crossing twice
    items, info = ff.generate(ff.FreeformParams(**dict(base, design=d)))
    start, moves = pm.path_3d(items)
    box = ct.bounds(d.paths[0][1])
    src = ff._place(d.paths[0][1], ff.FreeformParams(**dict(base, design=d)), ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2))
    far = max(ct.closest_point(src, q[:2])[3] for m in moves for q in m['pts'])
    zs = [m['pts'][-1][2] for m in moves]
    dev = max(h['dev'] for h in pm.heading_checks(items))
    if far > 0.05 or info["max_kink_deg"] > 4 or dev > 2.5 or any(b < a - 1e-9 for a, b in zip(zs, zs[1:])) or \
            abs(zs[-1] - 14) > 1e-9 or abs(info["length_mm"] - 3 * ct.perimeter(src)) > 2.0:
        bad.append("infinity: off the drawing by %.3f, corner %.1f, A %.1f, Z end %.1f, length %.0f vs %.0f"
                   % (far, info["max_kink_deg"], dev, zs[-1], info["length_mm"], 3 * ct.perimeter(src)))
    if "on top of itself" not in info["warnings"][0] or any("as drawn" in w for w in info["warnings"]):
        bad.append("infinity: notes %s" % info["warnings"])
    centre_hits = sum(1 for m in moves if m['layer'] == 0 and
                      any(math.hypot(q[0] - 150, q[1] - 225) < 2.0 for q in m['pts']))
    if centre_hits < 2:
        bad.append("infinity: the path must pass the crossing twice per layer")
    # the open path: there and back, the way back starts with the climb
    items, info = ff.generate(ff.FreeformParams(**dict(base, design=dw)))
    start, moves = pm.path_3d(items)
    ends = [m['pts'][-1] for m in moves]
    if abs(start[0] - 60) > 0.01 or abs(ends[-1][0] - 240) > 0.01 or abs(ends[-1][2] - 14) > 1e-9 or \
            not any("back and forth" in w for w in info["warnings"]):
        bad.append("open path: start X %.2f, end X %.2f Z %.1f, notes %s" % (start[0], ends[-1][0], ends[-1][2],
                                                                           info["warnings"]))
    one, info1 = ff.generate(ff.FreeformParams(**dict(base, design=dw, layers=1)))
    if info1["max_kink_deg"] > 2 or any("back and forth" in w for w in info1["warnings"]):
        bad.append("open path, 1 layer: corner %.1f, notes %s" % (info1["max_kink_deg"], info1["warnings"]))
    # Fill: inward turns E apart until the core is about 40 mm wide
    dp = imf.load_design(design("plate.dxf"))
    items, info = ff.generate(ff.FreeformParams(**dict(base, design=dp, fill=True, layers=1, turns=1, step=3)))
    n = sum(1 for i in items if isinstance(i, pm.Comment) and i.text.startswith("L0 T") and "->" not in i.text)
    if n != 4 or not any("Fill: 4 inward turns" in w for w in info["warnings"]):
        bad.append("fill of the 160 x 60 plate: %d turns, notes %s (expected 4: 60 mm wide, 3 mm step, 40 mm core)"
                   % (n, info["warnings"]))
    _, moves = pm.path_3d(items)
    src = ff.layer_outlines(ff.FreeformParams(**dict(base, design=dp)))[0][0]
    if not all(ff._inside(src, q[:2]) or ct.closest_point(src, q[:2])[3] < 0.05 for m in moves for q in m['pts']):
        bad.append("fill: the path leaves the outline")
    # the 3D view leaves out the approach and the lift
    with_approach = pm.add_approach_retract(items, 30)
    text = pm.program_to_krl(with_approach)
    _, all_moves = pm.path_3d(with_approach)
    if sum(1 for m in all_moves if m['aux']) != 2:
        bad.append("path_3d must mark the approach and the lift (%d marked)" % sum(1 for m in all_moves if m['aux']))
    root = tk.Tk()
    root.withdraw()
    try:
        v = view3d.View3D(root, lambda: text)
        if len(v.moves) != len(all_moves) - 2 or abs(v.bounds[5] - 10.0) > 1e-9 or abs(v.start[2] - 10.0) > 1e-9:
            bad.append("3D view: approach / lift must be left out (Z up to %.1f, %d moves)" % (v.bounds[5], len(v.moves)))
    finally:
        root.destroy()
    # through the app: choose the file, nothing else; no pop-up; suggestions and the one-click fix
    msgs = _quiet()
    asked = []
    messagebox.askyesno = lambda *a, **k: asked.append(a[1]) or True
    root, app = _new_main_app()
    try:
        if not app.import_design(infinity) or msgs:
            bad.append("importing the infinity shape: %s" % msgs)
        if "AS DRAWN" not in app.state()["output"] or not any("on top of itself" in w for w in app.warnings):
            bad.append("infinity in the app: %s" % app.warnings)
        if app.more_var.get() or hasattr(app, "x_none"):
            bad.append("the extra settings must be folded away after an import")
        if not app.import_design(design("corners_px.svg")) or msgs:
            bad.append("importing corners_px.svg must not pop up anything: %s" % msgs)
        w = " | ".join(app.warnings)
        if "sharp corner" not in w or "Suggestion: round them with a Corner rad. of 20 mm" not in w or "96 px" not in w:
            bad.append("sharp corners: the checks must give a suggestion and the file note (%s)" % w)
        if w.count("sharp corner") != 1:
            bad.append("sharp corners listed more than once: %s" % w)
        app.show_checks()
        if len(asked) != 1 or "Round the corners now" not in asked[0]:
            bad.append("the checks list must offer to round the corners (%s)" % asked)
        if app.shape_vars["import"]["corner_radius"].get() != "20" or not app.more_var.get() or \
                any("sharp corner" in x for x in app.warnings) or msgs:
            bad.append("one-click rounding: radius %r, warnings %s, messages %s"
                       % (app.shape_vars["import"]["corner_radius"].get(), app.warnings, msgs))
        # a shape too small for 20 mm takes the next radius that fits
        app.shape_vars["import"]["outline"].set("2")
        app.shape_vars["import"]["corner_radius"].set("")
        app.generate()
        got = app.round_corners_now()
        if got not in (15.0, 10.0, 5.0) or app.shape_vars["import"]["corner_radius"].get() != "%g" % got:
            bad.append("rounding a small shape: %s" % got)
        # Fill and the folded settings travel with the project
        app.fill_var.set(True)
        app.generate()
        proj = os.path.join(tmpdir, "auto_project.json")
        app.save_project_to(proj)
        out = app.state()["output"]
        app.fill_var.set(False)
        app.show_more(False)
        app.clear()
        del msgs[:]
        if not app.open_project_from(proj) or app.state()["output"] != out or not app.fill_var.get() or \
                not app.more_var.get() or any("differs" in m[1] for m in msgs):
            bad.append("project with Fill and extra settings did not come back (%s)" % msgs)
    finally:
        root.destroy()
    return bad


# ---------------------------------------------------------------------- spline export (optional)

def check_spline(tmpdir):
    import re
    import cuboid
    import cylinder
    import freeform as ff
    import import_formats as imf
    import krl_export
    import path_model as pm
    bad = []

    def seg_dist(q, a, b):
        d = [b[i] - a[i] for i in range(3)]
        l2 = sum(x * x for x in d)
        t = 0.0 if l2 == 0 else max(0.0, min(1.0, sum((q[i] - a[i]) * d[i] for i in range(3)) / l2))
        return math.sqrt(sum((q[i] - a[i] - t * d[i]) ** 2 for i in range(3)))

    def study(label, items, want_slin):
        body = pm.program_to_krl(items) + "\n"
        out = krl_export.to_spline(body, 3)
        lines = out.split("\n")
        if lines.count("SPLINE") != 1 or lines.count("ENDSPLINE") != 1 or "C_DIS" in out or \
                lines.index("SPLINE") > lines.index("ENDSPLINE"):
            bad.append("%s: one SPLINE ... ENDSPLINE block expected" % label)
        inside = lines[lines.index("SPLINE") + 1:lines.index("ENDSPLINE")]
        if any(not (l.startswith("  SPL {") or l.startswith("  SLIN {") or l.strip().startswith(";") or not l.strip())
               for l in inside):
            bad.append("%s: only SPL / SLIN / comments may be inside the block" % label)
        if any(re.match(r"\s*(LIN|CIRC|SCIRC)\b", l) for l in inside):
            bad.append("%s: LIN / CIRC left inside the block" % label)
        n_slin = sum(l.startswith("  SLIN") for l in lines)
        if (n_slin > 0) != want_slin:
            bad.append("%s: %d SLIN" % (label, n_slin))
        # every point is ON the path, in the order of the path, and the last one is its end
        _, moves = pm.path_3d(items)
        poly = [q for m in moves if not m['aux'] for q in m['pts']]
        pts = []
        for l in inside:
            m = re.match(r"\s*(SPL|SLIN) \{X ([-\d.]+), Y ([-\d.]+), Z ([-\d.]+), A ([-\d.]+)", l)
            if m:
                pts.append(tuple(float(m.group(i)) for i in (2, 3, 4, 5)))
        worst = max(min(seg_dist(q, a, b) for a, b in zip(poly, poly[1:])) for q in pts[::3])
        if worst > 0.1:                                   # the comparison path is drawn in 5 deg steps (sag 0.06 mm)
            bad.append("%s: a spline point is %.3f mm off the path" % (label, worst))
        end = poly[-1]
        if math.sqrt(sum((pts[-1][i] - end[i]) ** 2 for i in range(3))) > 0.001:
            bad.append("%s: the block must end on the last point of the print" % label)
        steps = [math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(3))) for a, b in zip(pts, pts[1:])]
        n_spl = sum(l.startswith("  SPL") for l in lines)
        if n_spl < sum(isinstance(i, pm.Circ) for i in items):
            bad.append("%s: every arc needs at least one SPL point" % label)
        turn = max(abs(pm.angle_diff(a[3], b[3])) for a, b in zip(pts, pts[1:]))
        if turn > 46:
            bad.append("%s: A jumps by %.0f deg between two spline points" % (label, turn))
        return out

    items, _ = cuboid.generate(cuboid.CuboidParams(length=150, width=300, corner_radius=None, xc=150, yc=225, z0=10,
                                                   step=2, layer_height=2, turns=3, layers=3, a=180, b=-3, c=180))
    out = study("cuboid", items, True)
    lines = out.split("\n")
    k = lines.index("SPLINE")
    want = ["  SLIN {X 97.5, Y 375.0, Z 10.0, A 180.0, B -3.0, C 180.0}",
            "  SPL {X 91.677, Y 374.233, Z 10.0, A -165.0, B -3.0, C 180.0}"]
    if lines[k + 1:k + 3] != want or not lines[k - 1].startswith("; Spline motion"):
        bad.append("cuboid spline start: %s" % lines[k - 1:k + 3])
    # quarter arc of radius 22.5: 6 points 15 deg apart, on the circle, A turning 15 deg each
    arc = [l for l in lines[k + 2:k + 8]]
    if len([l for l in arc if l.startswith("  SPL")]) != 6 or "A -90.0" not in arc[-1]:
        bad.append("cuboid corner as spline points: %s" % arc)
    with_ap = pm.add_approach_retract(items, 30)
    out = study("cuboid + approach", with_ap, True)
    lines = out.split("\n")
    if not any(l.startswith("LIN ") and l.endswith("; exact stop") for l in lines[:lines.index("SPLINE")]) or \
            not lines[lines.index("ENDSPLINE") + 2].startswith("LIN ") or "Z 44.0" not in lines[lines.index("ENDSPLINE") + 2]:
        bad.append("approach and lift must stay plain LIN outside the block")
    items, _ = cylinder.generate(cylinder.CylinderParams(xc=150, yc=225, z0=10, inner_diameter=100, step=2,
                                                         layer_height=2, turns=3, layers=3, b=-3))
    study("cylinder", items, False)
    d = imf.load_design(design("blob.svg"))
    items, _ = ff.generate(ff.FreeformParams(design=d, xc=150, yc=225, z0=10, step=2, layer_height=2, turns=2, layers=2))
    study("blob.svg", items, False)
    # straights meeting at a small angle are pieces of a curve (SPL); a real corner keeps its SLINs
    def poly_items(pts):
        return [pm.Ptp(pm.pose(pts[0], (0, 0, 180)))] + [pm.Lin(pm.pose(q, (0, 0, 180))) for q in pts[1:]]
    gentle = krl_export.to_spline(pm.program_to_krl(poly_items([(0, 0, 0), (50, 0, 0), (100, 4, 0), (150, 12, 0)])))
    corner = krl_export.to_spline(pm.program_to_krl(poly_items([(0, 0, 0), (50, 0, 0), (50, 50, 0), (0, 50, 0)])))
    if "  SLIN" in gentle or corner.count("  SLIN") != 3 or "  SPL" in corner:
        bad.append("SLIN / SPL choice at small angles and at corners:\n%s\n%s" % (gentle, corner))
    hand = "PTP {X 0.0, Y 0.0, Z 0.0}\nLIN {X 50.0, Y 0.0, Z 0.0}\n$OUT[1] = TRUE\nLIN {X 50.0, Y 50.0, Z 0.0}\n"
    got = krl_export.to_spline(hand).split("\n")
    if got.count("SPLINE") != 2 or got.count("ENDSPLINE") != 2 or got[got.index("$OUT[1] = TRUE") - 1] != "ENDSPLINE":
        bad.append("a hand-written statement must close the block before it: %s" % got)
    if krl_export.to_spline("; nothing here\n") != "; nothing here\n":
        bad.append("a text without moves must stay as it is")
    # through the app: off by default (same file as before), on = spline file, remembered in the project
    msgs = _quiet()
    root, app = _new_main_app()
    try:
        app.generate()
        plain = os.path.join(tmpdir, "SPL_OFF.src")
        app.export_to(plain)
        if app.spline_var.get() or "SPLINE" in open(plain).read() or " C_DIS" not in open(plain).read():
            bad.append("spline export must be off by default")
        app.spline_var.set(True)
        app._update_info()
        if "SPLINE" not in app.info.cget("text"):
            bad.append("the info line must say that the export is written as SPLINE")
        on = os.path.join(tmpdir, "SPL_ON.src")
        app.export_to(on)
        code = open(on).read()
        if code.count("\nSPLINE\n") != 1 or "C_DIS" in code.split("$ACC_AXIS[6]=100")[1] or \
                not code.endswith("END") or code.rstrip()[:-3].rstrip().split("\n")[-1] != "ENDSPLINE" or \
                not code.startswith("&ACCESS"):
            bad.append("spline export through the app: wrong file")
        if app.state()["output"].count("SPLINE"):
            bad.append("the text box must keep showing LIN / CIRC")
        proj = os.path.join(tmpdir, "spline_project.json")
        app.save_project_to(proj)
        app.spline_var.set(False)
        app.open_project_from(proj)
        if not app.spline_var.get():
            bad.append("the spline option must come back with the project")
    finally:
        root.destroy()
    return bad
