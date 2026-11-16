"""3D view window shared by the generator apps (tkinter only, no extra libraries).

Shows the path exactly as written in the KRL text (what goes to the robot): all layers
stacked in Z, CIRCs as real 3D arcs, transitions in purple, layers coloured.
Left-drag rotates, right/middle-drag moves, wheel zooms, double-click resets.
"Show the robot" draws the arm (robot_model) following the path: slider, Play, speed.

    open_view(parent, get_text, empty_message, on_position)   open (or reload + raise) the window

Kept light for long programs (measured with 100 layers, 5300 moves):
- neighbouring moves of one colour are drawn as ONE canvas line (`_runs`), not one per move;
- while the mouse drags or the robot plays, only a share of the points and arrows is drawn
  (`fast`); the full picture comes back when the mouse is released;
- several mouse events between two redraws give one redraw (`_request`);
- when only the robot moves, only the robot is drawn again (the path stays on the canvas).
"""
import bisect
import math
import time
import tkinter as tk
from tkinter import messagebox, ttk

import krl_export
import path_model as pm
import robot_model as rm
import ui_images
import ui_theme

# Layer colours: a continuous ramp (ui_images.layer_colors), so any number of layers gets
# distinct colours; transitions, path and texts come from the theme palette (ui_theme).
ARROW_OK, ARROW_WARN, ARROW_BAD = "#2ca02c", "#ff7f0e", "#d62728"   # A vs travel: <= 5, <= 20, > 20 deg
ARROW_PX = 16                                                       # arrow length on screen
BED = None                 # (x, y) size of the bed plate in mm, drawn under the robot (set by the main app)
ROBOT_ARM, ROBOT_JOINT, ROBOT_TOOL, ROBOT_BAD = "#f2681f", "#33363b", "#8a8f98", "#d62728"
ROBOT_STEP = 5.0           # mm between the robot positions of the slider
PLAY_SPEED = 200.0         # mm of path per second at 1x (the same for a short and a long program)
SPEEDS = ("0.1x", "0.25x", "0.5x", "0.75x", "1x", "2x", "4x", "8x")
FAST_POINTS = 6000         # points drawn while dragging / playing: Tk needs about 5 ms per 1000 on screen
FAST_ARROWS = 250          # arrows drawn while dragging
MAX_ARROWS = 1500          # arrows drawn when the view stands still

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


def _runs(moves, points=None):
    """Moves -> [(transition, layer, [points])]: neighbouring moves of the same kind that join
    end to start become one polyline (one canvas item instead of one per move).
    points: the moves' points in another frame (same shape), else the moves' own."""
    out = []
    for k, m in enumerate(moves):
        pts = points[k] if points is not None else m['pts']
        if not pts:
            continue
        last = out[-1] if out else None
        if last and last[0] == m['transition'] and last[1] == m['layer'] and last[2][-1] == pts[0]:
            last[2].extend(pts[1:])
        else:
            out.append((m['transition'], m['layer'], list(pts)))
    return out


class View3D:
    DEFAULT_YAW, DEFAULT_PITCH = math.radians(-35), math.radians(35)

    def __init__(self, parent, get_text, on_close=None, title="3D View", on_position=None):
        """parent: Tk window; get_text(): returns the KRL text to show;
        on_close(): called when the window is closed;
        on_position(item index): called when the robot is put on another line of the program."""
        self.get_text = get_text
        self.on_close = on_close
        self.on_position = on_position
        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.geometry("860x640")
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        # the same look as the main window when its styles exist (ui_theme.apply was called)
        styled = bool(getattr(parent._root(), "_palette", None))
        bar = tk.Frame(self.win)
        bar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)
        tk.Label(bar, text="Z exaggeration:").pack(side=tk.LEFT)
        self.zex_var = tk.IntVar(value=1)
        tk.Scale(bar, from_=1, to=40, orient=tk.HORIZONTAL, length=160, variable=self.zex_var,
                 showvalue=True, command=lambda _v: self.redraw()).pack(side=tk.LEFT, padx=(0, 10))
        self.by_layer_var = tk.BooleanVar(value=True)

        def check(row, text, var):
            if styled:
                return ttk.Checkbutton(row, text=" " + text, variable=var, command=self.redraw,
                                       style="Check.TCheckbutton", cursor="hand2")
            return tk.Checkbutton(row, text=text, variable=var, command=self.redraw)

        def button(row, text, command, width=5):
            if styled:
                return ttk.Button(row, text=text, command=command, style="Small.Rounded.TButton", cursor="hand2",
                                  width=width)
            return tk.Button(row, text=text, width=width, command=command)
        check(bar, "Colour by layer", self.by_layer_var).pack(side=tk.LEFT, padx=(0, 10))
        self.arrows_var = tk.BooleanVar(value=False)
        check(bar, "Head direction (A)", self.arrows_var).pack(side=tk.LEFT, padx=(0, 10))
        for txt, yaw, pitch in (("Iso", self.DEFAULT_YAW, self.DEFAULT_PITCH), ("Top", 0.0, math.radians(90)),
                                ("Front", 0.0, 0.0), ("Side", math.radians(-90), 0.0)):
            button(bar, txt, lambda y=yaw, p=pitch: self.set_view(y, p)).pack(side=tk.LEFT, padx=2)
        button(bar, "Reload", self.reload, width=7).pack(side=tk.RIGHT)

        # second row: the robot arm following the path
        bar2 = tk.Frame(self.win)
        bar2.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 6))
        self.robot_var = tk.BooleanVar(value=False)
        check(bar2, "Show the robot", self.robot_var).pack(side=tk.LEFT, padx=(0, 10))
        self.frame_path = False                     # robot view framed on the path (True) or the whole robot
        self.frame_btn = button(bar2, "Zoom to path", self.toggle_frame, width=12)
        self.frame_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.play_btn = button(bar2, "Play", self.toggle_play, width=6)
        self.play_btn.pack(side=tk.LEFT, padx=(0, 6))
        tk.Label(bar2, text="Speed:").pack(side=tk.LEFT)
        self.speed_var = tk.StringVar(value="1x")
        ttk.Combobox(bar2, textvariable=self.speed_var, values=SPEEDS, state="readonly", width=6
                     ).pack(side=tk.LEFT, padx=(2, 8))
        self.live_var = tk.BooleanVar(value=False)   # the robot draws the path as it goes (the rest stays faint)
        check(bar2, "Live drawing", self.live_var).pack(side=tk.LEFT, padx=(0, 8))
        self.pos_var = tk.DoubleVar(value=0.0)
        self.pos_scale = ttk.Scale(bar2, from_=0.0, to=1.0, variable=self.pos_var, orient=tk.HORIZONTAL,
                                   command=lambda _v: self._pos_moved())
        self.pos_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.pos_scale.bind("<ButtonRelease-1>", lambda e: (self._request(), self._tell_position()))
        self._playing = False
        self.report = None
        self._pending = None                        # the redraw waiting for the event loop (after id)
        self._scene = None                          # what the robot scene on the canvas was drawn for
        self._told = None

        self.win.update_idletasks()                 # wide enough for the whole toolbar (Side, Reload)
        self.win.geometry("%dx640" % max(860, bar.winfo_reqwidth() + 24))
        self.win.minsize(min(bar.winfo_reqwidth() + 24, 1200), 300)
        self.canvas = tk.Canvas(self.win, bg="white", highlightthickness=0)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.info = tk.Label(self.win, anchor="w", justify=tk.LEFT, fg="#555555", font=("Segoe UI", 8))
        self.info.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=2)

        c = self.canvas
        c.bind("<Configure>", lambda e: self._request())
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._rotate)
        for b in ("1", "2", "3"):
            c.bind(f"<ButtonRelease-{b}>", lambda e: self._request())
        for b in ("2", "3"):
            c.bind(f"<ButtonPress-{b}>", self._press)
            c.bind(f"<B{b}-Motion>", self._move)
        c.bind("<MouseWheel>", self._wheel)
        c.bind("<Double-Button-1>", lambda e: self.reset_view())
        self.win.bind("<Left>", lambda e: self.step(-1))
        self.win.bind("<Right>", lambda e: self.step(1))
        self.win.bind("<space>", lambda e: self.toggle_play())

        self.P = getattr(parent, "_palette", None) or ui_theme.THEMES["light"]
        self.apply_palette(self.P, redraw=False)
        self.reset_view(redraw=False)
        self.reload()

    # ---------- data ----------
    def reload(self):
        items = pm.parse_krl(self.get_text())
        self.start, self.moves = pm.path_3d(items)
        # the approach from above and the lift at the end are in the program, but they are not
        # part of the printed shape: left out here (they would squeeze the layers flat)
        if any(m.get('aux') for m in self.moves):
            self.moves = [m for m in self.moves if not m.get('aux')]
            self.start = self.moves[0]['pts'][0] if self.moves else None
        self.headings = pm.heading_checks(items)
        self.items = items
        self.runs = _runs(self.moves)
        self._rad = (None, 1.0)                      # (Z exaggeration, radius of the path's bounding sphere)
        self.report = None                           # the robot along this program: worked out when shown
        self._scene = None
        self._playing = False
        self.play_btn.configure(text="Play")
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

    def _request(self, fast=False):
        """Redraw when the event loop is free: many mouse events in between give ONE redraw.
        fast: the light picture (while dragging); a later full request replaces it."""
        if self._pending is not None:
            if fast or not self._pending[1]:
                return                               # one is waiting already (and it is not lighter than asked)
            self.win.after_cancel(self._pending[0])
        self._pending = (self.win.after(1, lambda: self.redraw(fast)), fast)

    def _screen(self, center, zex, radius):
        """The projection of this redraw: returns (scr(point) -> (x, y), scale in px per mm, depth(point))."""
        c = self.canvas
        W, H = max(c.winfo_width(), 10), max(c.winfo_height(), 10)
        cy_, sy_ = math.cos(self.yaw), math.sin(self.yaw)
        cp_, sp_ = math.cos(self.pitch), math.sin(self.pitch)
        s = 0.45 * min(W, H) / radius * self.zoom
        ox, oy = W / 2 + self.pan[0], H / 2 + self.pan[1]
        cx, cy, cz = center
        ax, ay = s * cy_, -s * sy_                   # screen x = ox + ax*x + ay*y
        bx, by, bz = -s * sy_ * sp_, -s * cy_ * sp_, -s * cp_ * zex      # screen y = oy + bx*x + by*y + bz*z

        def scr(p):
            x, y, z = p[0] - cx, p[1] - cy, p[2] - cz
            return ox + ax * x + ay * y, oy + bx * x + by * y + bz * z

        def depth(p):                               # larger = nearer to the viewer
            return -sy_ * cp_ * p[0] - cy_ * cp_ * p[1] + sp_ * p[2]
        scr.k = (ox - ax * cx - ay * cy, ax, ay, oy - bx * cx - by * cy - bz * cz, bx, by, bz)
        return scr, s, depth

    def _draw_runs(self, runs, scr, fast, tag=None, colour=None):
        """The path: one canvas line per run. fast: only every n-th layer (the first and the last
        always), and if that is still too much, only every n-th point of long runs."""
        c, P = self.canvas, self.P
        by_layer = self.by_layer_var.get()
        n_layers = (max(r[1] for r in runs) + 1) if runs else 1
        cols = ui_images.layer_colors(n_layers, P["ramp"])
        total = sum(len(r[2]) for r in runs)
        skip = 1
        if fast and total > FAST_POINTS:
            every = int(math.ceil(total / float(FAST_POINTS)))
            runs = [r for r in runs if r[1] % every == 0 or r[1] == n_layers - 1]
            skip = max(1, int(math.ceil(sum(len(r[2]) for r in runs) / float(FAST_POINTS))))
        for transition, layer, pts in runs:
            col = colour or (P["transition"] if transition else (cols[layer] if by_layer else P["path"]))
            if skip > 1 and len(pts) > 2 * skip:
                pts = pts[::skip] + [pts[-1]]
            # (the projection written out: this loop runs for every point of the program; a point
            # less than a pixel from the last drawn one is left out, which changes nothing visible)
            x0, ax, ay, y0, bx, by, bz = scr.k
            coords, lx, ly = [], -1e9, -1e9
            for x, y, z in pts:
                sx, sy = x0 + ax * x + ay * y, y0 + bx * x + by * y + bz * z
                if abs(sx - lx) + abs(sy - ly) >= 1.0:
                    coords.append(sx)
                    coords.append(sy)
                    lx, ly = sx, sy
            if len(coords) == 2:
                coords.extend(scr(pts[-1]))
            if len(coords) >= 4:
                c.create_line(*coords, fill=col, width=2 if transition and not colour else 1, tags=tag)

    def redraw(self, fast=False):
        """Draw everything again. fast = the light picture used while the mouse drags."""
        self._pending = None
        c = self.canvas
        if not c.winfo_exists():
            return
        W, H = max(c.winfo_width(), 10), max(c.winfo_height(), 10)
        if not getattr(self, "pts_all", None):
            c.delete("all")
            c.create_text(W / 2, H / 2, text="Nothing to show yet: generate a path first, then press Reload.",
                          fill=self.P["muted"])
            self.info.config(text="")
            return
        if self.robot_var.get():
            self._redraw_robot(W, H, fast)
            return
        c.delete("all")
        self._scene = None
        zex = max(1, int(self.zex_var.get()))
        # scale from the bounding sphere so rotating never pushes the shape out of view
        if self._rad[0] != zex:                      # (kept: it looks at every point of the program)
            self._rad = (zex, max(math.sqrt((p[0] - self.center[0]) ** 2 + (p[1] - self.center[1]) ** 2 +
                                            ((p[2] - self.center[2]) * zex) ** 2) for p in self.pts_all) or 1.0)
        rad = self._rad[1]
        scr, _s, _depth = self._screen(self.center, zex, rad)

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

        self._draw_runs(self.runs, scr, fast)

        # Start (green) and end (red) markers
        for p, col in ((self.start, self.P["start"]), (self.moves[-1]['pts'][-1] if self.moves else None, self.P["end"])):
            if p:
                x, y = scr(p)
                c.create_oval(x - 4, y - 4, x + 4, y + 4, fill=col, outline="")

        # Head direction A (arrows at the middle and the end of every move)
        arrow_line = ""
        if self.arrows_var.get():
            arrow_line = self._draw_arrows(scr, fast) + "\n"

        n_layers = len(set(m['layer'] for m in self.moves)) if self.moves else 0
        n_tr = sum(1 for m in self.moves if m['transition'])
        self._set_info(0, (
            f"{len(self.moves)} moves ({n_tr} in transitions), {n_layers} layer(s), Z {b[4]:.1f} to {b[5]:.1f} mm   |   "
            f"axes: X/Y {L:g} mm, Z {L / zex:g} mm (Z shown x{zex})   |   green = start, red = end\n" + arrow_line +
            f"Left-drag: rotate   |   Right-drag: move   |   Wheel: zoom   |   Double-click: reset view"))

    def _draw_arrows(self, scr, fast=False):
        """Arrows showing the head direction A (cos A, sin A in XY) at the middle and the end of
        each move, coloured by the angle between A and the travel direction. Returns a summary.
        Every arrow is drawn up to MAX_ARROWS (FAST_ARROWS while dragging); with more, the ones
        that are off the travel direction are kept first and the others are thinned out evenly."""
        c = self.canvas
        heads = self.headings
        limit = FAST_ARROWS if fast else MAX_ARROWS
        if len(heads) > limit:
            off = [h for h in heads if h['dev'] > 5]
            rest = [h for h in heads if h['dev'] <= 5]
            off = off[::max(1, int(math.ceil(len(off) / float(max(limit * 3 // 4, 1)))))]
            keep = max(limit - len(off), 1)
            heads = off + rest[::max(1, int(math.ceil(len(rest) / float(keep))))]
        for h in heads:
            p = h['point']
            a = math.radians(h['a'])
            x0, y0 = scr(p)
            x1, y1 = scr((p[0] + math.cos(a), p[1] + math.sin(a), p[2]))
            dx, dy = x1 - x0, y1 - y0
            n = math.hypot(dx, dy)
            if n < 1e-9:
                continue                       # A points straight at the viewer (e.g. Front view)
            col = ARROW_OK if h['dev'] <= 5 else (ARROW_WARN if h['dev'] <= 20 else ARROW_BAD)
            c.create_line(x0, y0, x0 + dx / n * ARROW_PX, y0 + dy / n * ARROW_PX, fill=col, width=2,
                          arrow=tk.LAST, arrowshape=(6, 7, 3), tags=("head_arrow",))
        if not self.headings:
            return "Head direction: no A values in the path."
        n_red = sum(1 for h in self.headings if h['dev'] > 20)
        worst = max(self.headings, key=lambda h: h['dev'])
        shown = "" if len(heads) == len(self.headings) else "; %d arrows drawn" % len(heads)
        return ("Head direction A (arrows; green <= 5 deg, orange <= 20, red > 20 off the travel direction): "
                "largest %.1f deg (%s of move %d), %d red of %d%s"
                % (worst['dev'], worst['where'], worst['move'] + 1, n_red, len(self.headings), shown))

    # ---------- the robot arm ----------
    def _robot_report(self):
        """The program on the robot model, with the path and the bed in the robot's world."""
        if self.report is None:
            settings = krl_export.active_settings()[0]
            rep = rm.analyse(self.items, settings, step=ROBOT_STEP)
            base = rm.frame(*settings.base)
            world = [[rm.frame_point(base, p) for p in m['pts']] for m in self.moves]
            rep.runs = _runs(self.moves, world)
            rep.bed = [rm.frame_point(base, p) for p in ((0, 0, 0), (BED[0], 0, 0), (BED[0], BED[1], 0),
                                                         (0, BED[1], 0))] if BED else []
            rep.tool = rm.frame(*settings.tool)
            top = rep.robot.base_height + rep.robot.upper_arm + rep.robot.elbow
            path = [p for mv in world for p in mv]

            def sphere(pts):
                lo = [min(p[k] for p in pts) for k in range(3)]
                hi = [max(p[k] for p in pts) for k in range(3)]
                ctr = tuple((lo[k] + hi[k]) / 2 for k in range(3))
                return ctr, max(math.sqrt(sum((p[k] - ctr[k]) ** 2 for k in range(3))) for p in pts)
            rep.frame_robot = sphere([(0.0, 0.0, 0.0), (0.0, 0.0, top)] + rep.bed + path)
            ctr, rad = sphere(path or [(0.0, 0.0, 0.0)])
            rep.frame_path = (ctr, max(1.5 * rad, 120.0))        # the path with the head and the forearm above it
            # the way along the program up to every position, for a Play that runs at an even speed
            rep.dist, d, last = [], 0.0, None
            for ps in rep.poses:
                if last is not None:
                    d += math.sqrt(sum((ps['world'][k] - last[k]) ** 2 for k in range(3)))
                last = ps['world']
                rep.dist.append(d)
            # what every position draws in a live drawing: (transition, layer) of its move
            kind = {m['line']: (m['transition'], m['layer']) for m in self.moves}
            rep.kinds = [kind.get(ps['item']) for ps in rep.poses]      # None: approach / lift, not printed
            self.report = rep
            self.pos_scale.configure(to=max(len(rep.poses) - 1, 1))
            self.pos_var.set(min(self.pos_var.get(), max(len(rep.poses) - 1, 0)))
        return self.report

    def position(self):
        """The robot position of the slider (index into the report's poses)."""
        n = len(self._robot_report().poses)
        return max(0, min(n - 1, int(round(self.pos_var.get())))) if n else 0

    def _redraw_robot(self, W, H, fast=False):
        """The arm at the slider's position, the path and the bed, all in true scale (robot world).
        The path, bed and floor are only drawn again when the view changed; else just the arm."""
        c, P = self.canvas, self.P
        rep = self._robot_report()
        ctr, radius = rep.frame_path if self.frame_path else rep.frame_robot
        scr, s, depth = self._screen(ctr, 1, radius)
        live = self.live_var.get()
        scene = (id(rep), self.yaw, self.pitch, self.zoom, self.pan, W, H, self.by_layer_var.get(),
                 self.frame_path, id(P), fast, live)
        if scene != self._scene:
            c.delete("all")
            self._scene = scene
            # the floor under the robot foot, the bed plate, the world axes in the foot
            g = 100.0
            for k in range(-3, 4):
                c.create_line(*scr((-3 * g, k * g, 0)), *scr((3 * g, k * g, 0)), fill=P["grid"])
                c.create_line(*scr((k * g, -3 * g, 0)), *scr((k * g, 3 * g, 0)), fill=P["grid"])
            if rep.bed:
                flat = [v for p in rep.bed for v in scr(p)]
                c.create_polygon(*flat, fill=P["card"], outline=P["muted"], dash=(4, 3))
            for d, col, name in (((150, 0, 0), "#d62728", "X"), ((0, 150, 0), "#2ca02c", "Y"),
                                 ((0, 0, 150), "#1f77b4", "Z")):
                e_s = scr(d)
                c.create_line(*scr((0, 0, 0)), *e_s, fill=col, width=2, arrow=tk.LAST)
                c.create_text(e_s[0] + 8, e_s[1] - 8, text=name, fill=col, font=("Segoe UI", 9, "bold"))
            # live drawing: the whole path faint, the part behind the robot in colour on top of it
            self._draw_runs(rep.runs, scr, fast, colour=P["grid"] if live else None)
            self._live_k = 0
        else:
            c.delete("robot")
        if live:
            self._draw_live(rep, scr, self.position())

        n = len(rep.poses)
        k = self.position()
        pose = rep.poses[k] if n else None
        line = ""
        if pose is not None and pose['q'] is not None:
            q = pose['q']
            pts = rm.joint_points(rep.robot, q)
            tcp = rm.frame_point(rm.frame_mul(rm.forward(rep.robot, q), rep.tool), (0, 0, 0))
            # the links at about their real thickness (the lengths are the data sheet's)
            wide = max(3.0, min(60.0, 90.0 * s))
            segs = [(pts[0], pts[1], ROBOT_JOINT, 1.5 * wide), (pts[1], pts[2], ROBOT_ARM, 1.25 * wide),
                    (pts[2], pts[3], ROBOT_ARM, wide), (pts[3], pts[4], ROBOT_ARM, 0.9 * wide),
                    (pts[4], pts[5], ROBOT_ARM, 0.8 * wide), (pts[5], pts[6], ROBOT_JOINT, 0.55 * wide)]
            mid = lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)
            # everything is drawn back to front: the arm's links and the faces of the head's boxes
            parts = [(depth(mid(a, b)), None, (a, b, col, w)) for a, b, col, w in segs]
            boxes = rep.head.boxes if rep.head else ()
            if not boxes:                            # no head shape: a line from the flange to the TCP
                parts.append((depth(mid(pts[6], tcp)), None, (pts[6], tcp, ROBOT_TOOL, 0.3 * wide)))
            tool_world = rm.frame_mul(rm.forward(rep.robot, q), rep.tool)
            edge = ROBOT_BAD if pose.get('hit') else P["canvas"]
            for box in boxes:
                corners = [rm.frame_point(tool_world, p) for p in rm.box_corners(box)]
                for n_face, face in enumerate(rm.BOX_FACES):
                    quad = [corners[i] for i in face]
                    centre = tuple(sum(p[j] for p in quad) / 4.0 for j in range(3))
                    shade = ui_images.mix(box[1], "#000000", (0.0, 0.0, 0.14, 0.14, 0.28, 0.28)[n_face])
                    parts.append((depth(centre), quad, shade))
            for _d, quad, what in sorted(parts, key=lambda part: part[0]):
                if quad is not None:
                    c.create_polygon(*[v for p in quad for v in scr(p)], fill=what, outline=edge, tags=("robot",))
                    continue
                a, b, col, w = what
                c.create_line(*scr(a), *scr(b), fill=col, width=w, capstyle=tk.ROUND, tags=("robot",))
                if col == ROBOT_ARM:                 # the axis at the start of this link
                    x, y = scr(a)
                    r = 0.33 * w
                    c.create_oval(x - r, y - r, x + r, y + r, fill=ROBOT_JOINT, outline="", tags=("robot",))
            x, y = scr(tcp)
            c.create_oval(x - 4, y - 4, x + 4, y + 4, fill=P["accent"], outline=P["canvas"], tags=("robot",))
            line = ("Position %d of %d (program line %d):   %s" % (k + 1, n, pose['item'] + 1,
                                                                   "COLLISION HERE   " if pose.get('hit') else "")
                    + "   ".join("A%d %.1f°" % (j + 1, v) for j, v in enumerate(q)))
        elif pose is not None:
            x, y = scr(pose['world'])
            c.create_line(x - 7, y - 7, x + 7, y + 7, fill=ROBOT_BAD, width=3, tags=("robot",))
            c.create_line(x - 7, y + 7, x + 7, y - 7, fill=ROBOT_BAD, width=3, tags=("robot",))
            c.create_text(x + 12, y, anchor="w", text="out of reach", fill=ROBOT_BAD, font=("Segoe UI", 9, "bold"),
                          tags=("robot",))
            line = ("Position %d of %d (program line %d):   OUT OF REACH (X %.0f, Y %.0f, Z %.0f)"
                    % ((k + 1, n, pose['item'] + 1) + tuple(pose['xyz'])))
        found = ("   |   ⚠ " + "  ⚠ ".join(rep.messages)) if rep.messages \
            else "   |   ✓ reach, axis limits, singularities and collisions OK"
        text = (line + "\n" + rep.summary() + found + "\n"
                "Robot from the data sheet, head: %s, true scale.   |   Left / Right: one step   |   "
                "Space: play / stop   |   1x = %g mm/s" % (rep.head.name if rep.head else "none", PLAY_SPEED))
        self._set_info(max(W - 12, 200), text)

    def _set_info(self, wrap, text):
        """The text under the picture; only touched when it changes (a new text lays the window
        out again, which costs a second drawing of the whole picture)."""
        if (wrap, text) != getattr(self, "_info_now", None):
            self._info_now = (wrap, text)
            self.info.config(wraplength=wrap, text=text)

    def _draw_live(self, rep, scr, k):
        """Live drawing: the path from the start up to position k, in the layer colours. Only the
        new piece since the last call is added; going back draws it again from the start."""
        c, P = self.canvas, self.P
        if k < self._live_k:
            c.delete("live")
            self._live_k = 0
        if k <= self._live_k:
            return
        by_layer = self.by_layer_var.get()
        n_layers = max([kd[1] for kd in rep.kinds if kd] or [0]) + 1
        cols = ui_images.layer_colors(n_layers, P["ramp"])
        coords, kind = list(scr(rep.poses[self._live_k]['world'])), rep.kinds[self._live_k + 1]

        def flush():
            if len(coords) >= 4:
                col = P["muted"] if kind is None else (
                    P["transition"] if kind[0] else (cols[kind[1]] if by_layer else P["path"]))
                c.create_line(*coords, fill=col, width=1 if kind is None else 2, tags=("live",))
        for i in range(self._live_k + 1, k + 1):
            if rep.kinds[i] != kind:
                flush()
                coords, kind = coords[-2:], rep.kinds[i]
            coords.extend(scr(rep.poses[i]['world']))
        flush()
        self._live_k = k

    def toggle_frame(self):
        """Robot view: the whole robot in the window, or the path filling it (the head above it)."""
        self.frame_path = not self.frame_path
        self.frame_btn.configure(text="Whole robot" if self.frame_path else "Zoom to path")
        self.zoom, self.pan = 1.0, (0.0, 0.0)
        if not self.robot_var.get():
            self.robot_var.set(True)
        self.redraw()

    def _pos_moved(self):
        if self.robot_var.get():
            self._request(fast=True)                 # (the slider's release asks for the full picture)

    def _tell_position(self):
        """Tell the owner of the window (the main app) which program line the robot stands on."""
        if not self.on_position or not self.robot_var.get() or self.report is None or not self.report.poses:
            return
        item = self.report.poses[self.position()]['item']
        if item != self._told:
            self._told = item
            self.on_position(item)

    def step(self, n):
        """One position forward (n = 1) or back (n = -1): the Left / Right keys."""
        if not self.robot_var.get():
            return
        self.pos_var.set(max(0, min(len(self._robot_report().poses) - 1, self.position() + n)))
        self.redraw()
        self._tell_position()

    def speed(self):
        try:
            return float(self.speed_var.get().rstrip("x"))
        except ValueError:
            return 1.0

    def toggle_play(self):
        """Run the robot along the path at PLAY_SPEED x the chosen speed, or stop it."""
        self._playing = not self._playing
        self.play_btn.configure(text="Stop" if self._playing else "Play")
        if self._playing:
            if not self.robot_var.get():
                self.robot_var.set(True)
            n = len(self._robot_report().poses)
            if self.pos_var.get() >= n - 1:
                self.pos_var.set(0)
            self.redraw(fast=True)
            self._clock = time.time()
            self._way = self.report.dist[self.position()] if n else 0.0
            self.win.after(30, self._tick)
        else:
            self.redraw()
            self._tell_position()

    def _tick(self):
        """Play: move as far as the time since the last tick allows (so a slow PC plays at the
        same speed, with fewer pictures)."""
        if not self._playing or not self.win.winfo_exists():
            return
        rep = self._robot_report()
        now = time.time()
        self._way += min(now - self._clock, 0.25) * PLAY_SPEED * self.speed()
        self._clock = now
        k = bisect.bisect_left(rep.dist, self._way)
        if k >= len(rep.poses) - 1:
            k, self._playing = len(rep.poses) - 1, False
            self.play_btn.configure(text="Play")
        if k != self.position() or not self._playing:
            self.pos_var.set(k)
            self.redraw(fast=self._playing)          # the light picture while it runs
        if self._playing:
            self.win.after(30, self._tick)
        else:
            self._tell_position()

    # ---------- mouse ----------
    def _press(self, e):
        self._last = (e.x, e.y)

    def _rotate(self, e):
        dx, dy = e.x - self._last[0], e.y - self._last[1]
        self._last = (e.x, e.y)
        self.yaw -= math.radians(dx * 0.5)
        self.pitch = max(math.radians(-90), min(math.radians(90), self.pitch + math.radians(dy * 0.5)))
        self._request(fast=True)

    def _move(self, e):
        dx, dy = e.x - self._last[0], e.y - self._last[1]
        self._last = (e.x, e.y)
        self.pan = (self.pan[0] + dx, self.pan[1] + dy)
        self._request(fast=True)

    def _wheel(self, e):
        f = 1.2 if e.delta > 0 else 1 / 1.2
        W, H = self.canvas.winfo_width(), self.canvas.winfo_height()
        mx, my = e.x - W / 2, e.y - H / 2          # keep the point under the mouse in place
        self.pan = (mx - (mx - self.pan[0]) * f, my - (my - self.pan[1]) * f)
        self.zoom *= f
        self.redraw(fast=True)
        if getattr(self, "_settle", None):
            self.win.after_cancel(self._settle)
        self._settle = self.win.after(250, self._settled)      # the full picture when the wheel rests

    def _settled(self):
        self._settle = None
        self._request()

    def apply_palette(self, P, redraw=True):
        """Theme colours (light / dark) for this window; the canvas included."""
        self.P = P
        ui_theme.paint_tk(self.win, P, canvases=True)
        self.info.configure(fg=P["muted"])
        ui_theme.title_bar(self.win, P is ui_theme.THEMES["dark"])
        if redraw:
            self.redraw()

    def close(self):
        self._playing = False
        if self.on_close:
            self.on_close()
        self.win.destroy()


_open_views = {}      # parent window -> its View3D (one 3D window per app window)


def open_view(parent, get_text, empty_message="Nothing to show yet.", title="3D View", on_position=None):
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
    view = View3D(parent, get_text, on_close=lambda: _open_views.pop(parent, None), title=title,
                  on_position=on_position)
    _open_views[parent] = view
    return view
