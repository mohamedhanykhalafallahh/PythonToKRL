"""Figures for the user manual (screenshots of the real program + illustrations, EN and FR).

    python docs/manual/make_figures.py

Writes PNG files into docs/manual/figures/. Screenshots are taken from the screen (the windows
are shown briefly), so do not use the PC while it runs (about 1 minute). Uses a temporary theme
setting, never the user's own app_settings.json.
"""
import contextlib
import io
import json
import math
import os
import runpy
import subprocess
import sys
import tempfile
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "figures")
sys.path.insert(0, REPO)
os.makedirs(OUT, exist_ok=True)

from tkinter import messagebox  # noqa: E402
messagebox.showinfo = messagebox.showwarning = lambda *a, **k: None

import ui_theme  # noqa: E402
ui_theme.SETTINGS_PATH = os.path.join(tempfile.mkdtemp(), "app_settings.json")
import KRL_Generator  # noqa: E402
import ui_images  # noqa: E402
import view3d  # noqa: E402

SCALE = 1.25                      # Windows display scaling of this PC (logical px -> screen px)
LIGHT = ui_theme.THEMES["light"]


# ---------------------------------------------------------------------- capture helpers

def _ps(script):
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


def grab(win, name, frame=True, crop_widget=None, pad=6):
    """Screenshot a window (with title bar and menu if frame=True) or one widget of it."""
    win.update()
    if crop_widget is not None:
        x0, y0 = crop_widget.winfo_rootx() - pad, crop_widget.winfo_rooty() - pad
        x1, y1 = x0 + crop_widget.winfo_width() + 2 * pad, y0 + crop_widget.winfo_height() + 2 * pad
    elif frame:
        # title bar + menu, but not Windows' invisible resize border at the sides / bottom
        x0, y0 = win.winfo_rootx() - 1, win.winfo_y() + 1
        x1, y1 = win.winfo_rootx() + win.winfo_width() + 1, win.winfo_rooty() + win.winfo_height() + 1
    else:
        x0, y0 = win.winfo_rootx(), win.winfo_rooty()
        x1, y1 = x0 + win.winfo_width(), y0 + win.winfo_height()
    path = os.path.join(OUT, name)
    _ps("Add-Type -AssemblyName System.Drawing; $b = New-Object System.Drawing.Bitmap %d, %d; "
        "$g = [System.Drawing.Graphics]::FromImage($b); $g.CopyFromScreen(%d, %d, 0, 0, $b.Size); "
        "$b.Save('%s'); $g.Dispose(); $b.Dispose()" % (int((x1 - x0) * SCALE), int((y1 - y0) * SCALE),
                                                     int(x0 * SCALE), int(y0 * SCALE), path))
    print("  ", name)
    return (x0, y0)


def annotate(name, callouts):
    """Draw numbered callout badges onto a screenshot. callouts: [(n, x, y), ...] in screen px
    relative to the image."""
    path = os.path.join(OUT, name)
    lines = ["Add-Type -AssemblyName System.Drawing",
             "$src = [System.Drawing.Image]::FromFile('%s')" % path,
             "$b = New-Object System.Drawing.Bitmap $src", "$src.Dispose()",
             "$g = [System.Drawing.Graphics]::FromImage($b)",
             "$g.SmoothingMode = 'AntiAlias'", "$g.TextRenderingHint = 'AntiAliasGridFit'",
             "$fill = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 234, 88, 12))",
             "$pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::White), 3",
             "$font = New-Object System.Drawing.Font('Segoe UI', 15, [System.Drawing.FontStyle]::Bold)",
             "$white = [System.Drawing.Brushes]::White",
             "$fmt = New-Object System.Drawing.StringFormat",
             "$fmt.Alignment = 'Center'; $fmt.LineAlignment = 'Center'"]
    r = 17
    for n, x, y in callouts:
        lines.append("$g.FillEllipse($fill, %d, %d, %d, %d)" % (x - r, y - r, 2 * r, 2 * r))
        lines.append("$g.DrawEllipse($pen, %d, %d, %d, %d)" % (x - r, y - r, 2 * r, 2 * r))
        lines.append("$g.DrawString('%d', $font, $white, (New-Object System.Drawing.RectangleF(%d, %d, %d, %d)), $fmt)"
                     % (n, x - r, y - r + 1, 2 * r, 2 * r))
    lines += ["$g.Dispose()", "$b.Save('%s.tmp.png')" % path, "$b.Dispose()"]
    _ps("; ".join(lines))
    os.replace(path + ".tmp.png", path)


def rel(widget, win, origin, dx=0, dy=0, where="nw"):
    """Screen-px position of a widget corner, relative to a captured image whose top-left was origin."""
    x = widget.winfo_rootx() - origin[0]
    y = widget.winfo_rooty() - origin[1]
    if where == "ne":
        x += widget.winfo_width()
    elif where == "w":
        y += widget.winfo_height() / 2
    elif where == "e":
        x += widget.winfo_width()
        y += widget.winfo_height() / 2
    return int((x + dx) * SCALE), int((y + dy) * SCALE)


def find(widget, text):
    for c in widget.winfo_children():
        try:
            if str(c.cget("text")).strip() == text:
                return c
        except tk.TclError:
            pass
        r = find(c, text)
        if r is not None:
            return r
    return None


# ---------------------------------------------------------------------- screenshots

def screenshots():
    print("screenshots")
    root = tk.Tk()
    root.geometry("+0+0")
    root.attributes("-topmost", True)
    app = KRL_Generator.MainApp(root)
    steps = []

    def nxt():
        if steps:
            steps.pop(0)()
        else:
            root.destroy()

    def s_main():
        app.generate()
        app.output_text.see("1.0")
        root.update()
        origin = grab(root, "main_light.png")
        menu_y = (root.winfo_rooty() - origin[1]) - 12
        c = [(1, int(250 * SCALE), int(menu_y * SCALE)),
             rel(app.badge, root, origin, -8, 6) and (2,) + rel(app.badge, root, origin, -8, 10),
             (3,) + rel(app.seg_buttons["cuboid"].master.master, root, origin, 92, 14),
             (4,) + rel(app.shape_frame, root, origin, 260, 14),
             (5,) + rel(find(root, "Path").master, root, origin, 70, 14),
             (6,) + rel(find(root, "Orientation (deg)  &  options").master, root, origin, 250, 14),
             (7,) + rel(find(root, "Generate"), root, origin, 16, 18),
             (8,) + rel(find(root, "3D View"), root, origin, 16, 14),
             (9,) + rel(app.canvas.master, root, origin, 120, 14),
             (10,) + rel(app.chips, root, origin, -6, 12),
             (11,) + rel(app.output_text.master.master, root, origin, 230, 14)]
        annotate("main_light.png", [t for t in c if len(t) == 3])
        root.after(200, nxt)

    def s_topview():
        grab(root, "topview.png", crop_widget=app.canvas.master)
        grab(root, "program_box.png", crop_widget=app.output_text.master.master)
        grab(root, "chips.png", crop_widget=app.chips, pad=4)
        grab(root, "left_panel.png", crop_widget=app.seg_buttons["cuboid"].master.master.master)
        root.after(200, nxt)

    def s_3d():
        app.vars["layers"].set("6")
        app.generate()
        app.open_3d_view()
        v = view3d._open_views[root]
        v.win.geometry("900x600+20+20")
        v.win.attributes("-topmost", True)
        v.arrows_var.set(True)
        v.win.update()
        v.redraw()
        root.after(700, lambda: (grab(v.win, "view3d.png"), v.close(), root.after(200, nxt)))

    def s_dialogs():
        app.vars["layers"].set("3")
        app.generate()
        d = app.open_export_settings()
        d.win.geometry("+40+30")
        d.win.attributes("-topmost", True)

        def after_settings():
            grab(d.win, "export_settings.png")
            d.win.destroy()
            w = app.add_comment()
            w.geometry("+80+80")
            w.attributes("-topmost", True)
            entry = [c for c in w.winfo_children() if c.winfo_class() == "TEntry"][0]
            entry.insert(0, "Fiber spool changed, check tension")

            def after_comment():
                grab(w, "add_comment.png")
                w.destroy()
                a = app.add_approach()
                a.geometry("+80+80")
                a.attributes("-topmost", True)
                for k, v in zip("XYZ", ("587.5", "160", "120")):
                    a.vars[k].set(v)
                root.after(600, lambda: (grab(a, "add_approach.png"), a.destroy(), root.after(200, nxt)))
            root.after(600, after_comment)
        root.after(700, after_settings)

    def s_cylinder():
        app.set_shape("cylinder")
        app.vars["turns"].set("3")
        app.vars["layers"].set("3")
        app.generate()
        root.update()
        grab(root, "main_cylinder.png")
        grab(root, "size_cylinder.png", crop_widget=app.shape_frame)
        app.set_shape("cuboid")
        grab(root, "size_cuboid.png", crop_widget=app.shape_frame)
        root.after(200, nxt)

    def s_dark():
        app.generate()
        app.apply_theme("dark", save=False)
        root.after(700, lambda: (grab(root, "main_dark.png"), app.apply_theme("light", save=False),
                                 root.after(300, nxt)))

    steps.extend([s_main, s_topview, s_3d, s_dialogs, s_cylinder, s_dark])
    root.after(800, nxt)
    root.mainloop()

    # the manual 11-point editor (as opened from the Tools menu), with an automated example
    sys.argv = [os.path.join(REPO, "PythonApplication6.py"), "--from-main"]
    real_mainloop = tk.Tk.mainloop
    tk.Tk.mainloop = lambda self, n=0: None
    with contextlib.redirect_stdout(io.StringIO()):
        G = runpy.run_path(sys.argv[0])["automate"].__globals__
    tk.Tk.mainloop = real_mainloop
    r6 = G["root"]
    r6.geometry("+0+0")
    r6.attributes("-topmost", True)
    G["generate_popup_values"].update(L="150", W="300", Th="0")
    before = set(r6.winfo_children())
    G["open_generate_popup"]()
    pop = [w for w in r6.winfo_children() if w not in before][0]
    [w for w in pop.winfo_children() if w.winfo_class() == "Button"][0].invoke()
    for n, v in (("E_entry", 2), ("W_entry", 2), ("NumberofTurns_entry", 2), ("NumberofLayers_entry", 1)):
        G[n].insert(0, str(v))
    with contextlib.redirect_stdout(io.StringIO()):
        G["automate"]()
    r6.after(800, lambda: (grab(r6, "manual_editor.png"), r6.destroy()))
    real_mainloop(r6)


# ---------------------------------------------------------------------- illustrations

TEXT = {
    "en": dict(
        wf=["Choose the\nshape", "Enter sizes,\npath, orientation", "Generate", "Check:\ntop view & 3D",
            "Export the\n.src file", "Run on the robot\n(dry run first)"],
        not_scale="Sizes not to scale", centre="Centre X / Y", length="Length X", width="Width Y",
        radius="Corner radius", start="Start", direction="Travel direction", turn1="Turn 1 (first, inner turn)",
        turn3="Turn 3 (outer)", e="Turn step E", seam="Turn and layer changes\nhappen here",
        inner_d="Inner diameter", ring1="Ring 1 (first, inner)", ring3="Ring 3 (outer)",
        seam_cyl="Seam quarter: lane change\nto the next ring / layer climb",
        inside="Inside of the part", outside="Outside", layer_h="Layer height",
        wall="Wall thickness = turns × E", lay_out="outward", lay_in="inward",
        layer="Layer", turn="Turn", roller="Roller", lamp="UV lamp (trails)",
        a_dir="A = travel direction", path_lbl="Path"),
    "fr": dict(
        wf=["Choisir la\nforme", "Saisir dimensions,\ntrajet, orientation", "Générer",
            "Vérifier :\nvue de dessus & 3D", "Exporter le\nfichier .src", "Exécuter sur le robot\n(d'abord à vide)"],
        not_scale="Dimensions non à l'échelle", centre="Centre X / Y", length="Longueur X",
        width="Largeur Y", radius="Rayon d'angle", start="Départ", direction="Sens de parcours",
        turn1="Tour 1 (premier, intérieur)", turn3="Tour 3 (extérieur)", e="Pas entre tours E",
        seam="Les changements de tour\net de couche se font ici", inner_d="Diamètre intérieur",
        ring1="Anneau 1 (premier, intérieur)", ring3="Anneau 3 (extérieur)",
        seam_cyl="Quart de jonction : changement\nd'anneau / montée de couche",
        inside="Intérieur de la pièce", outside="Extérieur", layer_h="Hauteur de couche",
        wall="Épaisseur de paroi = tours × E", lay_out="vers l'extérieur", lay_in="vers l'intérieur",
        layer="Couche", turn="Tour", roller="Rouleau", lamp="Lampe UV (suit)",
        a_dir="A = direction de déplacement", path_lbl="Trajet"),
}
INK, MUTED, ACCENT, PURPLE, GREEN = "#1f2933", "#6b7785", "#2563eb", "#9333ea", "#16a34a"
RING_COLS = ["#93c5fd", "#3b82f6", "#1e40af"]
F = "Segoe UI"


def arrow(c, x0, y0, x1, y1, col=INK, w=2, both=False):
    c.create_line(x0, y0, x1, y1, fill=col, width=w, arrow=tk.BOTH if both else tk.LAST, arrowshape=(11, 13, 4))


def rrect(c, x0, y0, x1, y1, r, **kw):
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(10):
            a = math.radians(a0 + 9 * k)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return c.create_polygon(*pts, smooth=False, **kw)


def diagram_workflow(c, T):
    W, H = 1180, 210
    c.config(width=W, height=H)
    n = len(T["wf"])
    bw, gap = 160, 32
    x = (W - (n * bw + (n - 1) * gap)) / 2
    for i, t in enumerate(T["wf"]):
        col = ACCENT if i in (2, 4) else "#e8eefc"
        fg = "#ffffff" if i in (2, 4) else INK
        rrect(c, x, 40, x + bw, 190, 16, fill=col, outline="#c9d6f2" if col != ACCENT else ACCENT, width=2)
        c.create_oval(x + bw / 2 - 18, 22, x + bw / 2 + 18, 58, fill="#ea580c", outline="#ffffff", width=3)
        c.create_text(x + bw / 2, 40, text=str(i + 1), fill="#ffffff", font=(F, 13, "bold"))
        c.create_text(x + bw / 2, 125, text=t, fill=fg, font=(F, 12, "bold" if i in (2, 4) else "normal"),
                      justify="center", width=bw - 16)
        if i < n - 1:
            arrow(c, x + bw + 4, 115, x + bw + gap - 4, 115, col=MUTED, w=3)
        x += bw + gap


def diagram_cuboid(c, T):
    W, H = 1080, 680
    c.config(width=W, height=H)
    cx, cy, hw, hh, r, e = 430, 320, 120, 215, 52, 22
    for i, col in enumerate(RING_COLS):
        d = i * e
        rrect(c, cx - hw - d, cy - hh - d, cx + hw + d, cy + hh + d, r + d, fill="", outline=col, width=5)
    # seam (transitions) at the top-right corner
    c.create_arc(cx + hw - r - 2 * e - 6, cy - hh - 2 * e - 6, cx + hw + 2 * e + 6, cy - hh + 2 * r + 6,
                 start=0, extent=90, style=tk.ARC, outline=PURPLE, width=8)
    c.create_text(cx + hw + 72, cy - hh - 30, text=T["seam"], anchor="w", fill=PURPLE, font=(F, 12, "bold"),
                  justify="left")
    arrow(c, cx + hw + 66, cy - hh - 24, cx + hw + 38, cy - hh + 4, col=PURPLE, w=2)
    # centre
    c.create_line(cx - 14, cy, cx + 14, cy, fill=INK, width=2)
    c.create_line(cx, cy - 14, cx, cy + 14, fill=INK, width=2)
    c.create_text(cx + 20, cy + 20, text=T["centre"], anchor="nw", fill=INK, font=(F, 12))
    # length / width of turn 1
    arrow(c, cx - hw, cy + hh + 85, cx + hw, cy + hh + 85, both=True)
    c.create_line(cx - hw, cy + hh + 8, cx - hw, cy + hh + 95, fill=MUTED, dash=(3, 3))
    c.create_line(cx + hw, cy + hh + 8, cx + hw, cy + hh + 95, fill=MUTED, dash=(3, 3))
    c.create_text(cx, cy + hh + 108, text=T["length"], fill=INK, font=(F, 12, "bold"))
    arrow(c, cx - hw - 95, cy - hh, cx - hw - 95, cy + hh, both=True)
    c.create_line(cx - hw - 8, cy - hh, cx - hw - 105, cy - hh, fill=MUTED, dash=(3, 3))
    c.create_line(cx - hw - 8, cy + hh, cx - hw - 105, cy + hh, fill=MUTED, dash=(3, 3))
    c.create_text(cx - hw - 112, cy, text=T["width"], angle=90, fill=INK, font=(F, 12, "bold"))
    # corner radius (bottom-left of turn 1)
    rcx, rcy = cx + hw - r, cy + hh - r                     # bottom-right corner of turn 1
    c.create_oval(rcx - 4, rcy - 4, rcx + 4, rcy + 4, fill=INK, outline="")
    a = math.radians(45)
    arrow(c, rcx, rcy, rcx + r * math.cos(a), rcy + r * math.sin(a), col=INK)
    c.create_text(rcx - 14, rcy - 16, text=T["radius"], anchor="e", fill=INK, font=(F, 12))
    # turn step E (right side)
    for i in range(2):
        y = cy + 80
        arrow(c, cx + hw + i * e, y, cx + hw + (i + 1) * e, y, both=True, w=2)
    c.create_text(cx + hw + 2 * e + 12, cy + 80, text=T["e"], anchor="w", fill=INK, font=(F, 12, "bold"))
    # turn labels
    c.create_text(cx, cy + hh - 130, text=T["turn1"], fill=RING_COLS[1], font=(F, 11, "bold"))
    c.create_text(cx - hw - 2 * e - 12, cy - hh - 2 * e + 10, text=T["turn3"], anchor="e", fill=RING_COLS[2],
                  font=(F, 11, "bold"))
    # start point + direction on turn 1 (top edge near the top-right corner, travelling -X)
    sx, sy = cx + hw - r, cy - hh
    c.create_oval(sx - 9, sy - 9, sx + 9, sy + 9, fill=GREEN, outline="#ffffff", width=3)
    c.create_text(sx + 4, sy + 26, text=T["start"], fill=GREEN, font=(F, 12, "bold"))
    arrow(c, sx - 30, sy + 52, sx - 150, sy + 52, col=GREEN, w=3)
    c.create_text(sx - 90, sy + 72, text=T["direction"], fill=GREEN, font=(F, 11))
    # axes + note
    ox, oy = 70, H - 60
    arrow(c, ox, oy, ox + 70, oy, col="#d62728", w=3)
    arrow(c, ox, oy, ox, oy - 70, col="#2ca02c", w=3)
    c.create_text(ox + 80, oy, text="X", fill="#d62728", font=(F, 13, "bold"), anchor="w")
    c.create_text(ox, oy - 82, text="Y", fill="#2ca02c", font=(F, 13, "bold"))
    c.create_text(W - 20, H - 20, text=T["not_scale"], anchor="se", fill=MUTED, font=(F, 10, "italic"))


def diagram_cylinder(c, T):
    W, H = 1080, 600
    c.config(width=W, height=H)
    cx, cy, r0, e = 430, 300, 170, 26
    for i, col in enumerate(RING_COLS):
        R = r0 + i * e
        c.create_oval(cx - R, cy - R, cx + R, cy + R, outline=col, width=5)
    # seam quarter (270 -> 360 deg, lower right), drawn over the rings
    R1, R2 = r0 - 10, r0 + 2 * e + 10
    c.create_arc(cx - R2, cy - R2, cx + R2, cy + R2, start=270, extent=90, style=tk.ARC, outline=PURPLE, width=9)
    c.create_text(cx + r0 + 2 * e + 40, cy + r0 + 10, text=T["seam_cyl"], anchor="w", fill=PURPLE,
                  font=(F, 12, "bold"))
    # inner diameter
    arrow(c, cx - r0, cy, cx + r0, cy, both=True)
    c.create_text(cx, cy - 18, text=T["inner_d"], fill=INK, font=(F, 12, "bold"))
    c.create_line(cx - 10, cy, cx + 10, cy, fill=INK)
    c.create_text(cx, cy + 24, text=T["centre"], fill=MUTED, font=(F, 11))
    # E between rings (top)
    for i in range(2):
        arrow(c, cx, cy - r0 - i * e, cx, cy - r0 - (i + 1) * e, both=True, w=2)
    c.create_text(cx + 16, cy - r0 - 2 * e - 16, text=T["e"], anchor="w", fill=INK, font=(F, 12, "bold"))
    # start at +X on ring 1 + direction (counter-clockwise: up)
    sx, sy = cx + r0, cy
    c.create_oval(sx - 9, sy - 9, sx + 9, sy + 9, fill=GREEN, outline="#ffffff", width=3)
    c.create_text(sx - 16, sy + 22, text=T["start"], fill=GREEN, font=(F, 12, "bold"), anchor="e")
    c.create_arc(cx - r0 + 30, cy - r0 + 30, cx + r0 - 30, cy + r0 - 30, start=5, extent=55, style=tk.ARC,
                 outline=GREEN, width=3)
    a = math.radians(60)
    tipx, tipy = cx + (r0 - 30) * math.cos(a), cy - (r0 - 30) * math.sin(a)
    arrow(c, tipx + 8, tipy + 6, tipx - 4, tipy - 4, col=GREEN, w=3)
    c.create_text(cx + 20, cy - 70, text=T["direction"], fill=GREEN, font=(F, 11), anchor="w")
    c.create_text(cx - r0 - 2 * e - 10, cy - r0 - 2 * e, text=T["ring3"], anchor="e", fill=RING_COLS[2],
                  font=(F, 11, "bold"))
    c.create_text(cx - r0 + 60, cy + r0 - 70, text=T["ring1"], anchor="w", fill=RING_COLS[1], font=(F, 11, "bold"))
    ox, oy = 70, H - 60
    arrow(c, ox, oy, ox + 70, oy, col="#d62728", w=3)
    arrow(c, ox, oy, ox, oy - 70, col="#2ca02c", w=3)
    c.create_text(ox + 80, oy, text="X", fill="#d62728", font=(F, 13, "bold"), anchor="w")
    c.create_text(ox, oy - 82, text="Y", fill="#2ca02c", font=(F, 13, "bold"))
    c.create_text(W - 20, H - 20, text=T["not_scale"], anchor="se", fill=MUTED, font=(F, 10, "italic"))


def diagram_layers(c, T):
    W, H = 1080, 470
    c.config(width=W, height=H)
    turns, layers = 3, 3
    cols = ui_images.layer_colors(layers, LIGHT["ramp"])
    x0, y0, fw, fh, gx, gy = 330, 290, 110, 46, 28, 36
    c.create_line(x0 - 70, y0 + fh + 8, x0 + turns * (fw + gx) + 40, y0 + fh + 8, fill=MUTED, width=3)
    for l in range(layers):
        y = y0 - l * (fh + gy)
        for t in range(turns):
            x = x0 + t * (fw + gx)
            rrect(c, x, y, x + fw, y + fh, 14, fill=cols[l], outline="#ffffff", width=2)
            c.create_text(x + fw / 2, y + fh / 2, text="%s %d" % (T["turn"], t + 1), fill=INK, font=(F, 11, "bold"))
        out = l % 2 == 0
        ya = y + fh / 2
        xa0, xa1 = x0 - 40, x0 + turns * (fw + gx) + 10
        if out:
            arrow(c, xa1 - 10, ya - 0.1, xa1 + 30, ya, col=ACCENT, w=3)
        else:
            arrow(c, x0 - 20, ya, x0 - 60, ya, col=ACCENT, w=3)
        c.create_text(x0 - 80 if out else x0 - 80, ya, text="%s %d: %s" % (T["layer"], l + 1,
                      T["lay_out"] if out else T["lay_in"]), anchor="e", fill=ACCENT, font=(F, 12, "bold"))
    # layer height
    xr = x0 + turns * (fw + gx) + 60
    arrow(c, xr, y0 + fh / 2, xr, y0 - (fh + gy) + fh / 2, both=True)
    c.create_text(xr + 12, y0 - (fh + gy) / 2 + fh / 2, text=T["layer_h"], anchor="w", fill=INK, font=(F, 12, "bold"))
    # E (between turn 1 and 2 centres) and wall thickness
    yb = y0 + fh + 45
    arrow(c, x0 + fw / 2, yb, x0 + fw + gx + fw / 2, yb, both=True)
    c.create_text(x0 + fw + gx / 2, yb + 18, text="E", fill=INK, font=(F, 12, "bold"))
    yw = yb + 55
    arrow(c, x0, yw, x0 + turns * (fw + gx) - gx, yw, both=True)
    c.create_text(x0 + (turns * (fw + gx) - gx) / 2, yw + 20, text=T["wall"], fill=INK, font=(F, 12, "bold"))
    c.create_text(x0 - 10, y0 - 3 * (fh + gy) + 30, text="← " + T["inside"], anchor="e", fill=MUTED, font=(F, 11))
    c.create_text(x0 + turns * (fw + gx) + 10, y0 - 3 * (fh + gy) + 30, text=T["outside"] + " →", anchor="w",
                  fill=MUTED, font=(F, 11))


def diagram_head(c, T):
    W, H = 1080, 420
    c.config(width=W, height=H)
    # path: straight then a rounded corner
    c.create_line(120, 300, 620, 300, fill=RING_COLS[1], width=8, capstyle=tk.ROUND)
    c.create_arc(520, 100, 720, 300, start=270, extent=90, style=tk.ARC, outline=RING_COLS[1], width=8)
    c.create_line(720, 200, 720, 60, fill=RING_COLS[1], width=8, capstyle=tk.ROUND)
    c.create_text(140, 330, text=T["path_lbl"], anchor="w", fill=MUTED, font=(F, 11))
    # head on the straight part (travelling +X): roller in front, lamp behind
    hx, hy = 380, 300
    rrect(c, hx - 95, hy - 34, hx + 45, hy + 34, 14, fill="#e8eefc", outline=ACCENT, width=2)
    c.create_oval(hx + 10, hy - 22, hx + 54, hy + 22, fill="#334155", outline="#ffffff", width=2)
    rrect(c, hx - 88, hy - 18, hx - 40, hy + 18, 8, fill="#facc15", outline="#a16207", width=2)
    c.create_text(hx + 32, hy - 52, text=T["roller"], fill=INK, font=(F, 11, "bold"))
    c.create_text(hx - 64, hy + 58, text=T["lamp"], fill="#a16207", font=(F, 11, "bold"))
    arrow(c, hx + 60, hy, hx + 170, hy, col="#ea580c", w=4)
    c.create_text(hx + 115, hy - 20, text="A", fill="#ea580c", font=(F, 14, "bold"))
    # head in the corner (rotated 45 deg): just an arrow showing A turning with the path
    a = math.radians(45)
    px, py = 620 + 100 * math.cos(math.radians(315)) * 0 + 670, 0
    ccx, ccy, rr = 620, 200, 100
    qx, qy = ccx + rr * math.cos(math.radians(-45)), ccy - rr * math.sin(math.radians(-45))
    arrow(c, qx, qy, qx + 80 * math.cos(a), qy - 80 * math.sin(a), col="#ea580c", w=4)
    arrow(c, 720, 150, 720, 70, col="#ea580c", w=4)
    c.create_text(800, 230, text=T["a_dir"], anchor="w", fill="#ea580c", font=(F, 13, "bold"))


def illustrations():
    print("illustrations")
    for lang, T in TEXT.items():
        for name, fn in (("diagram_workflow", diagram_workflow), ("diagram_cuboid", diagram_cuboid),
                         ("diagram_cylinder", diagram_cylinder), ("diagram_layers", diagram_layers),
                         ("diagram_head", diagram_head)):
            root = tk.Tk()
            root.overrideredirect(True)
            root.geometry("+0+0")
            root.attributes("-topmost", True)
            c = tk.Canvas(root, bg="#ffffff", highlightthickness=0)
            c.pack()
            fn(c, T)
            root.update()
            root.after(300, lambda r=root, n="%s_%s.png" % (name, lang): (grab(r, n, frame=False), r.destroy()))
            root.mainloop()


def icon():
    ui_images.export_icon_files(os.path.join(OUT, "icon"), png_sizes=(256,))


if __name__ == "__main__":
    which = sys.argv[1:] or ["screenshots", "illustrations", "icon"]
    if "screenshots" in which:
        screenshots()
    if "illustrations" in which:
        illustrations()
    if "icon" in which:
        icon()
    print("done ->", OUT)
