"""Cylinder KRL Code Generator (App7).

Generates a tube / thick-walled cylinder as one continuous path (rings joined by tangent
lane changes, layers alternating outward / inward) and exports it as a KUKA .src file.

The geometry is in cylinder.py, the KRL lines in path_model.py, the .src header in
krl_export.py and the 3D window in view3d.py (all shared with the cuboid app).
"""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cylinder
import export_settings_dialog
import krl_export
import path_model as pm
import project_files
import view3d

TRANSITION_COLOR = "purple"
PATH_COLOR = "#1f77b4"

# (key, label, default) of the numeric inputs
SHAPE_FIELDS = [
    ("xc", "Centre X (mm):", "535"),
    ("yc", "Centre Y (mm):", "10"),
    ("z0", "Start Z (mm):", "65"),
    ("inner_diameter", "Inner Diameter (mm):", "100"),
    ("step", "Ring Step E (mm):", "2"),
    ("layer_height", "Layer Height (mm):", "2"),
    ("turns", "Turns per Layer:", "3"),
    ("layers", "Number of Layers:", "2"),
]
ORIENT_FIELDS = [
    ("a", "A (deg):", "180"),
    ("b", "B / Tilt (deg):", "20"),
    ("c", "C (deg):", "180"),
]

HELP_TEXT = (
    "Path\n"
    "- Each layer has 'Turns' concentric rings, E apart, starting at the inner diameter "
    "(wall thickness = Turns x E).\n"
    "- A ring is 4 quarter CIRCs, counter-clockwise, starting at the +X side.\n"
    "- The last quarter of a ring is the seam: there the path changes lane to the next ring "
    "(two tangent arcs) or, on the last ring, climbs to the next layer.\n"
    "- Even layers go outward, odd layers inward (like the cuboid app).\n"
    "- Helix (only with 1 turn): the climb is spread over the whole loop, no seam.\n"
    "- Turns and Layers are exact (N gives N).\n\n"
    "Orientation\n"
    "- Auto-Orient on: A follows the travel direction (the lamp trails), B = tilt, C as entered.\n"
    "- Auto-Orient off: A, B, C are used as entered on every move.\n\n"
    "Export\n"
    "- The .src header (TOOL/BASE/speed) is the same as in the cuboid app.\n"
    "- The file name becomes the program name: letters, digits and '_' only, max 24.\n"
    "- The text box is exported as shown (you may add comments)."
)


class CylinderApp:
    def __init__(self, root):
        self.root = root
        root.title("Cylinder KRL Code Generator")
        self.vars = {}
        self.auto_orient_var = tk.BooleanVar(value=True)
        self.helix_var = tk.BooleanVar(value=False)
        self.c_dis_var = tk.BooleanVar(value=True)
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = self.root
        top = tk.Frame(root)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 0))
        tk.Button(top, text="← Back", command=self.go_back_to_selector).pack(side=tk.LEFT)
        tk.Label(top, text="Cylinder KRL Code Generator", font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT, padx=20)
        tk.Button(top, text="Help", command=lambda: messagebox.showinfo("Cylinder: how it works", HELP_TEXT)).pack(side=tk.RIGHT)

        left = tk.Frame(root)
        left.grid(row=1, column=0, sticky="n", padx=10, pady=8)

        shape = ttk.LabelFrame(left, text="Shape")
        shape.pack(fill=tk.X, pady=(0, 8))
        for row, (key, label, default) in enumerate(SHAPE_FIELDS):
            self._field(shape, row, key, label, default)

        orient = ttk.LabelFrame(left, text="Orientation")
        orient.pack(fill=tk.X, pady=(0, 8))
        for row, (key, label, default) in enumerate(ORIENT_FIELDS):
            self._field(orient, row, key, label, default)
        tk.Checkbutton(orient, text="Auto-Orient Along Travel (A follows the path)",
                       variable=self.auto_orient_var).grid(row=3, column=0, columnspan=2, sticky="w", padx=4)

        opts = ttk.LabelFrame(left, text="Options")
        opts.pack(fill=tk.X, pady=(0, 8))
        tk.Checkbutton(opts, text="Helix (single-wall tube, 1 turn only)",
                       variable=self.helix_var).pack(anchor="w", padx=4)
        tk.Checkbutton(opts, text="Approximate Moves on Export (C_DIS)",
                       variable=self.c_dis_var).pack(anchor="w", padx=4)

        buttons = tk.Frame(left)
        buttons.pack(fill=tk.X, pady=4)
        for col, (text, cmd) in enumerate((("Generate", self.generate), ("3D View", self.open_3d_view),
                                           ("Export KRL Code", self.export), ("Clear", self.clear))):
            tk.Button(buttons, text=text, command=cmd, width=13).grid(row=0, column=col, padx=3, pady=3)
        tk.Button(buttons, text="Open Project...", command=self.open_project).grid(
            row=1, column=0, sticky="ew", padx=3, pady=(0, 3))
        tk.Button(buttons, text="Save Project...", command=self.save_project).grid(
            row=1, column=1, sticky="ew", padx=3, pady=(0, 3))
        tk.Button(buttons, text="Export Settings (profiles)...",
                  command=lambda: export_settings_dialog.open_dialog(self.root)).grid(
            row=1, column=2, columnspan=2, sticky="ew", padx=3, pady=(0, 3))

        right = tk.Frame(root)
        right.grid(row=1, column=1, sticky="n", padx=10, pady=8)
        tk.Label(right, text="Top view (X right, Y up) - purple: lane changes / layer climbs",
                 fg="#555555", font=("Segoe UI", 8)).pack(anchor="w")
        self.canvas = tk.Canvas(right, width=420, height=420, bg="white", highlightthickness=1,
                                highlightbackground="#cccccc")
        self.canvas.pack()
        self.info = tk.Label(right, text="", justify=tk.LEFT, anchor="w", fg="#333333", font=("Segoe UI", 8))
        self.info.pack(fill=tk.X, pady=(4, 0))

        out = tk.Frame(root)
        out.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))
        self.output_text = tk.Text(out, height=12, width=110, font=("Consolas", 9), wrap=tk.NONE)
        yscroll = tk.Scrollbar(out, command=self.output_text.yview)
        xscroll = tk.Scrollbar(out, orient=tk.HORIZONTAL, command=self.output_text.xview)
        self.output_text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.output_text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        out.grid_rowconfigure(0, weight=1)
        out.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)
        root.grid_columnconfigure(1, weight=1)

    def _field(self, parent, row, key, label, default):
        tk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=2)
        var = tk.StringVar(value=default)
        tk.Entry(parent, textvariable=var, width=12).grid(row=row, column=1, padx=4, pady=2)
        self.vars[key] = var

    # ------------------------------------------------------------------ actions
    def read_params(self):
        """CylinderParams from the inputs, or None (after showing an error)."""
        try:
            num = {k: float(self.vars[k].get()) for k in
                   ("xc", "yc", "z0", "inner_diameter", "step", "layer_height", "a", "b", "c")}
            turns_f, layers_f = float(self.vars["turns"].get()), float(self.vars["layers"].get())
        except ValueError:
            messagebox.showerror("Input Error", "Please enter numbers in all fields.")
            return None
        if turns_f != int(turns_f) or layers_f != int(layers_f):
            messagebox.showerror("Input Error", "Turns and layers must be whole numbers.")
            return None
        return cylinder.CylinderParams(turns=int(turns_f), layers=int(layers_f),
                                       auto_orient=self.auto_orient_var.get(),
                                       helix=self.helix_var.get(), **num)

    def generate(self):
        p = self.read_params()
        if p is None:
            return False
        errors, warnings = cylinder.validate(p)
        if errors:
            messagebox.showerror("Input Error", "\n".join(errors))
            return False
        items, info = cylinder.generate(p)
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, pm.program_to_krl(items) + "\n")
        self.redraw()
        self.info.config(text=(
            "%d moves  |  path %.2f m  |  wall %.1f mm (%d x %g)  |  Z %.1f to %.1f mm  |  arc radii %.1f to %.1f mm"
            % (info["moves"], info["length_mm"] / 1000.0, info["wall_thickness"], p.turns, p.step,
               info["z_range"][0], info["z_range"][1], info["min_arc_radius"], info["max_arc_radius"])))
        if warnings:
            messagebox.showwarning("Check the path", "\n".join(warnings))
        return True

    def clear(self):
        self.output_text.delete("1.0", tk.END)
        self.canvas.delete("all")
        self.info.config(text="")

    def body_text(self):
        return self.output_text.get("1.0", tk.END)

    def open_3d_view(self):
        view3d.open_view(self.root, self.body_text, "Nothing to show yet. Press Generate first.")

    def export(self):
        if not self.body_text().strip():
            messagebox.showinfo("Export", "Nothing to export yet. Press Generate first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".src", filetypes=[("KRL files", "*.src")])
        if path:
            self.export_to(path)

    def export_to(self, path):
        """Write the .src for the current text to `path`. Returns True if written."""
        name = os.path.splitext(os.path.basename(path))[0]
        if not krl_export.is_valid_program_name(name):
            messagebox.showerror("Invalid File Name",
                                 "'%s' is not a valid KRL program name.\n\n%s\n\nNothing was saved."
                                 % (name, krl_export.PROGRAM_NAME_RULE))
            return False
        settings, profile_error = krl_export.active_settings()
        if profile_error:
            messagebox.showwarning("Export Settings", profile_error)
        code = krl_export.build_program(name, self.body_text(), settings, approximate=self.c_dis_var.get())
        with open(path, "w") as f:
            f.write(code)
        messagebox.showinfo("KRL Code Exported", "The KRL code has been exported successfully.")
        return True

    # ------------------------------------------------------------------ project files
    def project_data(self):
        return {
            "inputs": {k: v.get() for k, v in self.vars.items()},
            "options": {"auto_orient": self.auto_orient_var.get(), "helix": self.helix_var.get(),
                        "c_dis": self.c_dis_var.get()},
            "output": self.output_text.get("1.0", "end-1c"),
        }

    def save_project(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=project_files.FILETYPES,
                                            title="Save Project")
        if path:
            self.save_project_to(path)

    def save_project_to(self, path):
        try:
            project_files.save_project(path, "cylinder", self.project_data())
        except OSError as ex:
            messagebox.showerror("Save Project", "Could not save the project:\n%s" % ex)
            return False
        return True

    def open_project(self):
        path = filedialog.askopenfilename(filetypes=project_files.FILETYPES, title="Open Project")
        if path:
            self.open_project_from(path)

    def open_project_from(self, path):
        """Restore the inputs, regenerate, and keep the SAVED output if it differs from what
        this version generates (hand edits or a program change). Returns True if loaded."""
        try:
            data = project_files.load_project(path, "cylinder")
        except project_files.ProjectError as ex:
            messagebox.showerror("Open Project", str(ex))
            return False
        for key, value in data.get("inputs", {}).items():
            if key in self.vars:
                self.vars[key].set(str(value))
        opts = data.get("options", {})
        self.auto_orient_var.set(bool(opts.get("auto_orient", True)))
        self.helix_var.set(bool(opts.get("helix", False)))
        self.c_dis_var.set(bool(opts.get("c_dis", True)))
        saved = data.get("output", "")
        self.clear()
        if saved.strip():
            regenerated = self.generate() and self.output_text.get("1.0", "end-1c") == saved
            if not regenerated:
                self.output_text.delete("1.0", tk.END)
                self.output_text.insert("1.0", saved)
                self.redraw()
                self.info.config(text="Output as saved in the project (not regenerated).")
                messagebox.showinfo("Open Project",
                                    "The saved output differs from what this version generates "
                                    "(hand edits, or a program change).\n\nThe SAVED output was kept. "
                                    "Press Generate to regenerate it from the inputs.")
        warning = project_files.profile_mismatch(data)
        if warning:
            messagebox.showwarning("Open Project", warning)
        return True

    # ------------------------------------------------------------------ top view
    def redraw(self):
        c = self.canvas
        c.delete("all")
        start, moves = pm.path_3d(pm.parse_krl(self.body_text()))
        pts = [q for m in moves for q in m['pts']] + ([start] if start else [])
        if not pts:
            return
        W, H = int(c.cget("width")), int(c.cget("height"))
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
        s = (min(W, H) - 40) / span
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2

        def scr(q):
            return W / 2 + (q[0] - cx) * s, H / 2 - (q[1] - cy) * s     # Y up

        for m in moves:
            coords = []
            for q in m['pts']:
                coords.extend(scr(q))
            c.create_line(*coords, fill=TRANSITION_COLOR if m['transition'] else PATH_COLOR,
                          width=2 if m['transition'] else 1)
        ox, oy = scr((cx, cy))
        c.create_line(ox - 6, oy, ox + 6, oy, fill="#999999")
        c.create_line(ox, oy - 6, ox, oy + 6, fill="#999999")
        for q, col in ((start, "#2ca02c"), (moves[-1]['pts'][-1] if moves else None, "#d62728")):
            if q:
                x, y = scr(q)
                c.create_oval(x - 4, y - 4, x + 4, y + 4, fill=col, outline="")
        c.create_text(8, H - 8, anchor="sw", fill="#777777", font=("Segoe UI", 8),
                      text="green = start, red = end, + = centre")

    # ------------------------------------------------------------------ navigation
    def go_back_to_selector(self):
        try:
            selector = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Main_Window_Program_Selector_.py")
            if os.path.exists(selector):
                subprocess.Popen([sys.executable, selector])
            else:
                messagebox.showwarning("Not Found", "Main_Window_Program_Selector_.py was not found.")
        except Exception as ex:
            messagebox.showerror("Error", "Failed to open selector: %s" % ex)
        finally:
            self.root.destroy()


def main():
    root = tk.Tk()
    CylinderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
