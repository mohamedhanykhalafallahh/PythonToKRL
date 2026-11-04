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
import os
import runpy
import sys
import tempfile
import tkinter as tk
from tkinter import messagebox, filedialog

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
APP = os.path.join(REPO, "PythonApplication6.py")
GOLDEN = os.path.join(HERE, "golden")

# name: base (Xr, Yr, Zr, L, W, tool height), automation (E, W, turns, layers),
#       tilt angle, auto-orient on/off, C_DIS on/off
CASES = {
    "REG_300x150":      dict(base=(535, 10, 65, 300, 150, 0), auto=(2, 2, 2, 1), tilt=20, orient=True,  cdis=True),
    "REG_150x300_5T":   dict(base=(535, 10, 65, 150, 300, 0), auto=(2, 2, 5, 2), tilt=20, orient=True,  cdis=True),
    "REG_20x20_E3":     dict(base=(500, 0, 50, 20, 20, 5),    auto=(3, 1, 3, 2), tilt=10, orient=True,  cdis=True),
    "REG_600x80_moved": dict(base=(450, -120, 30, 600, 80, 2), auto=(1, 1.5, 4, 1), tilt=15, orient=True, cdis=True),
    "REG_tilt_off":     dict(base=(535, 10, 65, 300, 150, 0), auto=(2, 2, 2, 1), tilt=20, orient=False, cdis=True),
    "REG_cdis_off":     dict(base=(535, 10, 65, 300, 150, 0), auto=(2, 2, 2, 1), tilt=20, orient=True,  cdis=False),
}


class AppError(Exception):
    pass


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
        for name, case in CASES.items():
            try:
                out = run_case(case, tmpdir, name)
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
                with open(path, newline="") as f:
                    expected = f.read()
                if expected == text:
                    print("ok     %s" % fname)
                else:
                    print("DIFF   %s: %s" % (fname, first_diff(expected, text)))
                    failed += 1
    print("\n%s" % ("ALL IDENTICAL" if not failed else "%d PROBLEM(S)" % failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
