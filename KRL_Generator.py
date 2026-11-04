"""KRL Generator: the all-in-one app (cuboid and cylinder prints for the KUKA KR 6 R900 sixx).

Pick a shape, enter its sizes and the path settings, Generate, check it in the top view and
the 3D view, and export the .src. Everything is built on the shared modules:
    cuboid.py / cylinder.py   the path generators (no GUI)
    path_model.py             KRL lines (write / read), 3D geometry, kink and A checks
    krl_export.py             .src header + export profiles (export_profiles.json)
    project_files.py          project files (.json)
    view3d.py, export_settings_dialog.py   shared windows
The manual 11-point editor (PythonApplication6) stays available under Tools.

Turns and layers are EXACT (N gives N). B / Tilt is used as typed.
"""
import copy
import math
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cuboid
import cylinder
import export_settings_dialog
import krl_export
import path_model as pm
import project_files
import view3d

APP_TITLE = "KRL Generator"
TRANSITION_COLOR = "purple"
PATH_COLOR = "#1f77b4"
UNDO_LIMIT = 20

# Shape-specific fields: (key, label, default)
SHAPE_FIELDS = {
    "cuboid": [
        ("xc", "Centre X (mm):", "535"),
        ("yc", "Centre Y (mm):", "10"),
        ("z0", "Start Z (mm):", "65"),
        ("length", "Length X (mm):", "150"),
        ("width", "Width Y (mm):", "300"),
        ("corner_radius", "Corner Radius (mm, blank = auto):", ""),
    ],
    "cylinder": [
        ("xc", "Centre X (mm):", "535"),
        ("yc", "Centre Y (mm):", "10"),
        ("z0", "Start Z (mm):", "65"),
        ("inner_diameter", "Inner Diameter (mm):", "100"),
    ],
}
SHAPE_NAMES = {"cuboid": "Cuboid (rounded rectangle)", "cylinder": "Cylinder (tube)"}
# Path and orientation fields shared by all shapes
COMMON_FIELDS = [
    ("step", "Turn Step E (mm):", "2"),
    ("layer_height", "Layer Height (mm):", "2"),
    ("turns", "Turns per Layer:", "3"),
    ("layers", "Number of Layers:", "3"),
]
ORIENT_FIELDS = [
    ("a", "A (deg):", "180"),
    ("b", "B / Tilt (deg):", "0"),
    ("c", "C (deg):", "180"),
]

HELP_GENERAL = (
    "1. Choose the shape at the top left.\n"
    "2. Enter its size, the path settings and the orientation.\n"
    "3. Generate: the KRL moves appear below, the top view shows the path\n"
    "   (purple = turn / layer transitions). Check it in 3D View (Head direction (A)\n"
    "   arrows: green = the head follows the travel direction).\n"
    "4. Export KRL Code: the .src gets the header of the ACTIVE export profile\n"
    "   (Tools > Export Settings: TOOL/BASE, speed, rounding).\n\n"
    "- Turns per Layer and Number of Layers are exact (3 gives 3).\n"
    "- Turn Step E: distance between neighbouring turns (wall = Turns x E).\n"
    "- Layer Height: Z step between layers.\n"
    "- B / Tilt is used as typed (no limits).\n"
    "- The moves are shown rounded exactly as they are exported (Export Settings > Coordinate\n"
    "  decimals; changing it updates the text box if you did not edit it by hand).\n"
    "- The text box is exported as shown: you may add comments or approach moves\n"
    "  (Edit menu, inserted at the text cursor) or edit lines by hand.\n"
    "- Save Project keeps every input and the output, to repeat a print exactly.\n"
    "  Open Project also opens projects of the old cuboid / cylinder apps (a cuboid with a\n"
    "  hand-made base is offered to the manual editor).\n"
    "- A base built point by point: Tools > Manual 11-point editor (advanced)."
)
HELP_SHAPES = {
    "cuboid": (
        "Cuboid (rounded rectangle)\n\n"
        "- Centre X/Y, Length (X), Width (Y): the FIRST (inner) turn. Start Z: its height.\n"
        "- Corner Radius: blank = automatic (15 % of the shorter side, 2 mm .. 1/3).\n"
        "- Every next turn is the first one moved outward by E (corners keep their centre and\n"
        "  grow by E, so they stay round and tangent).\n"
        "- Layers alternate: even layers go outward, odd layers inward. Turn and layer changes\n"
        "  are tangent fillets at the top-right corner (purple).\n"
        "- Auto-Orient: A follows the travel direction (constant on straight edges, turning on\n"
        "  the corners); off: A/B/C as typed on every move."),
    "cylinder": (
        "Cylinder (tube)\n\n"
        "- Centre X/Y, Inner Diameter: the first (inner) ring. Start Z: its height.\n"
        "- Each ring is 4 quarter CIRCs, counter-clockwise, starting at the +X side.\n"
        "- The last quarter is the seam: there the path changes lane to the next ring (two\n"
        "  tangent arcs) or, on the last ring, climbs to the next layer (purple).\n"
        "- Even layers go outward, odd layers inward.\n"
        "- Helix (1 turn only): the climb is spread over the whole loop, no seam.\n"
        "- Auto-Orient: A follows the travel direction; off: A/B/C as typed."),
}
HELP_KEYS = (
    "Ctrl+G  Generate\n"
    "Ctrl+E  Export KRL Code\n"
    "Ctrl+Shift+D  3D View\n"
    "Ctrl+Shift+O / Ctrl+Shift+S  Open / Save Project\n"
    "Ctrl+Z / Ctrl+Y  Undo / Redo (inside the text box: undo / redo your typing)\n\n"
    "Top view: mouse wheel = zoom, drag = move, double-click = fit."
)


# ---------------------------------------------------------------------- old project files

def _num(v):
    """Number as field text with full precision: 535.0 -> '535', 22.5 -> '22.5'."""
    s = repr(float(v))
    return s[:-2] if s.endswith(".0") else s


def state_from_cylinder_project(data):
    """App7 project -> main-app state (same fields, exact counts, same generator)."""
    inp = data.get("inputs", {})
    return {"shape": "cylinder",
            "inputs": {"common": {k: inp[k] for k in ("step", "layer_height", "turns", "layers", "a", "b", "c")
                                  if k in inp},
                       "cylinder": {k: inp[k] for k in ("xc", "yc", "z0", "inner_diameter") if k in inp}},
            "options": dict(data.get("options", {})),
            "output": data.get("output", "")}


def state_from_cuboid_project(data):
    """App6 project -> main-app state, or None if its base was made by hand (no Auto-Generate
    parameters). App6 counted N+1 turns/layers and clamped the tilt to 5..20 deg; the main app
    is exact and uses B as typed, so the values are converted to give the same print."""
    bp = data.get("base_params")
    if not bp:
        return None
    ent = data.get("entries", {})
    opts = data.get("options", {})
    auto = bool(opts.get("auto_orient", True))

    def plus_one(key):
        text = str(ent.get(key, "")).strip()
        try:
            return str(int(float(text)) + 1)
        except ValueError:
            return None
    common = {"step": ent.get("E", ""), "layer_height": ent.get("W", ""), "a": ent.get("A", "180"),
              "c": ent.get("C", "180")}
    for key, name in (("turns", "turns"), ("layers", "layers")):
        v = plus_one(key)
        if v is not None:
            common[name] = v
    if auto:
        try:
            common["b"] = _num(max(5.0, min(float(ent.get("tilt", "")), 20.0)))
        except ValueError:
            pass
    else:
        common["b"] = ent.get("B", "0")
    common = {k: v for k, v in common.items() if str(v).strip() != ""}
    shape = {"xc": _num(bp["Xr"]), "yc": _num(bp["Yr"]), "z0": _num(bp["Zr"] + bp["Th"]),
             "length": _num(bp["L"]), "width": _num(bp["W"]),
             "corner_radius": "" if bp.get("r_auto") else _num(bp["r"])}
    return {"shape": "cuboid", "inputs": {"common": common, "cuboid": shape},
            "options": {"auto_orient": auto, "c_dis": bool(opts.get("c_dis", True)), "helix": False},
            "output": data.get("output", "")}


class MainApp:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        self.shape_var = tk.StringVar(value="cuboid")
        self.shape_vars = {s: {k: tk.StringVar(value=d) for k, _, d in f} for s, f in SHAPE_FIELDS.items()}
        self.vars = {k: tk.StringVar(value=d) for k, _, d in COMMON_FIELDS + ORIENT_FIELDS}
        self.auto_orient_var = tk.BooleanVar(value=True)
        self.helix_var = tk.BooleanVar(value=False)
        self.c_dis_var = tk.BooleanVar(value=True)
        self.undo_stack, self.redo_stack = [], []
        self.view = None                 # top view transform (s, tx, ty); None = fit on next draw
        self._build_menu()
        self._build_ui()
        self._show_shape_fields()
        self._bind_keys()

    # ================================================================== UI
    def _build_menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=False)
        f.add_command(label="Open Project...", accelerator="Ctrl+Shift+O", command=self.open_project)
        f.add_command(label="Save Project...", accelerator="Ctrl+Shift+S", command=self.save_project)
        f.add_separator()
        f.add_command(label="Export KRL Code (.src / .txt)...", accelerator="Ctrl+E", command=self.export)
        f.add_separator()
        f.add_command(label="Exit", command=self.root.destroy)
        m.add_cascade(label="File", menu=f)
        e = tk.Menu(m, tearoff=False)
        e.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo)
        e.add_command(label="Redo", accelerator="Ctrl+Y", command=self.redo)
        e.add_separator()
        e.add_command(label="Add Comment...", command=self.add_comment)
        e.add_command(label="Add Approach Move (PTP)...", command=self.add_approach)
        e.add_separator()
        e.add_command(label="Clear", command=self.clear)
        m.add_cascade(label="Edit", menu=e)
        t = tk.Menu(m, tearoff=False)
        t.add_command(label="3D View", accelerator="Ctrl+Shift+D", command=self.open_3d_view)
        t.add_command(label="Fit Top View", command=self.fit_view)
        t.add_separator()
        t.add_command(label="Export Settings (TOOL/BASE profiles)...",
                      command=lambda: export_settings_dialog.open_dialog(self.root, on_saved=self.on_profile_saved))
        t.add_separator()
        t.add_command(label="Manual 11-point editor (advanced)...", command=self.open_manual_editor)
        t.add_command(label="Free-form editor (experimental)...", command=self.open_free_form_editor)
        m.add_cascade(label="Tools", menu=t)
        h = tk.Menu(m, tearoff=False)
        h.add_command(label="How to use", command=lambda: messagebox.showinfo("How to use", HELP_GENERAL))
        h.add_command(label="Current shape", command=lambda: messagebox.showinfo(
            SHAPE_NAMES[self.shape_var.get()], HELP_SHAPES[self.shape_var.get()]))
        h.add_command(label="Keyboard and mouse", command=lambda: messagebox.showinfo("Keyboard and mouse", HELP_KEYS))
        m.add_cascade(label="Help", menu=h)
        self.root.config(menu=m)

    def _field(self, parent, row, var, label, width=12):
        tk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=2)
        tk.Entry(parent, textvariable=var, width=width).grid(row=row, column=1, sticky="w", padx=4, pady=2)

    def _build_ui(self):
        root = self.root
        left = tk.Frame(root)
        left.grid(row=0, column=0, sticky="nw", padx=10, pady=8)

        top = tk.Frame(left)
        top.pack(fill=tk.X, pady=(0, 6))
        tk.Label(top, text="Shape:", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self.shape_combo = ttk.Combobox(top, state="readonly", width=26,
                                        values=[SHAPE_NAMES[s] for s in SHAPE_FIELDS])
        self.shape_combo.set(SHAPE_NAMES[self.shape_var.get()])
        self.shape_combo.bind("<<ComboboxSelected>>", lambda e: self.set_shape(
            [s for s, n in SHAPE_NAMES.items() if n == self.shape_combo.get()][0]))
        self.shape_combo.pack(side=tk.LEFT, padx=6)

        self.shape_frame = ttk.LabelFrame(left, text="Shape")
        self.shape_frame.pack(fill=tk.X, pady=(0, 6))

        path = ttk.LabelFrame(left, text="Path")
        path.pack(fill=tk.X, pady=(0, 6))
        for r, (k, label, _) in enumerate(COMMON_FIELDS):
            self._field(path, r, self.vars[k], label)

        orient = ttk.LabelFrame(left, text="Orientation")
        orient.pack(fill=tk.X, pady=(0, 6))
        for r, (k, label, _) in enumerate(ORIENT_FIELDS):
            self._field(orient, r, self.vars[k], label)
        tk.Checkbutton(orient, text="Auto-Orient Along Travel (A follows the path)",
                       variable=self.auto_orient_var).grid(row=3, column=0, columnspan=2, sticky="w", padx=4)

        opts = ttk.LabelFrame(left, text="Options")
        opts.pack(fill=tk.X, pady=(0, 6))
        tk.Checkbutton(opts, text="Approximate Moves on Export (C_DIS)", variable=self.c_dis_var).pack(anchor="w", padx=4)
        self.helix_check = tk.Checkbutton(opts, text="Helix (single-wall tube, 1 turn only)", variable=self.helix_var)

        buttons = tk.Frame(left)
        buttons.pack(fill=tk.X, pady=4)
        rows = [[("Generate", self.generate), ("3D View", self.open_3d_view), ("Export KRL Code", self.export),
                 ("Clear", self.clear)],
                [("Undo", self.undo), ("Redo", self.redo), ("Add Comment...", self.add_comment),
                 ("Add Approach...", self.add_approach)]]
        for r, row in enumerate(rows):
            for col, (text, cmd) in enumerate(row):
                tk.Button(buttons, text=text, command=cmd, width=13).grid(row=r, column=col, padx=2, pady=2)

        right = tk.Frame(root)
        right.grid(row=0, column=1, sticky="nsew", padx=10, pady=8)
        tk.Label(right, text="Top view (X right, Y up)  -  purple: transitions  -  wheel: zoom, drag: move, "
                             "double-click: fit", fg="#555555", font=("Segoe UI", 8)).pack(anchor="w")
        self.canvas = tk.Canvas(right, width=460, height=440, bg="white", highlightthickness=1,
                                highlightbackground="#cccccc")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.info = tk.Label(right, text="", justify=tk.LEFT, anchor="w", fg="#333333", font=("Segoe UI", 8))
        self.info.pack(fill=tk.X, pady=(4, 0))
        c = self.canvas
        c.bind("<MouseWheel>", self._wheel)
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<Double-Button-1>", lambda e: self.fit_view())
        c.bind("<Configure>", lambda e: self.redraw())

        out = tk.Frame(root)
        out.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))
        self.output_text = tk.Text(out, height=12, width=120, font=("Consolas", 9), wrap=tk.NONE, undo=True)
        ys = tk.Scrollbar(out, command=self.output_text.yview)
        xs = tk.Scrollbar(out, orient=tk.HORIZONTAL, command=self.output_text.xview)
        self.output_text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.output_text.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        out.grid_rowconfigure(0, weight=1)
        out.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)
        root.grid_columnconfigure(1, weight=1)

    def _show_shape_fields(self):
        for w in self.shape_frame.winfo_children():
            w.destroy()
        shape = self.shape_var.get()
        self.shape_frame.config(text=SHAPE_NAMES[shape])
        for r, (k, label, _) in enumerate(SHAPE_FIELDS[shape]):
            self._field(self.shape_frame, r, self.shape_vars[shape][k], label)
        if shape == "cylinder":
            self.helix_check.pack(anchor="w", padx=4)
        else:
            self.helix_check.pack_forget()

    def set_shape(self, shape):
        """Switch the shape panel (each shape keeps its own values)."""
        self.shape_var.set(shape)
        self.shape_combo.set(SHAPE_NAMES[shape])
        self._show_shape_fields()

    def _bind_keys(self):
        r = self.root
        r.bind_all("<Control-g>", lambda e: self.generate())
        r.bind_all("<Control-e>", lambda e: self.export())
        r.bind_all("<Control-Shift-D>", lambda e: self.open_3d_view())
        r.bind_all("<Control-Shift-O>", lambda e: self.open_project())
        r.bind_all("<Control-Shift-S>", lambda e: self.save_project())
        r.bind_all("<Control-z>", lambda e: None if e.widget is self.output_text else self.undo())
        r.bind_all("<Control-y>", lambda e: None if e.widget is self.output_text else self.redo())

    # ================================================================== state / undo
    def state(self):
        return {
            "shape": self.shape_var.get(),
            "inputs": {"common": {k: v.get() for k, v in self.vars.items()},
                       **{s: {k: v.get() for k, v in fs.items()} for s, fs in self.shape_vars.items()}},
            "options": {"auto_orient": self.auto_orient_var.get(), "helix": self.helix_var.get(),
                        "c_dis": self.c_dis_var.get()},
            "output": self.output_text.get("1.0", "end-1c"),
        }

    def set_state(self, st, redraw=True):
        """Restore inputs, options, shape and output (unknown keys are ignored)."""
        shape = st.get("shape", "cuboid")
        if shape not in SHAPE_FIELDS:
            shape = "cuboid"
        inputs = st.get("inputs", {})
        for k, v in inputs.get("common", {}).items():
            if k in self.vars:
                self.vars[k].set(str(v))
        for s, fs in self.shape_vars.items():
            for k, v in inputs.get(s, {}).items():
                if k in fs:
                    fs[k].set(str(v))
        opts = st.get("options", {})
        self.auto_orient_var.set(bool(opts.get("auto_orient", True)))
        self.helix_var.set(bool(opts.get("helix", False)))
        self.c_dis_var.set(bool(opts.get("c_dis", True)))
        self.set_shape(shape)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", st.get("output", ""))
        self.output_text.edit_reset()
        if redraw:
            self.view = None
            self.redraw()
            self._update_info()

    def push_undo(self):
        self.undo_stack.append(copy.deepcopy(self.state()))
        del self.undo_stack[:-UNDO_LIMIT]
        self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.state())
            self.set_state(self.undo_stack.pop())

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.state())
            self.set_state(self.redo_stack.pop())

    # ================================================================== generate
    def read_params(self, quiet=False):
        """Parameters of the current shape, or None (after an error message unless quiet)."""
        if quiet:
            show = messagebox.showerror
            messagebox.showerror = lambda *a, **k: None
            try:
                return self.read_params()
            finally:
                messagebox.showerror = show
        shape = self.shape_var.get()
        fs = self.shape_vars[shape]
        try:
            common = {k: float(self.vars[k].get()) for k in ("step", "layer_height", "a", "b", "c")}
            turns_f, layers_f = float(self.vars["turns"].get()), float(self.vars["layers"].get())
            vals = {}
            for k, label, _ in SHAPE_FIELDS[shape]:
                text = fs[k].get().strip()
                if k == "corner_radius" and not text:
                    vals[k] = None
                else:
                    vals[k] = float(text)
        except ValueError:
            messagebox.showerror("Input Error", "Please enter numbers in all fields (Corner Radius may be blank).")
            return None
        if turns_f != int(turns_f) or layers_f != int(layers_f):
            messagebox.showerror("Input Error", "Turns and layers must be whole numbers.")
            return None
        turns, layers = int(turns_f), int(layers_f)
        if shape == "cuboid":
            return cuboid.CuboidParams(length=vals["length"], width=vals["width"], corner_radius=vals["corner_radius"],
                                       xc=vals["xc"], yc=vals["yc"], z0=vals["z0"], turns=turns, layers=layers,
                                       auto_orient=self.auto_orient_var.get(), **common)
        return cylinder.CylinderParams(xc=vals["xc"], yc=vals["yc"], z0=vals["z0"],
                                       inner_diameter=vals["inner_diameter"], turns=turns, layers=layers,
                                       auto_orient=self.auto_orient_var.get(), helix=self.helix_var.get(), **common)

    def _generator(self):
        return cuboid if self.shape_var.get() == "cuboid" else cylinder

    def generate(self, record_undo=True):
        p = self.read_params()
        if p is None:
            return False
        gen = self._generator()
        errors, warnings = gen.validate(p)
        if errors:
            messagebox.showerror("Input Error", "\n".join(errors))
            return False
        items, info = gen.generate(p)
        if record_undo:
            self.push_undo()
        self.show_items(items)
        if warnings:
            messagebox.showwarning("Check the path", "\n".join(warnings))
        return True

    # ---------------------------------------------------------------- shown rounding
    def _decimals(self):
        """Decimals of the active export profile (None = full precision): the text box shows
        the values exactly as they will be exported."""
        return krl_export.active_settings()[0].decimals

    def round_text(self, text):
        """KRL text with the move values rounded like the export (other lines unchanged)."""
        d = self._decimals()
        return text if d is None else pm.program_to_krl(pm.parse_krl(text), decimals=d)

    def show_items(self, items):
        """Put generated moves into the text box, rounded like the export. The full-precision
        items are kept, so a later change of the profile's decimals can re-render them."""
        text = pm.program_to_krl(items, decimals=self._decimals()) + "\n"
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, text)
        self.output_text.edit_reset()
        self._generated = (items, text)
        self.view = None
        self.redraw()
        self._update_info()

    def on_profile_saved(self, _settings=None):
        """Export Settings saved: if the box still holds the generated text (no hand edits),
        show it again with the (possibly new) decimals."""
        gen = getattr(self, "_generated", None)
        if gen and self.output_text.get("1.0", "end-1c") == gen[1]:
            self.show_items(gen[0])
        else:
            self._update_info()

    def _update_info(self):
        items = pm.parse_krl(self.body_text())
        start, moves = pm.path_3d(items)
        if not moves:
            self.info.config(text="")
            return
        pts = [q for m in moves for q in m['pts']]
        xs, ys, zs = [q[0] for q in pts], [q[1] for q in pts], [q[2] for q in pts]
        hc = pm.heading_checks(items)
        a_txt = ("A vs travel: max %.1f deg" % max(h['dev'] for h in hc)) if hc else "no A values"
        settings = krl_export.active_settings()[0]
        shown = ("values as exported: %d decimals (profile %s)" % (settings.decimals, settings.profile)
                 if settings.decimals is not None else "values at full precision (profile %s)" % settings.profile)
        self.info.config(text=(
            "%d moves  |  path %.2f m  |  X %.1f..%.1f  Y %.1f..%.1f  Z %.1f..%.1f mm  |  %s\n%s"
            % (len(moves), pm.path_length(moves) / 1000.0, min(xs), max(xs), min(ys), max(ys), min(zs), max(zs),
               a_txt, shown)))

    def clear(self):
        self.push_undo()
        self.output_text.delete("1.0", tk.END)
        self.output_text.edit_reset()
        self.view = None
        self.redraw()
        self.info.config(text="")

    def body_text(self):
        return self.output_text.get("1.0", tk.END)

    # ================================================================== edit helpers
    def add_comment(self):
        win = tk.Toplevel(self.root)
        win.title("Add Comment")
        tk.Label(win, text="Comment (inserted at the text cursor as a '; ...' line):").pack(padx=10, pady=(10, 4))
        var = tk.StringVar()
        entry = tk.Entry(win, textvariable=var, width=60)
        entry.pack(padx=10)
        entry.focus_set()

        def ok(event=None):
            text = var.get().strip()
            if text:
                self.insert_line(pm.Comment(text).to_krl())
            win.destroy()
        tk.Button(win, text="Add", command=ok, width=10).pack(pady=8)
        entry.bind("<Return>", ok)
        return win

    def add_approach(self):
        win = tk.Toplevel(self.root)
        win.title("Add Approach Move (PTP)")
        tk.Label(win, text="PTP move, inserted at the text cursor (e.g. above the start point):").grid(
            row=0, column=0, columnspan=6, padx=10, pady=(10, 4))
        vars_ = {}
        for i, key in enumerate("XYZABC"):
            tk.Label(win, text=key + ":").grid(row=1 + i // 3, column=(i % 3) * 2, padx=4, pady=2, sticky="e")
            vars_[key] = tk.StringVar(value={"A": self.vars["a"].get(), "B": self.vars["b"].get(),
                                             "C": self.vars["c"].get()}.get(key, ""))
            tk.Entry(win, textvariable=vars_[key], width=10).grid(row=1 + i // 3, column=(i % 3) * 2 + 1, padx=4, pady=2)

        def ok():
            try:
                v = [float(vars_[k].get()) for k in "XYZABC"]
            except ValueError:
                messagebox.showwarning("Add Approach Move", "Please enter numbers for X, Y, Z, A, B and C.", parent=win)
                return
            self.insert_line(pm.Ptp(pm.pose(v[:3], v[3:], cuboid.PTP_S, cuboid.PTP_T)).to_krl())
            win.destroy()
        tk.Button(win, text="Add", command=ok, width=10).grid(row=3, column=0, columnspan=6, pady=8)
        win.vars = vars_
        win.ok = ok
        return win

    def insert_line(self, line):
        """Insert a whole line at the start of the line where the text cursor is (undoable)."""
        self.push_undo()
        self.output_text.insert("insert linestart", line + "\n")
        self.redraw()
        self._update_info()

    # ================================================================== top view
    def fit_view(self):
        self.view = None
        self.redraw()

    def _fit(self, pts, W, H):
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
        s = 0.9 * min(W, H) / span
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        return s, W / 2 - cx * s, H / 2 + cy * s

    def redraw(self):
        c = self.canvas
        c.delete("all")
        start, moves = pm.path_3d(pm.parse_krl(self.body_text()))
        pts = [q for m in moves for q in m['pts']] + ([start] if start else [])
        if not pts:
            return
        W, H = max(c.winfo_width(), int(c.cget("width"))), max(c.winfo_height(), int(c.cget("height")))
        if self.view is None:
            self.view = self._fit(pts, W, H)
        s, tx, ty = self.view
        scr = lambda q: (tx + q[0] * s, ty - q[1] * s)
        for m in moves:
            coords = []
            for q in m['pts']:
                coords.extend(scr(q))
            c.create_line(*coords, fill=TRANSITION_COLOR if m['transition'] else PATH_COLOR,
                          width=2 if m['transition'] else 1)
        for q, col in ((start, "#2ca02c"), (moves[-1]['pts'][-1] if moves else None, "#d62728")):
            if q:
                x, y = scr(q)
                c.create_oval(x - 4, y - 4, x + 4, y + 4, fill=col, outline="")
        c.create_text(8, H - 8, anchor="sw", fill="#777777", font=("Segoe UI", 8),
                      text="green = start, red = end")

    def _wheel(self, e):
        if self.view is None:
            return
        f = 1.2 if e.delta > 0 else 1 / 1.2
        s, tx, ty = self.view
        self.view = (s * f, e.x - (e.x - tx) * f, e.y - (e.y - ty) * f)
        self.redraw()

    def _press(self, e):
        self._last = (e.x, e.y)

    def _drag(self, e):
        if self.view is None:
            return
        dx, dy = e.x - self._last[0], e.y - self._last[1]
        self._last = (e.x, e.y)
        s, tx, ty = self.view
        self.view = (s, tx + dx, ty + dy)
        self.redraw()

    # ================================================================== windows / files
    def open_3d_view(self):
        view3d.open_view(self.root, self.body_text, "Nothing to show yet. Press Generate first.")

    def _start_tool(self, script_name, title, extra_args=()):
        """Start one of the older editors as its own window. '--from-main' makes its Back
        button just close it (this app stays open)."""
        try:
            subprocess.Popen(tool_command(script_name) + ["--from-main"] + list(extra_args))
        except OSError as ex:
            messagebox.showerror(title, "Could not start the %s:\n%s" % (title.lower(), ex))

    def open_manual_editor(self, project_path=None):
        """Start the manual 11-point editor (App6), optionally opening a cuboid project in it."""
        self._start_tool("PythonApplication6.py", "Manual editor", [project_path] if project_path else [])

    def open_free_form_editor(self):
        """Start the free-form LIN/CIRC editor (App5, experimental)."""
        self._start_tool("PythonApplication5.py", "Free-form editor")

    def export(self):
        if not self.body_text().strip():
            messagebox.showinfo("Export", "Nothing to export yet. Press Generate first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".src", title="Export KRL Code",
                                            filetypes=[("KRL program", "*.src"), ("Text file", "*.txt")])
        if path:
            self.export_to(path)

    def export_to(self, path):
        """Write the .src (or .txt) for the current text. Returns True if written."""
        name = os.path.splitext(os.path.basename(path))[0]
        if not krl_export.is_valid_program_name(name):
            messagebox.showerror("Invalid File Name", "'%s' is not a valid KRL program name.\n\n%s\n\nNothing was saved."
                                 % (name, krl_export.PROGRAM_NAME_RULE))
            return False
        settings, profile_error = krl_export.active_settings()
        if profile_error:
            messagebox.showwarning("Export Settings", profile_error)
        code = krl_export.build_program(name, self.body_text(), settings, approximate=self.c_dis_var.get())
        with open(path, "w") as f:
            f.write(code)
        messagebox.showinfo("KRL Code Exported", "Exported with profile '%s'." % settings.profile)
        return True

    def save_project(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=project_files.FILETYPES,
                                            title="Save Project")
        if path:
            self.save_project_to(path)

    def save_project_to(self, path):
        try:
            project_files.save_project(path, "main", self.state())
        except OSError as ex:
            messagebox.showerror("Save Project", "Could not save the project:\n%s" % ex)
            return False
        self._set_title(path)
        return True

    def open_project(self):
        path = filedialog.askopenfilename(filetypes=project_files.FILETYPES, title="Open Project")
        if path:
            self.open_project_from(path)

    def open_project_from(self, path):
        """Restore everything, regenerate, and keep the SAVED output if it differs (hand
        edits or a program change). One undo step. Returns True if loaded."""
        try:
            data = project_files.load_project_any(path)
        except project_files.ProjectError as ex:
            messagebox.showerror("Open Project", str(ex))
            return False
        kind = data["app"]
        if kind == "main":
            st = data
        elif kind == "cylinder":
            st = state_from_cylinder_project(data)
        else:
            st = state_from_cuboid_project(data)
            if st is None:
                if messagebox.askyesno(
                        "Open Project",
                        "This cuboid project has a base made point by point (manual or imported), "
                        "which has no size parameters.\n\nOpen it in the Manual 11-point editor?"):
                    self.open_manual_editor(path)
                return False
        self.push_undo()
        saved = st.get("output", "")
        self.set_state(st, redraw=False)
        if saved.strip():
            if kind == "cuboid" and "===== LAYER" not in saved:
                messagebox.showinfo("Open Project",
                                    "This cuboid project was saved before Automate (base loop only).\n\n"
                                    "The sizes were loaded and the saved output was kept. Press Generate "
                                    "to create the print.")
            else:
                # Same print if the regenerated output equals the saved one after rounding both
                # like the export (older projects were saved at full precision). Then show the
                # regenerated output (rounded); otherwise keep the saved text as it is.
                p = self.read_params(quiet=True)
                same = False
                if p is not None and not self._generator().validate(p)[0]:
                    items, _ = self._generator().generate(p)
                    same = self.round_text(pm.program_to_krl(items) + "\n") == self.round_text(saved)
                    if same:
                        self.show_items(items)
                if not same:
                    messagebox.showinfo("Open Project",
                                        "The saved output differs from what this version generates "
                                        "(hand edits, or a program change).\n\nThe SAVED output was kept. "
                                        "Press Generate to regenerate it from the inputs.")
        self.view = None
        self.redraw()
        self._update_info()
        self._set_title(path, converted_from=None if kind == "main" else project_files.APP_NAMES[kind])
        warning = project_files.profile_mismatch(data)
        if warning:
            messagebox.showwarning("Open Project", warning)
        return True

    def _set_title(self, path=None, converted_from=None):
        title = APP_TITLE
        if path:
            title += " - " + os.path.basename(path)
            if converted_from:
                title += " (from the %s; Save Project writes the new format)" % converted_from
        self.root.title(title)


# ---------------------------------------------------------------------- entry point / exe

TOOLS = {"manual": "PythonApplication6.py", "freeform": "PythonApplication5.py"}


def is_frozen():
    """True when running as the packaged .exe (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def tool_command(script_name):
    """Command that starts one of the older editors: the same .exe with --tool when packaged
    (there are no .py files on the lab PC), else python + the script."""
    if is_frozen():
        name = [k for k, v in TOOLS.items() if v == script_name][0]
        return [sys.executable, "--tool", name]
    return [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), script_name)]


def run_tool(name, args):
    """Run an older editor in this process (they build their window when imported)."""
    sys.argv = [TOOLS[name]] + list(args)
    if name == "manual":
        import PythonApplication6  # noqa: F401  (runs the manual 11-point editor)
    else:
        import PythonApplication5  # noqa: F401  (runs the free-form editor)


def selftest(quiet=False):
    """Generate and export a cuboid and a cylinder (built-in defaults) into a temporary folder,
    check the files, and write selftest_report.txt next to the program. Returns 0 if all OK.
    For checking the packaged .exe on a new PC: KRL_Generator.exe --selftest"""
    import tempfile
    lines, ok = [], True
    originals = {f: getattr(messagebox, f) for f in ("showinfo", "showwarning", "showerror")}
    for f in originals:                         # no pop-ups while testing
        setattr(messagebox, f, lambda *a, **k: None)
    root = tk.Tk()
    root.withdraw()
    try:
        app = MainApp(root)
        tmp = tempfile.mkdtemp(prefix="krl_selftest_")
        settings, profile_error = krl_export.active_settings()
        lines.append("Program folder: %s" % krl_export.app_dir())
        if not os.path.exists(krl_export.PROFILES_PATH):
            source = "built-in, no export_profiles.json next to the program"
        else:
            source = profile_error or "export_profiles.json OK"
        lines.append("Export profile: %s (%s)" % (settings.profile, source))
        lines.append("  TOOL_DATA[%d] = {%s}" % (settings.tool_no, krl_export._frame(settings.tool)))
        lines.append("  BASE_DATA[%d] = {%s}" % (settings.base_no, krl_export._frame(settings.base)))
        lines.append("  decimals: %s, $APO.CDIS %s mm, VEL_CP %s m/s" % (
            "full precision" if settings.decimals is None else settings.decimals, settings.cdis, settings.vel_cp))
        for shape in ("cuboid", "cylinder"):
            app.set_shape(shape)
            good = app.generate()
            path = os.path.join(tmp, "SELFTEST_%s.src" % shape.upper())
            good = good and app.export_to(path)
            text = open(path).read() if good and os.path.exists(path) else ""
            items = pm.parse_krl(text)
            n_moves = sum(isinstance(i, (pm.Lin, pm.Circ)) for i in items)
            dev = max([h['dev'] for h in pm.heading_checks(items)] or [999])
            good = good and text.startswith("&ACCESS") and text.endswith("END") and n_moves > 10 and dev < 1.0
            ok = ok and good
            lines.append("%-8s %s: %d moves, A vs travel max %.2f deg, %d bytes" % (
                shape, "OK" if good else "FAIL", n_moves, dev, len(text)))
    except Exception as ex:                     # report anything unexpected instead of crashing
        ok = False
        lines.append("FAIL: %s: %s" % (type(ex).__name__, ex))
    finally:
        root.destroy()
        for f, fn in originals.items():
            setattr(messagebox, f, fn)
    lines.insert(0, "KRL Generator self-test: %s" % ("OK" if ok else "FAILED"))
    report = "\n".join(lines)
    try:
        with open(os.path.join(krl_export.app_dir(), "selftest_report.txt"), "w") as f:
            f.write(report + "\n")
    except OSError:
        pass
    if not quiet:                               # the windowed .exe has no console: show it
        r = tk.Tk()
        r.withdraw()
        (messagebox.showinfo if ok else messagebox.showerror)("KRL Generator self-test", report, parent=r)
        r.destroy()
    print(report)
    return 0 if ok else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        sys.exit(selftest(quiet="--quiet" in argv))
    if "--tool" in argv:
        i = argv.index("--tool")
        name = argv[i + 1] if i + 1 < len(argv) else ""
        if name not in TOOLS:
            raise SystemExit("unknown tool %r (use: %s)" % (name, ", ".join(TOOLS)))
        run_tool(name, argv[:i] + argv[i + 2:])
        return
    root = tk.Tk()
    MainApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
