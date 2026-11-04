"""3D view window shared by the generator apps (tkinter only, no extra libraries).

Shows the path exactly as written in the KRL text (what goes to the robot): all layers
stacked in Z, CIRCs as real 3D arcs, transitions in purple, layers coloured.
Left-drag rotates, right/middle-drag moves, wheel zooms, double-click resets.

    open_view(parent, get_text, empty_message)   open (or reload + raise) the window
"""
import math
import tkinter as tk
from tkinter import messagebox

import path_model as pm

LAYER_COLORS_3D = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#8c564b",
                   "#e377c2", "#17becf", "#bcbd22", "#7f7f7f", "#393b79"]
TRANSITION_COLOR_3D = "purple"
ARROW_OK, ARROW_WARN, ARROW_BAD = "#2ca02c", "#ff7f0e", "#d62728"   # A vs travel: <= 5, <= 20, > 20 deg
ARROW_PX = 16                                                       # arrow length on screen

# KRL text -> 3D moves: path_model.parse_krl + path_model.path_3d (shared with other tools)

def _nice_length(x):
    """Round number (1, 2 or 5 x 10^k) close to x, for the axis length."""
    if x <= 0:
        return 1.0
    k = 10 ** math.floor(math.log10(x))
    for m in (1, 2, 5, 10):
        if m * k >= x:
            return m * k
    return 10 * k

class View3D:
    DEFAULT_YAW, DEFAULT_PITCH = math.radians(-35), math.radians(35)

    def __init__(self, parent, get_text, on_close=None, title="3D View"):
        """parent: Tk window; get_text(): returns the KRL text to show;
        on_close(): called when the window is closed."""
        self.get_text = get_text
        self.on_close = on_close
        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.geometry("780x620")
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        bar = tk.Frame(self.win)
        bar.pack(side=tk.TOP, fill=tk.X, padx=6, pady=4)
        tk.Label(bar, text="Z exaggeration:").pack(side=tk.LEFT)
        self.zex_var = tk.IntVar(value=1)
        tk.Scale(bar, from_=1, to=40, orient=tk.HORIZONTAL, length=160, variable=self.zex_var,
                 showvalue=True, command=lambda _v: self.redraw()).pack(side=tk.LEFT, padx=(0, 10))
        self.by_layer_var = tk.BooleanVar(value=True)
        tk.Checkbutton(bar, text="Colour by layer", variable=self.by_layer_var,
                       command=self.redraw).pack(side=tk.LEFT, padx=(0, 10))
        self.arrows_var = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="Head direction (A)", variable=self.arrows_var,
                       command=self.redraw).pack(side=tk.LEFT, padx=(0, 10))
        for txt, yaw, pitch in (("Iso", self.DEFAULT_YAW, self.DEFAULT_PITCH), ("Top", 0.0, math.radians(90)),
                                ("Front", 0.0, 0.0), ("Side", math.radians(-90), 0.0)):
            tk.Button(bar, text=txt, width=5,
                      command=lambda y=yaw, p=pitch: self.set_view(y, p)).pack(side=tk.LEFT, padx=1)
        tk.Button(bar, text="Reload", command=self.reload).pack(side=tk.RIGHT)

        self.canvas = tk.Canvas(self.win, bg="white", highlightthickness=0)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.info = tk.Label(self.win, anchor="w", justify=tk.LEFT, fg="#555555", font=("Segoe UI", 8))
        self.info.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=2)

        c = self.canvas
        c.bind("<Configure>", lambda e: self.redraw())
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._rotate)
        for b in ("2", "3"):
            c.bind(f"<ButtonPress-{b}>", self._press)
            c.bind(f"<B{b}-Motion>", self._move)
        c.bind("<MouseWheel>", self._wheel)
        c.bind("<Double-Button-1>", lambda e: self.reset_view())

        self.reset_view(redraw=False)
        self.reload()

    # ---------- data ----------
    def reload(self):
        items = pm.parse_krl(self.get_text())
        self.start, self.moves = pm.path_3d(items)
        self.headings = pm.heading_checks(items)
        pts = [p for m in self.moves for p in m['pts']] + ([self.start] if self.start else [])
        self.pts_all = pts
        if not pts:
            self.redraw()
            return
        xs, ys, zs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
        self.bounds = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
        self.center = ((self.bounds[0] + self.bounds[1]) / 2, (self.bounds[2] + self.bounds[3]) / 2,
                       (self.bounds[4] + self.bounds[5]) / 2)
        extent = max(self.bounds[1] - self.bounds[0], self.bounds[3] - self.bounds[2], 1e-6)
        height = self.bounds[5] - self.bounds[4]
        # Default: make the layer stack about 15% of the shape size so layers are visible
        zex = 1 if height < 1e-6 else int(round(max(1.0, min(40.0, 0.15 * extent / height))))
        self.zex_var.set(zex)
        self.redraw()

    # ---------- view ----------
    def reset_view(self, redraw=True):
        self.yaw, self.pitch = self.DEFAULT_YAW, self.DEFAULT_PITCH
        self.zoom, self.pan = 1.0, (0.0, 0.0)
        if redraw:
            self.redraw()

    def set_view(self, yaw, pitch):
        self.yaw, self.pitch = yaw, pitch
        self.zoom, self.pan = 1.0, (0.0, 0.0)
        self.redraw()

    def _project(self, p, zex, cy_, sy_, cp_, sp_):
        x = p[0] - self.center[0]
        y = p[1] - self.center[1]
        z = (p[2] - self.center[2]) * zex
        x1 = x * cy_ - y * sy_
        y1 = x * sy_ + y * cy_
        return x1, y1 * sp_ + z * cp_          # screen x, screen y (up)

    def redraw(self):
        c = self.canvas
        c.delete("all")
        W, H = max(c.winfo_width(), 10), max(c.winfo_height(), 10)
        if not getattr(self, "pts_all", None):
            c.create_text(W / 2, H / 2, text="Nothing to show yet: generate a path first, then press Reload.",
                          fill="#777777")
            self.info.config(text="")
            return
        zex = max(1, int(self.zex_var.get()))
        cy_, sy_ = math.cos(self.yaw), math.sin(self.yaw)
        cp_, sp_ = math.cos(self.pitch), math.sin(self.pitch)
        # scale from the bounding sphere so rotating never pushes the shape out of view
        rad = max(math.sqrt((p[0] - self.center[0]) ** 2 + (p[1] - self.center[1]) ** 2 +
                            ((p[2] - self.center[2]) * zex) ** 2) for p in self.pts_all) or 1.0
        s = 0.45 * min(W, H) / rad * self.zoom
        ox, oy = W / 2 + self.pan[0], H / 2 + self.pan[1]
        def scr(p):
            u, v = self._project(p, zex, cy_, sy_, cp_, sp_)
            return ox + s * u, oy - s * v

        # Axis cross at the lowest corner of the path
        b = self.bounds
        L = _nice_length(0.2 * max(b[1] - b[0], b[3] - b[2], 1e-6))
        o = (b[0], b[2], b[4])
        o_s = scr(o)
        for d, col, name in (((L, 0, 0), "#d62728", "X"), ((0, L, 0), "#2ca02c", "Y"),
                             ((0, 0, L / zex), "#1f77b4", "Z")):
            e_s = scr((o[0] + d[0], o[1] + d[1], o[2] + d[2]))
            c.create_line(*o_s, *e_s, fill=col, width=2, arrow=tk.LAST)
            c.create_text(e_s[0] + 8, e_s[1] - 8, text=name, fill=col, font=("Segoe UI", 9, "bold"))

        # Path
        by_layer = self.by_layer_var.get()
        for m in self.moves:
            if m['transition']:
                col = TRANSITION_COLOR_3D
            elif by_layer:
                col = LAYER_COLORS_3D[m['layer'] % len(LAYER_COLORS_3D)]
            else:
                col = "blue"
            coords = []
            for p in m['pts']:
                coords.extend(scr(p))
            c.create_line(*coords, fill=col, width=2 if m['transition'] else 1)

        # Start (green) and end (red) markers
        for p, col in ((self.start, "#2ca02c"), (self.moves[-1]['pts'][-1] if self.moves else None, "#d62728")):
            if p:
                x, y = scr(p)
                c.create_oval(x - 4, y - 4, x + 4, y + 4, fill=col, outline="")

        # Head direction A (arrows at the middle and the end of every move)
        arrow_line = ""
        if self.arrows_var.get():
            arrow_line = self._draw_arrows(scr) + "\n"

        n_layers = len(set(m['layer'] for m in self.moves)) if self.moves else 0
        n_tr = sum(1 for m in self.moves if m['transition'])
        self.info.config(text=(
            f"{len(self.moves)} moves ({n_tr} in transitions), {n_layers} layer(s), Z {b[4]:.1f} to {b[5]:.1f} mm   |   "
            f"axes: X/Y {L:g} mm, Z {L / zex:g} mm (Z shown x{zex})   |   green = start, red = end\n" + arrow_line +
            f"Left-drag: rotate   |   Right-drag: move   |   Wheel: zoom   |   Double-click: reset view"))

    def _draw_arrows(self, scr):
        """Arrows showing the head direction A (cos A, sin A in XY) at the middle and the end of
        each move, coloured by the angle between A and the travel direction. Returns a summary."""
        c = self.canvas
        n_red = 0
        for h in self.headings:
            p = h['point']
            a = math.radians(h['a'])
            x0, y0 = scr(p)
            x1, y1 = scr((p[0] + math.cos(a), p[1] + math.sin(a), p[2]))
            dx, dy = x1 - x0, y1 - y0
            n = math.hypot(dx, dy)
            if n < 1e-9:
                continue                       # A points straight at the viewer (e.g. Front view)
            col = ARROW_OK if h['dev'] <= 5 else (ARROW_WARN if h['dev'] <= 20 else ARROW_BAD)
            n_red += h['dev'] > 20
            c.create_line(x0, y0, x0 + dx / n * ARROW_PX, y0 + dy / n * ARROW_PX, fill=col, width=2,
                          arrow=tk.LAST, arrowshape=(6, 7, 3), tags=("head_arrow",))
        if not self.headings:
            return "Head direction: no A values in the path."
        worst = max(self.headings, key=lambda h: h['dev'])
        return ("Head direction A (arrows; green <= 5 deg, orange <= 20, red > 20 off the travel direction): "
                "largest %.1f deg (%s of move %d), %d red of %d"
                % (worst['dev'], worst['where'], worst['move'] + 1, n_red, len(self.headings)))

    # ---------- mouse ----------
    def _press(self, e):
        self._last = (e.x, e.y)

    def _rotate(self, e):
        dx, dy = e.x - self._last[0], e.y - self._last[1]
        self._last = (e.x, e.y)
        self.yaw -= math.radians(dx * 0.5)
        self.pitch = max(math.radians(-90), min(math.radians(90), self.pitch + math.radians(dy * 0.5)))
        self.redraw()

    def _move(self, e):
        dx, dy = e.x - self._last[0], e.y - self._last[1]
        self._last = (e.x, e.y)
        self.pan = (self.pan[0] + dx, self.pan[1] + dy)
        self.redraw()

    def _wheel(self, e):
        f = 1.2 if e.delta > 0 else 1 / 1.2
        W, H = self.canvas.winfo_width(), self.canvas.winfo_height()
        mx, my = e.x - W / 2, e.y - H / 2          # keep the point under the mouse in place
        self.pan = (mx - (mx - self.pan[0]) * f, my - (my - self.pan[1]) * f)
        self.zoom *= f
        self.redraw()

    def close(self):
        if self.on_close:
            self.on_close()
        self.win.destroy()


_open_views = {}      # parent window -> its View3D (one 3D window per app window)


def open_view(parent, get_text, empty_message="Nothing to show yet.", title="3D View"):
    """Open the 3D view for `parent` (or bring it to the front and reload it).
    get_text() must return the current KRL text."""
    if not get_text().strip():
        messagebox.showinfo(title, empty_message)
        return None
    view = _open_views.get(parent)
    if view is not None and view.win.winfo_exists():
        view.reload()
        view.win.lift()
        return view
    view = View3D(parent, get_text, on_close=lambda: _open_views.pop(parent, None), title=title)
    _open_views[parent] = view
    return view
