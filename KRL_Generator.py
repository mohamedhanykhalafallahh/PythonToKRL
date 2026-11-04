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
    "- The text box is exported as shown: you may add comments or approach moves\n"
    "  (Edit menu, inserted at the text cursor) or edit lines by hand.\n"
    "- Save Project keeps every input and the output, to repeat a print exactly.\n"
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
                      command=lambda: export_settings_dialog.open_dialog(self.root))
        t.add_separator()
        t.add_command(label="Manual 11-point editor (advanced)...", command=self.open_manual_editor)
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
    def read_params(self):
        """Parameters of the current shape, or None (after an error message)."""
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
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, pm.program_to_krl(items) + "\n")
        self.output_text.edit_reset()
        self.view = None
        self.redraw()
        self._update_info()
        if warnings:
            messagebox.showwarning("Check the path", "\n".join(warnings))
        return True

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
        self.info.config(text=(
            "%d moves  |  path %.2f m  |  X %.1f..%.1f  Y %.1f..%.1f  Z %.1f..%.1f mm  |  %s"
            % (len(moves), pm.path_length(moves) / 1000.0, min(xs), max(xs), min(ys), max(ys), min(zs), max(zs), a_txt)))

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

    def open_manual_editor(self):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PythonApplication6.py")
        try:
            subprocess.Popen([sys.executable, script])
        except OSError as ex:
            messagebox.showerror("Manual editor", "Could not start the manual editor:\n%s" % ex)

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
        return True

    def open_project(self):
        path = filedialog.askopenfilename(filetypes=project_files.FILETYPES, title="Open Project")
        if path:
            self.open_project_from(path)

    def open_project_from(self, path):
        """Restore everything, regenerate, and keep the SAVED output if it differs (hand
        edits or a program change). One undo step. Returns True if loaded."""
        try:
            data = project_files.load_project(path, "main")
        except project_files.ProjectError as ex:
            messagebox.showerror("Open Project", str(ex))
            return False
        self.push_undo()
        saved = data.get("output", "")
        self.set_state(data, redraw=False)
        if saved.strip():
            p = self.read_params()
            same = False
            if p is not None and not self._generator().validate(p)[0]:
                items, _ = self._generator().generate(p)
                same = pm.program_to_krl(items) + "\n" == saved
            if not same:
                messagebox.showinfo("Open Project",
                                    "The saved output differs from what this version generates "
                                    "(hand edits, or a program change).\n\nThe SAVED output was kept. "
                                    "Press Generate to regenerate it from the inputs.")
        self.view = None
        self.redraw()
        self._update_info()
        warning = project_files.profile_mismatch(data)
        if warning:
            messagebox.showwarning("Open Project", warning)
        return True


def main():
    root = tk.Tk()
    MainApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
