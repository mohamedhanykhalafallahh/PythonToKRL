"""Export Settings dialog (tkinter), shared by the generator apps.

Edits the export profiles in export_profiles.json (see krl_export): TOOL / BASE data,
approximation, velocities, accelerations, coordinate decimals and the header comments.
The ACTIVE profile is used by every export, in every app.

    open_dialog(parent)
"""
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import krl_export

FRAME_KEYS = ("X", "Y", "Z", "A", "B", "C")
# (attribute, label, hint)
MOTION_FIELDS = [
    ("cdis", "$APO.CDIS (mm)", "blending distance used by C_DIS"),
    ("cptp", "$APO.CPTP (%)", "PTP blending"),
    ("vel_ptp", "VEL_PTP (%)", "PTP speed"),
    ("vel_cp", "VEL_CP (m/s)", "path speed in m/s! 2 = 2 m/s; the real speed currently comes from the override"),
    ("acc_cp", "ACC_CP (%)", "path acceleration"),
    ("acc_axis", "ACC_AXIS (%)", "axis acceleration, all 6 axes"),
]


def _number(text, what):
    """'50' -> 50 (int), '5.0' / '0.01' -> float. Raises ValueError with a readable message."""
    t = text.strip()
    try:
        v = float(t)
    except ValueError:
        raise ValueError("%s: '%s' is not a number" % (what, text))
    return int(v) if v.is_integer() and "." not in t and "e" not in t.lower() else v


def _show(v):
    return "" if v is None else str(v)


class ExportSettingsDialog:
    def __init__(self, parent, path=None, on_saved=None):
        self.path = path
        self.on_saved = on_saved
        self.active, self.profiles, error = krl_export.load_profiles(path)
        self.win = tk.Toplevel(parent)
        self.win.title("Export Settings (profiles)")
        self.win.transient(parent)
        self.vars = {}
        self._build()
        self._load(self.active)
        if error:
            messagebox.showwarning("Export Settings", error + "\n\nSaving will replace the file.", parent=self.win)

    # ------------------------------------------------------------------ UI
    def _entry(self, parent, key, width=9):
        var = tk.StringVar()
        tk.Entry(parent, textvariable=var, width=width).pack(side=tk.LEFT, padx=2)
        self.vars[key] = var
        return var

    def _build(self):
        w = self.win
        top = tk.Frame(w)
        top.pack(fill=tk.X, padx=10, pady=(10, 4))
        tk.Label(top, text="Profile:").pack(side=tk.LEFT)
        self.profile_var = tk.StringVar()
        self.combo = ttk.Combobox(top, textvariable=self.profile_var, state="readonly", width=24)
        self.combo.pack(side=tk.LEFT, padx=6)
        self.combo.bind("<<ComboboxSelected>>", lambda e: self._load(self.profile_var.get()))
        self.active_label = tk.Label(top, text="", fg="#2a7a2a")
        self.active_label.pack(side=tk.LEFT, padx=6)

        for kind in ("tool", "base"):
            box = ttk.LabelFrame(w, text="TOOL" if kind == "tool" else "BASE")
            box.pack(fill=tk.X, padx=10, pady=4)
            row = tk.Frame(box)
            row.pack(fill=tk.X, padx=4, pady=4)
            tk.Label(row, text="Number").pack(side=tk.LEFT)
            self._entry(row, kind + "_no", width=4)
            for k in FRAME_KEYS:
                tk.Label(row, text="  " + k).pack(side=tk.LEFT)
                self._entry(row, "%s_%s" % (kind, k))

        motion = ttk.LabelFrame(w, text="Motion")
        motion.pack(fill=tk.X, padx=10, pady=4)
        for r, (key, label, hint) in enumerate(MOTION_FIELDS):
            tk.Label(motion, text=label).grid(row=r, column=0, sticky="w", padx=4, pady=1)
            var = tk.StringVar()
            tk.Entry(motion, textvariable=var, width=9).grid(row=r, column=1, padx=4, pady=1)
            tk.Label(motion, text=hint, fg="#777777").grid(row=r, column=2, sticky="w", padx=4)
            self.vars[key] = var

        out = ttk.LabelFrame(w, text="Output")
        out.pack(fill=tk.X, padx=10, pady=4)
        row = tk.Frame(out)
        row.pack(fill=tk.X, padx=4, pady=4)
        tk.Label(row, text="Coordinate decimals").pack(side=tk.LEFT)
        self._entry(row, "decimals", width=4)
        tk.Label(row, text="0..6, empty = full precision (applied to the moves when exporting)",
                 fg="#777777").pack(side=tk.LEFT, padx=6)

        notes = ttk.LabelFrame(w, text="Header comments")
        notes.pack(fill=tk.X, padx=10, pady=4)
        tk.Label(notes, text="Base comment:").grid(row=0, column=0, sticky="nw", padx=4, pady=2)
        self.vars["base_comment"] = tk.StringVar()
        tk.Entry(notes, textvariable=self.vars["base_comment"], width=80).grid(row=0, column=1, padx=4, pady=2)
        tk.Label(notes, text="Tool comments\n(one per line):").grid(row=1, column=0, sticky="nw", padx=4, pady=2)
        self.tool_comments = tk.Text(notes, width=80, height=3)
        self.tool_comments.grid(row=1, column=1, padx=4, pady=2)

        buttons = tk.Frame(w)
        buttons.pack(fill=tk.X, padx=10, pady=10)
        tk.Button(buttons, text="Save (use for export)", command=self.save, width=20).pack(side=tk.LEFT, padx=3)
        tk.Button(buttons, text="Save as New...", command=self.save_as_new, width=14).pack(side=tk.LEFT, padx=3)
        tk.Button(buttons, text="Delete", command=self.delete, width=10).pack(side=tk.LEFT, padx=3)
        tk.Button(buttons, text="Close", command=self.win.destroy, width=10).pack(side=tk.RIGHT, padx=3)

    # ------------------------------------------------------------------ data <-> fields
    def _refresh_names(self, selected):
        self.combo["values"] = sorted(self.profiles)
        self.profile_var.set(selected)
        self.active_label.config(text="(active: used for export)" if selected == self.active
                                 else "(not active: Save to use it)")

    def _load(self, name):
        s = self.profiles[name]
        for kind in ("tool", "base"):
            self.vars[kind + "_no"].set(_show(getattr(s, kind + "_no")))
            for k, v in zip(FRAME_KEYS, getattr(s, kind)):
                self.vars["%s_%s" % (kind, k)].set(_show(v))
        for key, _, _ in MOTION_FIELDS:
            self.vars[key].set(_show(getattr(s, key)))
        self.vars["decimals"].set(_show(s.decimals))
        self.vars["base_comment"].set(s.base_comment)
        self.tool_comments.delete("1.0", tk.END)
        self.tool_comments.insert("1.0", "\n".join(s.tool_comments))
        self._refresh_names(name)

    def read_fields(self, name):
        """ExportSettings from the fields (raises ValueError with a readable message)."""
        d = {"profile": name}
        for kind in ("tool", "base"):
            no = _number(self.vars[kind + "_no"].get(), kind.upper() + " number")
            if not isinstance(no, int):
                raise ValueError("%s number must be a whole number" % kind.upper())
            d[kind + "_no"] = no
            d[kind] = tuple(float(_number(self.vars["%s_%s" % (kind, k)].get(), "%s %s" % (kind.upper(), k)))
                            for k in FRAME_KEYS)
        for key, label, _ in MOTION_FIELDS:
            d[key] = _number(self.vars[key].get(), label)
        dec = self.vars["decimals"].get().strip()
        if dec:
            dec = _number(dec, "Coordinate decimals")
            if not isinstance(dec, int):
                raise ValueError("Coordinate decimals must be a whole number")
        d["decimals"] = dec if dec != "" else None
        d["base_comment"] = self.vars["base_comment"].get().strip()
        d["tool_comments"] = [ln.strip() for ln in self.tool_comments.get("1.0", tk.END).split("\n") if ln.strip()]
        return krl_export.settings_from_dict(d)

    # ------------------------------------------------------------------ actions
    def _store(self, name):
        try:
            s = self.read_fields(name)
        except ValueError as ex:
            messagebox.showerror("Export Settings", str(ex), parent=self.win)
            return False
        self.profiles[name] = s
        self.active = name
        try:
            krl_export.save_profiles(self.active, self.profiles, self.path)
        except OSError as ex:
            messagebox.showerror("Export Settings", "Could not save the profiles:\n%s" % ex, parent=self.win)
            return False
        self._refresh_names(name)
        if self.on_saved:
            self.on_saved(s)
        return True

    def save(self):
        if self._store(self.profile_var.get()):
            messagebox.showinfo("Export Settings", "Profile '%s' saved. It is used for every export."
                                % self.profile_var.get(), parent=self.win)

    def save_as_new(self):
        name = simpledialog.askstring("Save as New", "Name of the new profile (e.g. the head):", parent=self.win)
        if name is None:
            return
        name = " ".join(name.split())
        if not name:
            messagebox.showerror("Export Settings", "The name must not be empty.", parent=self.win)
            return
        if name in self.profiles:
            messagebox.showerror("Export Settings", "A profile '%s' already exists." % name, parent=self.win)
            return
        if self._store(name):
            messagebox.showinfo("Export Settings", "Profile '%s' created and used for export." % name, parent=self.win)

    def delete(self):
        name = self.profile_var.get()
        if len(self.profiles) <= 1:
            messagebox.showerror("Export Settings", "The last profile cannot be deleted.", parent=self.win)
            return
        if not messagebox.askyesno("Delete Profile", "Delete profile '%s'?" % name, parent=self.win):
            return
        del self.profiles[name]
        if self.active == name:
            self.active = sorted(self.profiles)[0]
        try:
            krl_export.save_profiles(self.active, self.profiles, self.path)
        except OSError as ex:
            messagebox.showerror("Export Settings", "Could not save the profiles:\n%s" % ex, parent=self.win)
            return
        self._load(self.active)


def open_dialog(parent, path=None, on_saved=None):
    return ExportSettingsDialog(parent, path, on_saved)
