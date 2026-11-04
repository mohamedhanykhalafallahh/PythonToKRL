import tkinter as tk
from tkinter import messagebox, filedialog
from tkinter import ttk
import copy
import math
import re
import sys
import os
import subprocess

import krl_export   # shared header / TOOL / BASE / C_DIS / DEF-name export
import path_model as pm   # move types, KRL line formatting/parsing, 3D geometry
import shapes            # base loops (rounded rectangle) and the turn offset
import cuboid            # the cuboid path generator (Automate), shared with the main app
import view3d            # 3D view window (shared)
import export_settings_dialog   # export profiles (TOOL/BASE/speeds/decimals) dialog
import project_files     # save / open all inputs of a print (.json)

# Variables to store the points
points = []

# Variables to store the circ points
points_circ = []

# Motion command types for each line
motion_commands = []

# Orientations for each line
orientations = []

#For Center Change
xc = 0 
yc = 0
zc = 0

# Canvas dimensions
canvas_width = 400
canvas_height = 320

# Initial scaling factor (pixels per mm at zoom 1)
scaling_factor = 3

# Canvas view zoom on top of scaling_factor (changed by fit-to-drawing and mouse wheel).
# All drawing uses scaling_factor * view_zoom, and zooming always scales about the canvas
# origin (0,0) so new drawings stay aligned with what is already drawn.
view_zoom = 1.0
VIEW_ZOOM_MAX = 3.0          # never auto-zoom in more than 3x (single points, tiny shapes)
POINT_RADIUS = 2             # dot radius in pixels (kept constant when zooming)
LABEL_OFFSET = 9             # label distance from its line/arc, in pixels
LABEL_FONT = ("Segoe UI", 7)
LABEL_COLOR = "#9a9a9a"
_label_offsets = {}          # canvas text id -> (ox, oy) pixel offset from its anchor

# Global variable to track A-axis orientation for smooth transitions
current_a_angle = 180.0   # Current A angle

# Auto-Generate parameters of the current base (None if the base was made or changed by hand)
base_params = None
# Last values typed into the Auto-Generate popup (pre-fill); a project restores them too
generate_popup_values = {"Xr": "535", "Yr": "10", "Zr": "65", "L": "", "W": "", "Th": "", "r": ""}

# Undo history (bounded)
UNDO_HISTORY_LIMIT = 10
undo_history = []  # list of snapshots (bounded)
redo_history = []  # list of redo snapshots (bounded)

def _snapshot_state():
    # Capture deep copies of mutable program state and current output text
    return {
        'points': copy.deepcopy(points),
        'points_circ': copy.deepcopy(points_circ),
        'motion_commands': copy.deepcopy(motion_commands),
        'orientations': copy.deepcopy(orientations),
        'current_a_angle': current_a_angle,
        'base_params': copy.deepcopy(base_params),
        'output_text': output_text.get("1.0", "end-1c")
    }

def _restore_state(snap):
    global points, points_circ, motion_commands, orientations, current_a_angle, base_params
    points = copy.deepcopy(snap['points'])
    base_params = copy.deepcopy(snap.get('base_params'))
    points_circ = copy.deepcopy(snap['points_circ'])
    motion_commands = copy.deepcopy(snap['motion_commands'])
    orientations = copy.deepcopy(snap['orientations'])
    current_a_angle = snap.get('current_a_angle', 180.0)
    canvas.delete("all")
    reset_view_zoom()
    output_text.delete("1.0", tk.END)
    output_text.insert(tk.END, snap['output_text'])
    # Redraw what the restored output contains (the automated turns too, not only the base)
    redraw_canvas_from_state()

def _push_undo_snapshot():
    # Keep last 3 states
    if len(undo_history) >= UNDO_HISTORY_LIMIT:
        undo_history.pop(0)
    undo_history.append(_snapshot_state())
    # Any new action invalidates redo history
    redo_history.clear()

def undo_action(event=None):
    if undo_history:
        current = _snapshot_state()
        # Move current into redo
        if len(redo_history) >= UNDO_HISTORY_LIMIT:
            redo_history.pop(0)
        redo_history.append(current)
        snap = undo_history.pop()  # last snapshot
        _restore_state(snap)

def redo_action(event=None):
    if redo_history:
        current = _snapshot_state()
        # Move current into undo
        if len(undo_history) >= UNDO_HISTORY_LIMIT:
            undo_history.pop(0)
        undo_history.append(current)
        snap = redo_history.pop()  # last redo snapshot
        _restore_state(snap)


# ---------------------------------------------------------------- KRL line output
# Every generated KRL line goes through these helpers, so the line format (and any future
# rounding) is defined in one place: path_model.
PTP_S, PTP_T = 2, 43          # Status / Turn written on every PTP (fixed for now)

def emit(item):
    """Append one path_model item (Ptp/Lin/Circ/Comment) to the output box as a KRL line."""
    output_text.insert(tk.END, item.to_krl() + "\n")

def ptp_item(xyz, abc):
    return pm.Ptp(pm.pose(xyz, abc, PTP_S, PTP_T))

def lin_item(xyz, abc):
    return pm.Lin(pm.pose(xyz, abc))

def circ_item(via, end, abc):
    return pm.Circ(pm.pose(via), pm.pose(end, abc))

def emit_ptp(xyz, abc):
    emit(ptp_item(xyz, abc))

def emit_lin(xyz, abc):
    emit(lin_item(xyz, abc))

def emit_circ(via, end, abc):
    emit(circ_item(via, end, abc))

def emit_comment(text):
    emit(pm.Comment(text))

def a1(v):
    """Angle rounded to 0.1 deg (what the computed A/B/C values are written with)."""
    return round(float(v), 1)


def validate_coordinates(x, y, z, a, b, c):
    try:
        x = float(x)
        y = float(y)
        z = float(z)
        a = float(a)
        b = float(b)
        c = float(c)
        return True
    except ValueError:
        return False

def normalize_angle(angle):
    """Normalize angle to -180 to +180 range"""
    while angle > 180.0:
        angle -= 360.0
    while angle < -180.0:
        angle += 360.0
    return angle

def calculate_smooth_a_angle(dx, dy):
    """Calculate exact A-angle based on movement direction"""
    global current_a_angle
    
    # Calculate exact angle based on movement direction
    target_angle = math.degrees(math.atan2(dy, dx))
    target_angle = normalize_angle(target_angle)
    
    # Update current A angle to exact target
    current_a_angle = target_angle
    
    return current_a_angle

def get_current_a_angle():
    """Get current A-angle without updating it (for LIN movements)"""
    return current_a_angle

def generate_krl_code(points, motion_commands, points_circ, orientations, a, b, c, tilt_angle_deg):
    krl_code = ""

    # Guard against empty input
    if not points:
        return krl_code

    # Handle the origin point separately - use interface values for PTP start
    origin_point = points[0]
    krl_code += ptp_item(origin_point, (a, tilt_angle_deg, c)).to_krl() + "\n"

    i = 1
    j = 0

    for k in motion_commands:
        if k == "LIN":
            # Keep A-angle constant from previous movement (no rotation during LIN)
            lin_a = get_current_a_angle()  # Use current A-angle without change
            krl_code += lin_item(points[i], (a1(lin_a), tilt_angle_deg, c)).to_krl() + "\n"
            i += 1
        elif k == "CIRC":
            # Calculate A angle based on the NEXT edge direction (not the CIRC diagonal)
            # This ensures the tool orientation matches the straight edge after the corner
            
            middle_x = points_circ[j][0]
            middle_y = points_circ[j][1]
            end_x = points_circ[j + 1][0]
            end_y = points_circ[j + 1][1]
            
            # Look ahead to the next LIN point to get the actual edge direction
            if i < len(points):  # If there's a next LIN point
                next_x = points[i][0]
                next_y = points[i][1]
                # Calculate direction from CIRC end to next LIN point (the actual edge)
                dx = next_x - end_x
                dy = next_y - end_y
            else:
                # Last CIRC, use direction to first point (closing the loop)
                next_x = points[0][0]
                next_y = points[0][1]
                dx = next_x - end_x
                dy = next_y - end_y
            
            # Use exact A-angle calculation based on next edge direction
            A_angle = calculate_smooth_a_angle(dx, dy)
            
            # Use calculated A, constant B tilt (20°), and constant C (180°)
            krl_code += circ_item(points_circ[j], points_circ[j + 1], (a1(A_angle), tilt_angle_deg, c)).to_krl() + "\n"
            j += 2

    return krl_code

def update_krl_code():
    # Get interface values for orientations
    try:
        a = float(a_entry.get())
        b = float(b_entry.get())
        c = float(c_entry.get())
        tilt_angle_deg = float(tilt_entry.get())
    except Exception:
        a, b, c = 180.0, 20.0, 180.0  # Default fallback values
        tilt_angle_deg = 10.0
    
    # Generate KRL code for the points and motion commands
    krl_code = generate_krl_code(points, motion_commands, points_circ, orientations, a, b, c, tilt_angle_deg)
    # Add initialization lines
    krl_code_with_init = krl_code
    output_text.delete("1.0", tk.END)
    output_text.insert(tk.END, krl_code_with_init)

def update_scroll_region():
    # Get the bounding box of all drawn elements (points and lines)
    bbox = canvas.bbox(tk.ALL)
    
    # Check if bbox is None
    if bbox is not None:
        # Expand the bounding box to add some padding
        padding = 10
        bbox = (bbox[0] - padding, bbox[1] - padding, bbox[2] + padding, bbox[3] + padding)
        
        # Set the scroll region of the canvas
        canvas.config(scrollregion=bbox)

def _to_canvas(x, y):
    """World mm -> canvas pixels (Y inverted)."""
    s = scaling_factor * view_zoom
    return x * s, -y * s

def draw_point(x, y, color="red"):
    cx, cy = _to_canvas(x, y)
    r = POINT_RADIUS
    canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color)
    update_scroll_region()

def _draw_label(ax, ay, nx, ny, text):
    """Small grey label beside a drawing: anchor (ax, ay) in canvas px, pushed out along
    the unit normal (nx, ny) by LABEL_OFFSET px so it does not sit on top of the line."""
    ox, oy = nx * LABEL_OFFSET, ny * LABEL_OFFSET
    # Turns lie only a few pixels apart: show one label per group instead of a smeared pile
    for other in canvas.find_withtag("label"):
        if canvas.itemcget(other, "text") == text:
            x, y = canvas.coords(other)
            if math.hypot(x - (ax + ox), y - (ay + oy)) < 12:
                return
    tid = canvas.create_text(ax + ox, ay + oy, text=text, fill=LABEL_COLOR, font=LABEL_FONT, tags=("label",))
    _label_offsets[tid] = (ox, oy)

def draw_line(x1, y1, x2, y2, motion_command, color="blue"):
    cx1, cy1 = _to_canvas(x1, y1)
    cx2, cy2 = _to_canvas(x2, y2)
    canvas.create_line(cx1, cy1, cx2, cy2, fill=color)
    # Label beside the middle of the line, on the right-hand side of travel
    # (= outside of the shape for the counter-clockwise auto-generated loop)
    dx, dy = cx2 - cx1, cy2 - cy1
    d = math.hypot(dx, dy)
    if d > 1e-9 and motion_command:
        _draw_label((cx1 + cx2) / 2, (cy1 + cy2) / 2, -dy / d, dx / d, motion_command)

def _circle_through(p1, p2, p3):
    """Centre and radius of the circle through three 2D points, or None if collinear."""
    (ax, ay), (bx, by), (cx, cy) = p1, p2, p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    ux = ((ax*ax + ay*ay) * (by - cy) + (bx*bx + by*by) * (cy - ay) + (cx*cx + cy*cy) * (ay - by)) / d
    uy = ((ax*ax + ay*ay) * (cx - bx) + (bx*bx + by*by) * (ax - cx) + (cx*cx + cy*cy) * (bx - ax)) / d
    return ux, uy, math.hypot(ax - ux, ay - uy)

def draw_arc(x1, y1, xv, yv, x2, y2, motion_command="CIRC", color="blue"):
    """Draw a CIRC as the real circular arc start -> via -> end (what the robot does),
    instead of two straight lines. Falls back to two lines if the points are collinear."""
    c1, cv_, c2 = _to_canvas(x1, y1), _to_canvas(xv, yv), _to_canvas(x2, y2)
    circ = _circle_through(c1, cv_, c2)
    if circ is None:
        canvas.create_line(*c1, *cv_, *c2, fill=color)
        dx, dy = c2[0] - c1[0], c2[1] - c1[1]
        d = math.hypot(dx, dy)
        if d > 1e-9 and motion_command:
            _draw_label(cv_[0], cv_[1], -dy / d, dx / d, motion_command)
        return
    ux, uy, R = circ
    a1 = math.atan2(c1[1] - uy, c1[0] - ux)
    av = math.atan2(cv_[1] - uy, cv_[0] - ux)
    a2 = math.atan2(c2[1] - uy, c2[0] - ux)
    two_pi = 2 * math.pi
    # Sweep from a1 to a2 in the direction that passes through the via point
    ccw_v = (av - a1) % two_pi
    ccw_2 = (a2 - a1) % two_pi
    sweep = ccw_2 if ccw_v <= ccw_2 else -(two_pi - ccw_2)
    n = max(8, int(abs(math.degrees(sweep)) / 3))   # one segment per ~3 degrees
    pts = []
    for k in range(n + 1):
        t = a1 + sweep * k / n
        pts += [ux + R * math.cos(t), uy + R * math.sin(t)]
    canvas.create_line(*pts, fill=color)
    if motion_command:
        # Label beside the middle of the arc, on the outside (away from the centre)
        am = a1 + sweep / 2
        mx, my = ux + R * math.cos(am), uy + R * math.sin(am)
        _draw_label(mx, my, math.cos(am), math.sin(am), motion_command)

def _apply_zoom(factor):
    """Scale everything on the canvas about the origin by factor; keep dots and label
    offsets at their pixel size."""
    global view_zoom
    view_zoom *= factor
    canvas.scale("all", 0, 0, factor, factor)
    r = POINT_RADIUS
    for it in canvas.find_all():
        t = canvas.type(it)
        if t == "oval":
            x0, y0, x1, y1 = canvas.coords(it)
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            canvas.coords(it, mx - r, my - r, mx + r, my + r)
        elif t == "text" and it in _label_offsets:
            ox, oy = _label_offsets[it]
            x, y = canvas.coords(it)
            canvas.coords(it, x - ox * factor + ox, y - oy * factor + oy)

def _canvas_view_size():
    w, h = canvas.winfo_width(), canvas.winfo_height()
    if w <= 1 or h <= 1:          # not mapped yet: use the configured size
        w, h = int(canvas.cget("width")), int(canvas.cget("height"))
    return w, h

def _show_view(left, top):
    """Scroll so that canvas coordinate (left, top) is at the top-left of the window."""
    w, h = _canvas_view_size()
    bbox = canvas.bbox(tk.ALL) or (left, top, left + w, top + h)
    x0, y0 = min(bbox[0] - 10, left), min(bbox[1] - 10, top)
    x1, y1 = max(bbox[2] + 10, left + w), max(bbox[3] + 10, top + h)
    canvas.config(scrollregion=(x0, y0, x1, y1))
    canvas.xview_moveto((left - x0) / (x1 - x0))
    canvas.yview_moveto((top - y0) / (y1 - y0))

def _drawing_bbox():
    """Bounding box of everything except the labels (so labels don't change the fit)."""
    box = None
    for it in canvas.find_all():
        if "label" in canvas.gettags(it):
            continue
        b = canvas.bbox(it)
        if b:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    return box

def fit_view(event=None):
    """Zoom and scroll so the whole drawing fits inside the canvas (canvas size unchanged)."""
    box = _drawing_bbox()
    if box is None:
        return
    w, h = _canvas_view_size()
    margin = 25
    bw, bh = max(box[2] - box[0], 1), max(box[3] - box[1], 1)
    factor = min((w - 2 * margin) / bw, (h - 2 * margin) / bh)
    factor = min(factor, VIEW_ZOOM_MAX / view_zoom)
    if factor > 0 and abs(factor - 1) > 1e-6:
        _apply_zoom(factor)
    box = _drawing_bbox()
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    _show_view(cx - w / 2, cy - h / 2)

def zoom_canvas(event):
    """Mouse wheel on the canvas: zoom in/out around the mouse pointer."""
    factor = 1.2 if event.delta > 0 else 1 / 1.2
    px, py = canvas.canvasx(event.x), canvas.canvasy(event.y)
    left, top = canvas.canvasx(0), canvas.canvasy(0)
    _apply_zoom(factor)
    # keep the point under the mouse where it was (second pass corrects border/scroll rounding)
    new_left, new_top = px * factor - (px - left), py * factor - (py - top)
    _show_view(new_left, new_top)
    err_x = canvas.canvasx(event.x) - px * factor
    err_y = canvas.canvasy(event.y) - py * factor
    if abs(err_x) > 0.5 or abs(err_y) > 0.5:
        _show_view(new_left - err_x, new_top - err_y)

def start_pan(event):
    """Left button pressed on the canvas: allow dragging well past the drawing, then mark."""
    w, h = _canvas_view_size()
    bbox = canvas.bbox(tk.ALL)
    left, top = canvas.canvasx(0), canvas.canvasy(0)
    if bbox:
        # Scroll region = drawing plus one window size of free space on every side
        x0, y0 = min(bbox[0] - w, left), min(bbox[1] - h, top)
        x1, y1 = max(bbox[2] + w, left + w), max(bbox[3] + h, top + h)
        canvas.config(scrollregion=(x0, y0, x1, y1))
    canvas.scan_mark(event.x, event.y)
    canvas.config(cursor="fleur")

def do_pan(event):
    """Drag with the left button: move the view with the mouse (1:1)."""
    canvas.scan_dragto(event.x, event.y, gain=1)

def end_pan(event=None):
    canvas.config(cursor="")

def reset_view_zoom():
    """Called when the canvas is cleared: start again at the default scale."""
    global view_zoom
    view_zoom = 1.0
    _label_offsets.clear()

def visualize_cuboid():
    update_scroll_region()

    # Variables to start point
    start_point = points[0]
    i=0
    j=0
    if len(points) > 1: 
        for k in motion_commands:
          if k == "LIN":
            draw_line(start_point[0], start_point[1], points[i+1][0], points[i+1][1], k)
            start_point = points[i+1]
            i+=1
          elif k == "CIRC":
            # Real arc through start -> via -> end (the via dot below sits on it)
            draw_arc(start_point[0], start_point[1], points_circ[j][0], points_circ[j][1],
                     points_circ[j+1][0], points_circ[j+1][1], k)
            start_point = points_circ[j+1]
            j+=2

    # Draw points
    for point in points:
        draw_point(point[0], point[1])
    # Draw points
    for point in points_circ:
        draw_point(point[0], point[1])

    # Show the whole drawing inside the (fixed-size) canvas
    fit_view()

def draw_output_path():
    """Draw the path written in the output text (all turns, layers and transitions) the way
    Automate draws it: moves in blue with labels and red point dots, transitions in purple
    with a purple via dot. Used when a state is restored (undo/redo, Open Project), because
    the automated drawing is otherwise only made while Automate runs."""
    canvas.delete("all")
    reset_view_zoom()
    update_scroll_region()
    items = pm.parse_krl(output_text.get("1.0", tk.END))
    _, moves3d = pm.path_3d(items)               # same move order, with the transition flags
    pos, k = None, 0
    for item in items:
        if isinstance(item, pm.Ptp):
            pos = item.target.xyz
            continue
        if not isinstance(item, (pm.Lin, pm.Circ)) or pos is None:
            continue
        transition = moves3d[k]['transition']
        k += 1
        end = item.target.xyz
        color = "purple" if transition else "blue"
        if isinstance(item, pm.Lin):
            draw_line(pos[0], pos[1], end[0], end[1], "LIN", color=color)
        else:
            via = item.via.xyz
            draw_arc(pos[0], pos[1], via[0], via[1], end[0], end[1], "CIRC", color=color)
            if transition:
                draw_point(via[0], via[1], "purple")
        if not transition:
            for q in ((pos, end) if isinstance(item, pm.Lin) else (pos, item.via.xyz, end)):
                draw_point(q[0], q[1])
        pos = end
    fit_view()

def redraw_canvas_from_state():
    """Canvas for the current state: the automated path from the output text if there is one,
    otherwise the base loop (preview / manual mode)."""
    if "===== LAYER" in output_text.get("1.0", tk.END):
        draw_output_path()
    elif points:
        visualize_cuboid()

def add_point():
    global points, motion_commands
    # Take snapshot only if inputs are valid; will push after validation
    x_str = x_entry.get()
    y_str = y_entry.get()
    z_str = z_entry.get()
    a_str = a_entry.get()
    b_str = b_entry.get()
    c_str = c_entry.get()

    if not validate_coordinates(x_str, y_str, z_str, a_str , b_str, c_str):
        messagebox.showwarning("Invalid Input", "Please enter valid numerical values for X, Y, and Z coordinates or A, B, and C orientations.")
        return

    # Enforce the 11-point limit before adding anything
    if len(points) + len(points_circ) >= 11:
        messagebox.showwarning("Too Many Points", "You can only enter up to 11 points to form a cuboid.")
        return

    # Snapshot before mutating state
    _push_undo_snapshot()
    global base_params
    base_params = None          # the base is now made / changed by hand
    x = float(x_str)
    y = float(y_str)
    z = float(z_str)
    a = float(a_str)
    b = float(b_str)
    c = float(c_str)

    if len(points) > 0:
       motion_commands.append("LIN")

    points.append((float(x), float(y), float(z)))
    orientations.append((float(a), float(b), float(c)))
    visualize_cuboid()

    if len(points+points_circ) <= 11:
            if len(points) > 1:
                emit_lin((x, y, z), (a, b, c))
            else:
                emit_ptp((x, y, z), (a, b, c))
            if len(points+points_circ) == 11:
                dummy_og_y= ((points[1][1] + points_circ[1][1])/2)
                dummy_final_y = dummy_og_y - (0.3*dummy_og_y)
                dummy_og_x = ((points[0][0] + points[4][0])/2)
                dummy_final_x = dummy_og_x + (0.1*dummy_og_x)
                draw_point(dummy_final_x,dummy_final_y)
                draw_line(points[4][0],points[4][1],dummy_final_x,dummy_final_y,"CIRC")
                draw_line(dummy_final_x,dummy_final_y,points[0][0],points[0][1],"CIRC")
                messagebox.showinfo("Stage 1 Completed!", "Manual Base Cuboid Finished:\n\nNow please enter valid numerical values for \n\n E, W, No. of Turns & No. of Layers to prepare for Automation on your provided base \n\n (Considering your base is as Instructed - Read Instructions).\n\nN.b: If this is not the shape you wish for, Please 'Clear All' and Start Again.")
                print(f"Points: {points}")
                print(f"Points CIRC: {points_circ}")

def input_points_for_circ():
    # Create a pop-up window to input points for CIRC motion command
    popup = tk.Toplevel(root)
    popup.title("Input Points for CIRC Command")

    a = float(a_entry.get())
    b = float(b_entry.get())
    c = float(c_entry.get())

    last_point = points[-1] if points else (0, 0, 0)  # Get the last entered point or (0, 0, 0) if none
    start_x_var = tk.StringVar(value=str(last_point[0]))
    start_y_var = tk.StringVar(value=str(last_point[1]))
    start_z_var = tk.StringVar(value=str(last_point[2]))

    # Labels and entry fields for start point
    start_label = tk.Label(popup, text="Start Point:")
    start_label.grid(row=0, column=0, padx=5, pady=5)
    start_x_label = tk.Label(popup, text="X:")
    start_x_label.grid(row=0, column=1)
    start_x_entry = tk.Entry(popup, textvariable=start_x_var)
    start_x_entry.grid(row=0, column=2)
    start_y_label = tk.Label(popup, text="Y:")
    start_y_label.grid(row=0, column=3)
    start_y_entry = tk.Entry(popup, textvariable=start_y_var)
    start_y_entry.grid(row=0, column=4)
    start_z_label = tk.Label(popup, text="Z:")
    start_z_label.grid(row=0, column=5)
    start_z_entry = tk.Entry(popup, textvariable=start_z_var)
    start_z_entry.grid(row=0, column=6)

    # Labels and entry fields for middle point
    middle_label = tk.Label(popup, text="Middle Point:")
    middle_label.grid(row=1, column=0, padx=5, pady=5)
    middle_x_label = tk.Label(popup, text="X:")
    middle_x_label.grid(row=1, column=1)
    middle_x_entry = tk.Entry(popup)
    middle_x_entry.grid(row=1, column=2)
    middle_y_label = tk.Label(popup, text="Y:")
    middle_y_label.grid(row=1, column=3)
    middle_y_entry = tk.Entry(popup)
    middle_y_entry.grid(row=1, column=4)
    middle_z_label = tk.Label(popup, text="Z:")
    middle_z_label.grid(row=1, column=5)
    middle_z_entry = tk.Entry(popup)
    middle_z_entry.grid(row=1, column=6)

    # Labels and entry fields for end point
    end_label = tk.Label(popup, text="End Point:")
    end_label.grid(row=2, column=0, padx=5, pady=5)
    end_x_label = tk.Label(popup, text="X:")
    end_x_label.grid(row=2, column=1)
    end_x_entry = tk.Entry(popup)
    end_x_entry.grid(row=2, column=2)
    end_y_label = tk.Label(popup, text="Y:")
    end_y_label.grid(row=2, column=3)
    end_y_entry = tk.Entry(popup)
    end_y_entry.grid(row=2, column=4)
    end_z_label = tk.Label(popup, text="Z:")
    end_z_label.grid(row=2, column=5)
    end_z_entry = tk.Entry(popup)
    end_z_entry.grid(row=2, column=6)

    # Function to handle the input
    def ok_click():
        # Snapshot prior to applying changes
        _push_undo_snapshot()
        global base_params
        base_params = None          # the base is changed by hand
        # Get the input values
        middle_x = middle_x_entry.get()
        middle_y = middle_y_entry.get()
        middle_z = middle_z_entry.get()
        end_x = end_x_entry.get()
        end_y = end_y_entry.get()
        end_z = end_z_entry.get()
        # Validate the input
        if middle_x and middle_y and middle_z and end_x and end_y and end_z:
            try:
                # Convert input values to floats
                middle_x = float(middle_x)
                middle_y = float(middle_y)
                middle_z = float(middle_z)
                end_x = float(end_x)
                end_y = float(end_y)
                end_z = float(end_z)
                # Calculate A angle based on curve direction for pen-like movement
                # Get start point (last point in points list)
                if points:
                    start_x = points[-1][0]
                    start_y = points[-1][1]
                else:
                    start_x = 0
                    start_y = 0
                
                # Calculate direction vector
                dx = end_x - start_x
                dy = end_y - start_y
                
                # Use smooth A-angle calculation to avoid large jumps
                A_angle = calculate_smooth_a_angle(dx, dy)
                
                # Generate the KRL code with calculated A, interface B tilt, and interface C
                circ = circ_item((middle_x, middle_y, middle_z), (end_x, end_y, end_z), (a1(A_angle), b, c))
                # Append the KRL code to the output text widget
                points_circ.append((float(middle_x), float(middle_y), float(middle_z)))
                orientations.append((float(a), float(b), float(c)))
                motion_commands.append("CIRC")
                points_circ.append((float(end_x), float(end_y), float(end_z)))
                orientations.append((float(a), float(b), float(c)))
                emit(circ)
                # Close the pop-up window
                popup.destroy()
                # Redraw the cuboid visualization
                visualize_cuboid()
            except ValueError:
                tk.messagebox.showwarning("Invalid Input", "Please enter valid numerical values for coordinates.")
        else:
            # If any of the fields are empty, show a warning message
            tk.messagebox.showwarning("Missing Input", "Please enter values for all points.")

    # Button to confirm the input
    ok_button = tk.Button(popup, text="OK", command=ok_click)
    ok_button.grid(row=3, column=0, columnspan=7)


# Function to handle the selection of motion commands
def select_motion_command(motion_command):
    global selected_motion_command
    selected_motion_command = motion_command
    # If the selected command is CIRC, prompt the user to input points
    if motion_command == "CIRC":
        input_points_for_circ()

def automate():
    global points, points_circ, motion_commands, current_a_angle

    # Validate everything BEFORE touching the current output/state
    if len(points) < 5 or len(points_circ) < 2:
        messagebox.showerror("Input Error", "Please create the 11-point base first (manually, by import, or Auto-Generate Base).")
        return

    e = E_entry.get()
    w = W_entry.get()
    turns = NumberofTurns_entry.get()
    layers = NumberofLayers_entry.get()

    if not e or not w or not turns or not layers:
        messagebox.showerror("Input Error", "Please fill in all the required fields in Automation Options.")
        return

    try:
        e = float(e)
        w = float(w)
        turns = int(turns)
        layers = int(layers)
        a = float(a_entry.get())
        b = float(b_entry.get())
        c = float(c_entry.get())
    except ValueError:
        messagebox.showerror("Input Error", "E and W must be numbers, Turns and Layers must be whole numbers, A/B/C must be numbers.")
        return

    # Read tilt angle (fallback to 10 if invalid)
    try:
        tilt_angle_deg = float(tilt_entry.get())
    except Exception:
        tilt_angle_deg = 10.0
    tilt_angle_deg = max(5.0, min(tilt_angle_deg, 20.0))

    # Inputs OK: one undo snapshot, then clear output (clear_for_auto pushes the snapshot)
    clear_for_auto()

    # Ensure all points are lists
    points = [list(point) for point in points]
    points_circ = [list(point) for point in points_circ]

    # The path comes from cuboid.py (the same code as the main app). This app keeps its old
    # counting: the Turns / Layers entered give N+1 turns / layers.
    items, final_a = cuboid.generate_from_loop(points, points_circ, motion_commands, e, w,
                                               turns + 1, layers + 1, a, b, c, tilt_angle_deg,
                                               tilt_along_travel_var.get())
    current_a_angle = final_a           # the base preview continues from here (as before)
    output_text.insert(tk.END, pm.program_to_krl(items) + "\n")
    draw_output_path()                  # all turns, layers and purple transitions

def clear_for_auto():
    global current_a_angle
    _push_undo_snapshot()
    current_a_angle = 180.0  # Reset A angle to default
    canvas.delete("all")
    reset_view_zoom()
    output_text.delete("1.0", tk.END)

def clear_all():
    global points, points_circ, motion_commands, orientations, current_a_angle, base_params
    _push_undo_snapshot()
    base_params = None
    points = []
    points_circ = []
    motion_commands = []
    orientations = []
    current_a_angle = 180.0  # Reset A angle to default
    canvas.delete("all")
    reset_view_zoom()
    output_text.delete("1.0", tk.END)

def change_center():
    global xc, yc, zc
    # Create a pop-up window to input points for new center
    popup = tk.Toplevel(root)
    popup.title("Input Points for new center")

    # Labels and entry fields for center point
    center_label = tk.Label(popup, text="Center Point:")
    center_label.grid(row=1, column=0, padx=5, pady=5)
    xc_label = tk.Label(popup, text="Xc:")
    xc_label.grid(row=1, column=1)
    xc_entry = tk.Entry(popup)
    xc_entry.grid(row=1, column=2)
    yc_label = tk.Label(popup, text="Yc:")
    yc_label.grid(row=1, column=3)
    yc_entry = tk.Entry(popup)
    yc_entry.grid(row=1, column=4)
    zc_label = tk.Label(popup, text="Zc:")
    zc_label.grid(row=1, column=5)
    zc_entry = tk.Entry(popup)
    zc_entry.grid(row=1, column=6)

    # Function to handle the input
    def ok_click():
        global xc, yc, zc
        # Snapshot prior to applying changes
        _push_undo_snapshot()
        global base_params
        base_params = None          # moved base: the parameters no longer match
        # Get the input values
        xc_str = xc_entry.get()
        yc_str = yc_entry.get()
        zc_str = zc_entry.get()
        # Validate the input
        if xc_str and yc_str and zc_str:
            try:
                # Convert input values to floats
                xc = float(xc_str)
                yc = float(yc_str)
                zc = float(zc_str)

                # Offset all base points once
                for idx in range(len(points)):
                    px, py, pz = points[idx]
                    points[idx] = (px + xc, py + yc, pz + zc)

                # Offset all circ points once (pairs)
                for idx in range(len(points_circ)):
                    px, py, pz = points_circ[idx]
                    points_circ[idx] = (px + xc, py + yc, pz + zc)

                # Close the pop-up window
                popup.destroy()
                # Redraw the cuboid visualization
                clear_for_auto()
                update_krl_code()
                visualize_cuboid()

            except ValueError:
                tk.messagebox.showwarning("Invalid Input", "Please enter valid numerical values for coordinates.")
        else:
            # If any of the fields are empty, show a warning message
            tk.messagebox.showwarning("Missing Input", "Please enter values for all points.")

    # Button to confirm the input
    ok_button = tk.Button(popup, text="OK", command=ok_click)
    ok_button.grid(row=3, column=0, columnspan=7)


def save_krl_code():
    # Get the KRL code (motion lines) from the output text widget
    krl_code = output_text.get("1.0", tk.END)

    # Ask the user to choose the file format
    file_format = file_format_var.get()

    # Set the default extension based on the file format
    if file_format == "KRL (.src)":
        default_extension = ".src"
        filetypes = [("KRL files", "*.src")]
    else:
        default_extension = ".txt"
        filetypes = [("Text files", "*.txt")]

    # Prompt the user to choose the file path for saving
    file_path = filedialog.asksaveasfilename(defaultextension=default_extension, filetypes=filetypes)
    if not file_path:
        return

    # The DEF name is the file name, so it must be a valid KRL identifier
    file_name = os.path.splitext(os.path.basename(file_path))[0]
    if not krl_export.is_valid_program_name(file_name):
        messagebox.showerror(
            "Invalid File Name",
            f"'{file_name}' is not a valid KRL program name.\n\n"
            f"{krl_export.PROGRAM_NAME_RULE}\n\nNothing was saved."
        )
        return

    # Header (BASE/TOOL/speed/approximation) + moves (+ C_DIS unless switched off) + END,
    # all from the shared krl_export module
    settings, profile_error = krl_export.active_settings()
    if profile_error:
        messagebox.showwarning("Export Settings", profile_error)
    full_code = krl_export.build_program(file_name, krl_code, settings, approximate=c_dis_var.get())

    with open(file_path, "w") as file:
        file.write(full_code)

    # Show a message box indicating that the KRL code has been saved
    messagebox.showinfo("KRL Code Exported", "The KRL code has been exported successfully.")

def import_points():
    file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
    if file_path:
        try:
            _push_undo_snapshot()
            global base_params
            base_params = None          # imported base: no Auto-Generate parameters
            points_from_file, points_circ_from_file, orientations_from_file, motion_commands_from_file = read_points_from_file(file_path)
            # Update the global variables with the imported points
            global points, points_circ, orientations, motion_commands
            points = points_from_file
            points_circ = points_circ_from_file
            orientations = orientations_from_file
            motion_commands = motion_commands_from_file 
            messagebox.showinfo("Success", "Points imported successfully!")
            update_krl_code()
            visualize_cuboid()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import points: {e}")

def read_points_from_file(file_path):
    points = []
    orientations = []
    points_circ = []  # For CIRC points as a flat list
    motion_commands = []

    with open(file_path, 'r') as file:
        lines = file.readlines()

        # Parse the origin point (Point 1) from the first non-empty, non-comment line
        origin_index = 0
        while origin_index < len(lines):
            first = lines[origin_index].strip()
            if first and not first.startswith('#'):
                break
            origin_index += 1
        if origin_index >= len(lines):
            raise ValueError("File does not contain an origin line.")

        x, y, z, a, b, c = map(float, lines[origin_index].strip().split())
        points.append((x, y, z))
        orientations.append((a, b, c))

        line_index = origin_index + 1

        while line_index < len(lines):
            raw = lines[line_index].strip()
            if not raw or raw.startswith('#'):
                line_index += 1
                continue
            parts = raw.split()
            if len(parts) == 7 and parts[6] == "LIN":
                # LIN command
                x, y, z, a, b, c = map(float, parts[:6])
                points.append((x, y, z))
                orientations.append((a, b, c))
                motion_commands.append("LIN")
                line_index += 1
            elif len(parts) == 10 and parts[9] == "CIRC":
                # CIRC command
                x1, y1, z1, x2, y2, z2, a1, b1, c1 = map(float, parts[:9])
                points_circ.extend([(x1, y1, z1), (x2, y2, z2)])
                orientations.extend([(a1, b1, c1), (a1, b1, c1)])
                motion_commands.append("CIRC")
                line_index += 1
            else:
                raise ValueError("Invalid format in the points file.")

    return points, points_circ, orientations, motion_commands

def save_points():
    file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
    if file_path:
        try:
            with open(file_path, "w") as file:
                # Save origin point
                origin_x, origin_y, origin_z = points[0]
                origin_a, origin_b, origin_c = orientations[0]
                file.write(f"{origin_x} {origin_y} {origin_z} {origin_a} {origin_b} {origin_c}\n")

                i = 1  # Index for points (starting from the second point)
                j = 0  # Index for points_circ
                o = 1  # Index for orientations (stored in insertion order: LIN = 1 entry, CIRC = 2 entries)

                # Save remaining points and motion commands
                for k in motion_commands:
                    if k == "LIN":
                        x, y, z = points[i]
                        a, b, c = orientations[o]
                        file.write(f"{x} {y} {z} {a} {b} {c} LIN\n")
                        i += 1
                        o += 1
                    elif k == "CIRC":
                        x1, y1, z1 = points_circ[j]
                        x2, y2, z2 = points_circ[j + 1]
                        a1, b1, c1 = orientations[o + 1]  # Orientation of the CIRC end point
                        file.write(f"{x1} {y1} {z1} {x2} {y2} {z2} {a1} {b1} {c1} CIRC\n")
                        j += 2  # Move to the next pair of points in points_circ
                        o += 2

            messagebox.showinfo("Success", "Points saved successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save points: {e}")

# Function to create a popup window for user input
def open_commentary_popup():
    # Create a new top-level window (popup)
    popup = tk.Toplevel(root)
    popup.title("Enter Your Comment")

    # Create a label and an entry widget for user input
    label = tk.Label(popup, text="Enter your comment:")
    label.pack(padx=10, pady=5)

    comment_entry = tk.Entry(popup, width=40)
    comment_entry.pack(padx=10, pady=5)

    # Function to handle the submission of the comment
    def submit_comment():
        comment = comment_entry.get()
        if comment:
            emit_comment(comment)
        popup.destroy()  # Close the popup after submission

    # Create a submit button
    submit_button = tk.Button(popup, text="Submit", command=submit_comment)
    submit_button.pack(pady=10)

# Function to create a popup window for user input
def open_approach_popup():
    global xa, ya, za, aa, ba, ca
    # Create a new top-level window (popup)
    popup = tk.Toplevel(root)
    popup.title("Input Points for Approach Point")

    # Labels and entry fields for approach point
    center_label = tk.Label(popup, text="Approach Point:")
    center_label.grid(row=1, column=0, padx=5, pady=5)
    xa_label = tk.Label(popup, text="Xa:")
    xa_label.grid(row=1, column=1)
    xa_entry = tk.Entry(popup)
    xa_entry.grid(row=1, column=2)
    ya_label = tk.Label(popup, text="Ya:")
    ya_label.grid(row=1, column=3)
    ya_entry = tk.Entry(popup)
    ya_entry.grid(row=1, column=4)
    za_label = tk.Label(popup, text="Za:")
    za_label.grid(row=1, column=5)
    za_entry = tk.Entry(popup)
    za_entry.grid(row=1, column=6)
    aa_label = tk.Label(popup, text="Aa:")
    aa_label.grid(row=2, column=1)
    aa_entry = tk.Entry(popup)
    aa_entry.grid(row=2, column=2)
    ba_label = tk.Label(popup, text="Ba:")
    ba_label.grid(row=2, column=3)
    ba_entry = tk.Entry(popup)
    ba_entry.grid(row=2, column=4)
    ca_label = tk.Label(popup, text="Ca:")
    ca_label.grid(row=2, column=5)
    ca_entry = tk.Entry(popup)
    ca_entry.grid(row=2, column=6)

    # Function to handle the submission of the comment
    def submit_approach():
            global xa, ya, za, aa, ba, ca
            # Get the input values
            xa = xa_entry.get()
            ya = ya_entry.get()
            za = za_entry.get()
            aa = aa_entry.get()
            ba = ba_entry.get()
            ca = ca_entry.get()
            if xa and ya and za and aa and ba and ca:
                try:
                    # Convert input values to floats
                    xa = float(xa)
                    ya = float(ya)
                    za = float(za)
                    aa = float(aa)
                    ba = float(ba)
                    ca = float(ca)
                    emit_ptp((xa, ya, za), (aa, ba, ca))
                    popup.destroy()  # Close the popup after submission

                except ValueError:
                    tk.messagebox.showwarning("Invalid Input", "Please enter valid numerical values for coordinates.")
            else:
                # If any of the fields are empty, show a warning message
                tk.messagebox.showwarning("Missing Input", "Please enter values for all points.")
    # Create a submit button
    submit_button = tk.Button(popup, text="Submit", command=submit_approach)
    submit_button.grid(row=3, column=0, columnspan=7, pady=10)


def open_generate_popup():
    popup = tk.Toplevel(root)
    popup.title("Generate Cuboid from Dimensions")

    # Labels & entries
    tk.Label(popup, text="Center Xr:").grid(row=0, column=0, padx=20)
    xr_entry = tk.Entry(popup); xr_entry.grid(row=0, column=1, padx=50, pady=30)
    xr_entry.insert(0, generate_popup_values["Xr"])

    tk.Label(popup, text="Center Yr:").grid(row=1, column=0, padx=20)
    yr_entry = tk.Entry(popup); yr_entry.grid(row=1, column=1, padx=50, pady=30)
    yr_entry.insert(0, generate_popup_values["Yr"])

    tk.Label(popup, text="Center Zr:").grid(row=2, column=0, padx=20)
    zr_entry = tk.Entry(popup); zr_entry.grid(row=2, column=1, padx=50, pady=30)
    zr_entry.insert(0, generate_popup_values["Zr"])

    tk.Label(popup, text="Cuboid Length (X):").grid(row=3, column=0, padx=20)
    length_entry = tk.Entry(popup); length_entry.grid(row=3, column=1, padx=50, pady=30)

    tk.Label(popup, text="Cuboid Width (Y):").grid(row=4, column=0, padx=20)
    width_entry  = tk.Entry(popup); width_entry.grid(row=4, column=1, padx=50, pady=30)

    tk.Label(popup, text="Tool Height (Z offset):").grid(row=5, column=0, padx=20)
    th_entry     = tk.Entry(popup); th_entry.grid(row=5, column=1, padx=50, pady=30)

    tk.Label(popup, text="Corner Radius (blank = auto):").grid(row=6, column=0, padx=20)
    radius_entry = tk.Entry(popup); radius_entry.grid(row=6, column=1, padx=50, pady=30)
    # Pre-fill with the last values used (or the ones from an opened project)
    for entry, key in ((length_entry, "L"), (width_entry, "W"), (th_entry, "Th"), (radius_entry, "r")):
        entry.insert(0, generate_popup_values[key])

    def generate_points():
        global points, points_circ, motion_commands, orientations, base_params
        try:
            Xr = float(xr_entry.get())
            Yr = float(yr_entry.get())
            Zr = float(zr_entry.get())
            L  = float(length_entry.get())
            W  = float(width_entry.get())
            Th = float(th_entry.get())
            r_text = radius_entry.get().strip()
            r = float(r_text) if r_text else None
        except ValueError:
            messagebox.showerror("Input Error", "Please enter valid numbers")
            return
        if L <= 0 or W <= 0:
            messagebox.showerror("Input Error", "Length and width must be greater than 0.")
            return

        # Corner radius: given, or automatic (15% of the shorter side, clamped to [2, min/3])
        if r is None:
            r = shapes.auto_corner_radius(L, W)
        r_max = min(L, W) / 2
        if not (0 < r <= r_max):
            messagebox.showerror(
                "Input Error",
                f"Corner radius must be greater than 0 and at most half the shorter side "
                f"({r_max:g} mm).\n\nUsed radius: {r:g} mm.")
            return

        Z = Zr + Th
        A, B, C = 180.0, 0.0, 180.0

        # Clear everything (this takes the one undo snapshot), then build the base loop
        clear_all()
        points, points_circ, motion_commands = shapes.rounded_rect_base(Xr, Yr, Z, L, W, r)
        orientations = [(A, B, C)] * (len(points) + len(points_circ))
        base_params = {"Xr": Xr, "Yr": Yr, "Zr": Zr, "L": L, "W": W, "Th": Th, "r": r,
                       "r_auto": not r_text}
        generate_popup_values.update({"Xr": xr_entry.get(), "Yr": yr_entry.get(), "Zr": zr_entry.get(),
                                      "L": length_entry.get(), "W": width_entry.get(),
                                      "Th": th_entry.get(), "r": r_text})

        # Preview: PTP P1, then the base moves in order (LIN / CIRC)
        emit_ptp(points[0], (A, B, C))
        i, j = 1, 0
        for k in motion_commands:
            if k == "LIN":
                emit_lin(points[i], (A, B, C))
                i += 1
            else:
                emit_circ(points_circ[j], points_circ[j + 1], (A, B, C))
                j += 2

        popup.destroy()
        visualize_cuboid()

    tk.Button(popup, text="Generate", command=generate_points).grid(row=7, column=0, columnspan=2, pady=10)


def instructions():

    messagebox.showinfo("How to create base cuboid?", "To automate the process: \n\nStage 1: In the first stage, You need to create a base cuboid using only X, Y, Z, A, B, C fields consisting of 11 points (maximum) with their orientations.\nRead 'Points Order Instructions' for more details.\n\nStage 2: In this stage we will use 'Automation Options'.\nThe program will increment E and W values you provide to a formula to draw more turns and layers to the existing base. \nIt will stop at the limit you specify in the No. of Turns and No. of Layers Fields.\n\nNote:\nYou have the ability to change the center of your 11 points by specifying where the relative position of your center in the form of (Xc, Yc, Zc) through the 'Change Center' button.\nThis button can only be used after adding the base 11 points, shifting them to their new co-ordinates.\n(Start Point on KUKA is X 745 Y 10 Z 125)\n\nIf you want to add a comment, You can use'Add Commentary' Button, This button is only used for comments so it adds ; symbol at the begininng of the comment to avoid modifications and errors to the output code.")

def pt_instructions():

    messagebox.showinfo("How to order your points?", "To create a good base/cuboid you need to: \n\nPoint 1>>Start with Origin Point (Ex.:(0,0,0)).\n\nPoint 2>>Continue to create your 'upper-edge' of the cuboid by incrementing only X-coordinate (Ex.:(50,0,0)).\n\nPoint3 & 4>> Create a CIRC which represents the 'upper right corner' and consists of inputing two extra points in addition to your last point provided (Ex.:(50,0,0)(60,10,0)(70,30,0)).\n\nPoint 5>>Create your 'right-edge' of the cuboid by incrementing only Y-coordinate (Ex.:(70,80,0)).\n\nPoint 6 & 7>>Create another CIRC which represents the 'lower-right-corner' (Ex.:(70,80,0)(60,100,0)(50,110,0)).\n\nPoint 8>>Create your 'bottom-edge' of the cuboid by decrementing only X-coordinate (Ex.:(0,110,0)).\n\nPoint 9 & 10>>Create the final CIRC which represents the 'lower-left-corner' (Ex.:(0,110,0)(-10,100,0)(-20,80,0)).\n\nPoint11>>Create your final 'left-edge' of the cuboid by decrementing only Y-coordinate (Ex.:(-20,30,0)).\n\n(Please note that: Y-axis is inversed in this version of the application, also note that orientations values will be included.)")

def import_instructions():

    messagebox.showinfo("How to import external points?", "To import external points from an external file rather than inputing them 1 by 1 through the program, you will click on the 'Import Points' button and select a Text File (.txt) where all of your 11 points are saved.\n\nPlease follow the format in the example below in your text file to avoid any errors:\nFormat: {X Y Z A B C Motion_command}\n\n0.0 0.0 125.0 180.0 0.0 180.0\n50.0 0.0 125.0 180.0 0.0 180.0 LIN\n60.0 10.0 125.0 70.0 30.0 125.0 180.0 0.0 180.0 CIRC\n70.0 80.0 125.0 180.0 0.0 180.0 LIN\n60.0 100.0 125.0 50.0 110.0 125.0 180.0 0.0 180.0 CIRC\n0.0 110.0 125.0 180.0 0.0 180.0 LIN\n-10.0 100.0 125.0 -20.0 80.0 125.0 180.0 0.0 180.0 CIRC\n-20.0 30.0 125.0 180.0 0.0 180.0 LIN\n\nN.b: You can create your desired cuboid once through the program and then use the 'Save Points' button which saves the 11 points with their orientations in a text file (.txt) with the desired format mentioned above.\n\nThis file can then be imported later to be used through the program.")

def automation_instructions():

    messagebox.showinfo(
        "How does Automation Functions work?",
        "Options explained:\n\n"
        "Auto-Orient Along Travel: When enabled, the tool follows the path like a pen:\n"
        "• A = direction of travel of the next edge (updated at each corner CIRC)\n"
        "• LIN moves keep the current A (no rotation along straight edges)\n"
        "• B = Tilt Angle (clamped to 5–20°)\n"
        "• C = interface C value\n"
        "Tilt angle can be set near the Functions menu. Disable to use your own A/B/C\n"
        "for every LIN and CIRC.\n\n"
        "Tips:\n"
        "• Use tilt angle 10-20° for best results\n"
        "• Use small E (filament thickness) to avoid over-extrusion\n"
        "• Keep base path consistent (LIN/CIRC order) for best automation"
    )

# =====================================================================================
# 3D VIEW: shared module view3d.py (the same window is used by the cylinder app)
# =====================================================================================
def open_3d_view(event=None):
    """Open the 3D view window (or bring it to the front and reload it)."""
    view3d.open_view(root, lambda: output_text.get("1.0", tk.END),
                     "Nothing to show yet. Generate a base or run Automate first.")


root = tk.Tk()
root.title("Cuboidal KRL Code Generator")

# =====================================================================================
# PROJECT FILES (project_files.py): all inputs + the output, to reproduce a print
# =====================================================================================
def _project_entries():
    return {"X": x_entry, "Y": y_entry, "Z": z_entry, "A": a_entry, "B": b_entry, "C": c_entry,
            "E": E_entry, "W": W_entry, "turns": NumberofTurns_entry, "layers": NumberofLayers_entry,
            "tilt": tilt_entry}

def project_data():
    return {
        "base": {"points": [list(p) for p in points], "points_circ": [list(p) for p in points_circ],
                 "motion_commands": list(motion_commands), "orientations": [list(o) for o in orientations]},
        "base_params": copy.deepcopy(base_params),
        "generate_popup": dict(generate_popup_values),
        "entries": {k: e.get() for k, e in _project_entries().items()},
        "options": {"auto_orient": tilt_along_travel_var.get(), "c_dis": c_dis_var.get()},
        "current_a_angle": current_a_angle,
        "output": output_text.get("1.0", "end-1c"),
    }

def save_project(event=None):
    path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=project_files.FILETYPES,
                                        title="Save Project")
    if path:
        save_project_to(path)

def save_project_to(path):
    try:
        project_files.save_project(path, "cuboid", project_data())
    except OSError as ex:
        messagebox.showerror("Save Project", f"Could not save the project:\n{ex}")
        return False
    return True

def open_project(event=None):
    path = filedialog.askopenfilename(filetypes=project_files.FILETYPES, title="Open Project")
    if path:
        open_project_from(path)

def open_project_from(path):
    """Restore base, parameters, fields and options. If the project was automated, Automate
    runs again; if its result differs from the SAVED output (hand edits or a program change),
    the saved output is kept. Undo returns to the state before opening."""
    global points, points_circ, motion_commands, orientations, current_a_angle, base_params
    try:
        data = project_files.load_project(path, "cuboid")
        base = data.get("base", {})
        new_points = [tuple(float(v) for v in p) for p in base.get("points", [])]
        new_circ = [tuple(float(v) for v in p) for p in base.get("points_circ", [])]
        new_mc = [str(m) for m in base.get("motion_commands", [])]
        new_ori = [tuple(float(v) for v in o) for o in base.get("orientations", [])]
        if any(m not in ("LIN", "CIRC") for m in new_mc) or \
                (new_points and len(new_points) != 1 + new_mc.count("LIN")) or \
                len(new_circ) != 2 * new_mc.count("CIRC") or any(len(p) != 3 for p in new_points + new_circ):
            raise project_files.ProjectError("The base loop in the project file is inconsistent.")
    except project_files.ProjectError as ex:
        messagebox.showerror("Open Project", str(ex))
        return False
    except (TypeError, ValueError) as ex:
        messagebox.showerror("Open Project", f"The project file is damaged:\n{ex}")
        return False

    _push_undo_snapshot()
    points, points_circ, motion_commands, orientations = new_points, new_circ, new_mc, new_ori
    current_a_angle = float(data.get("current_a_angle", 180.0))
    base_params = data.get("base_params")
    generate_popup_values.update({k: str(v) for k, v in data.get("generate_popup", {}).items()
                                  if k in generate_popup_values})
    for key, entry in _project_entries().items():
        if key in data.get("entries", {}):
            entry.delete(0, tk.END)
            entry.insert(0, str(data["entries"][key]))
    opts = data.get("options", {})
    tilt_along_travel_var.set(bool(opts.get("auto_orient", True)))
    c_dis_var.set(bool(opts.get("c_dis", True)))

    saved = data.get("output", "")
    canvas.delete("all")
    reset_view_zoom()
    output_text.delete("1.0", tk.END)
    output_text.insert("1.0", saved)
    redraw_canvas_from_state()
    entries = data.get("entries", {})
    if "===== LAYER" in saved and all(str(entries.get(k, "")).strip() for k in ("E", "W", "turns", "layers")):
        last_snapshot = undo_history[-1] if undo_history else None
        automate()                      # regenerates the turns and draws them
        if undo_history and undo_history[-1] is not last_snapshot:
            undo_history.pop()          # Open + regeneration = ONE undo step
        if output_text.get("1.0", "end-1c") != saved:
            output_text.delete("1.0", tk.END)
            output_text.insert("1.0", saved)
            draw_output_path()          # the canvas must show the SAVED path, not the regenerated one
            messagebox.showinfo("Open Project",
                                "The saved output differs from what this version generates "
                                "(hand edits, or a program change).\n\nThe SAVED output was kept. "
                                "Press Automate to regenerate it from the inputs.")
    warning = project_files.profile_mismatch(data)
    if warning:
        messagebox.showwarning("Open Project", warning)
    return True

def go_back_to_selector():
    """Back: close this editor. Opened from the main app (--from-main): that app is still
    open, so just close. Started on its own: start the main app (KRL_Generator.py)."""
    try:
        if "--from-main" not in sys.argv:
            main_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "KRL_Generator.py")
            if os.path.exists(main_script):
                subprocess.Popen([sys.executable, main_script])
            else:
                messagebox.showwarning("Not Found", "KRL_Generator.py was not found.")
    except Exception as ex:
        messagebox.showerror("Error", f"Failed to open the main app: {ex}")
    finally:
        root.destroy()

# Top-level notebook with Main and Help tabs
root.grid_rowconfigure(0, weight=1)
root.grid_columnconfigure(0, weight=1)
top_notebook = ttk.Notebook(root)
main_tab = ttk.Frame(top_notebook)
help_tab = ttk.Frame(top_notebook)
top_notebook.add(main_tab, text="Main")
top_notebook.add(help_tab, text="Help")
top_notebook.grid(row=0, column=0, sticky="nsew")

# Default values - Optimized for comfortable robot operation
default_x = 685
default_y = 25
default_increment = 0
default_ori = 180
tool_z = 50  # Comfortable working height relative to optimized base

# Back button at far left; title centered above X/Y/Z/A/B/C (columns 0–3)
back_btn = tk.Button(main_tab, text="← Back", command=go_back_to_selector)
back_btn.grid(row=0, column=0, sticky="w", padx=(0, 10))

# Make columns 1–3 expand so the label centers over inputs
for col_idx in (1, 2, 3):
    try:
        main_tab.grid_columnconfigure(col_idx, weight=1)
    except Exception:
        pass

input_label = tk.Label(main_tab, text="Enter 11 points (Maximum) to form a cuboid:")
input_label.grid(row=0, column=1, columnspan=3, sticky="n")

# Input fields for X, Y, Z coordinates & A, B , C orientations
x_label = tk.Label(main_tab, text="X:")
x_label.grid(row=1, column=0)
x_entry = tk.Entry(main_tab)
x_entry.insert(0, default_x)
x_entry.grid(row=1, column=1)

y_label = tk.Label(main_tab, text="Y:")
y_label.grid(row=2, column=0)
y_entry = tk.Entry(main_tab)
y_entry.insert(0, default_y)
y_entry.grid(row=2, column=1)

z_label = tk.Label(main_tab, text="Z:")
z_label.grid(row=3, column=0)
z_entry = tk.Entry(main_tab)
z_entry.insert(0, tool_z)
z_entry.grid(row=3, column=1)

a_label = tk.Label(main_tab, text="A:")
a_label.grid(row=1, column=2)
a_entry = tk.Entry(main_tab)
a_entry.insert(0, default_ori)
a_entry.grid(row=1, column=3)

b_label = tk.Label(main_tab, text="B:")
b_label.grid(row=2, column=2)
b_entry = tk.Entry(main_tab)
b_entry.insert(0, default_increment)
b_entry.grid(row=2, column=3)

c_label = tk.Label(main_tab, text="C:")
c_label.grid(row=3, column=2)
c_entry = tk.Entry(main_tab)
c_entry.insert(0, default_ori)
c_entry.grid(row=3, column=3)

# Styled Functions dropdown (ttk menubutton + configured menu)
functions_style = ttk.Style()
functions_style.configure("Functions.TMenubutton", padding=(10, 6), relief="raised", borderwidth=1)
try:
    functions_style.configure("Functions.TMenubutton", background="#f7f7f7")
    functions_style.map(
        "Functions.TMenubutton",
        background=[('active', '#e6f2ff'), ('pressed', '#d9eaff'), ('!active', '#f7f7f7')],
        relief=[('pressed', 'sunken'), ('!pressed', 'raised')]
    )
except Exception:
    pass

tilt_along_travel_var = tk.BooleanVar(value=True)
tilt_angle_var = tk.DoubleVar(value=10.0)
# Approximation on export: adds C_DIS to LIN/CIRC so the robot does not stop at every point
c_dis_var = tk.BooleanVar(value=True)

functions_mbtn = ttk.Menubutton(main_tab, text="Functions", style="Functions.TMenubutton")
functions_menu = tk.Menu(functions_mbtn, tearoff=False)

# Menu aesthetics (font, colors, border)
try:
    functions_menu.configure(font=("Segoe UI", 10), background="#ffffff", foreground="#000000",
                             activebackground="#e6f2ff", activeforeground="#000000", borderwidth=1, relief="solid")
except Exception:
    pass

functions_menu.add_checkbutton(label="Auto-Orient Along Travel (With Tilt Angle)", onvalue=True, offvalue=False,
                               variable=tilt_along_travel_var)
functions_menu.add_separator()
functions_menu.add_checkbutton(label="Approximate Moves on Export (C_DIS)", onvalue=True, offvalue=False,
                               variable=c_dis_var)
functions_menu.add_separator()
functions_menu.add_command(label="Add Approach\t (Ctrl+Shift+A)", command=open_approach_popup)
functions_menu.add_separator()
functions_menu.add_command(label="Change Center\t (Ctrl+Shift+C)", command=change_center)
functions_menu.add_separator()
functions_menu.add_command(label="Auto‑Generate Base\t (Ctrl+Shift+G)", command=open_generate_popup)
functions_menu.add_separator()
functions_menu.add_command(label="Fit Canvas to Drawing\t (double-click canvas)", command=fit_view)
functions_menu.add_separator()
functions_menu.add_command(label="3D View\t (Ctrl+Shift+D)", command=open_3d_view)
functions_menu.add_separator()
functions_menu.add_command(label="Open Project...\t (Ctrl+Shift+O)", command=open_project)
functions_menu.add_command(label="Save Project...\t (Ctrl+Shift+S)", command=save_project)
functions_menu.add_separator()
functions_menu.add_command(label="Export Settings (TOOL/BASE profiles)...",
                           command=lambda: export_settings_dialog.open_dialog(root))

functions_mbtn.configure(menu=functions_menu)
functions_mbtn.grid(row=8, column=4, padx=10, pady=8, sticky="ew")

# Compact Undo/Redo icon buttons next to Functions
undo_icon_btn = tk.Button(main_tab, text="↺", width=3, command=undo_action)
undo_icon_btn.grid(row=8, column=5, padx=(0, 4), pady=8, sticky="w")
redo_icon_btn = tk.Button(main_tab, text="↻", width=3, command=redo_action)
redo_icon_btn.grid(row=8, column=6, padx=(0, 10), pady=8, sticky="w")

# Keyboard shortcuts (accelerators shown in menu)
root.bind_all("<Control-Shift-A>", lambda e: open_approach_popup())
root.bind_all("<Control-Shift-C>", lambda e: change_center())
root.bind_all("<Control-Shift-G>", lambda e: open_generate_popup())
root.bind_all("<Control-Shift-D>", open_3d_view)
root.bind_all("<Control-Shift-O>", open_project)
root.bind_all("<Control-Shift-S>", save_project)

## Remove inline help notebook; we will use top-level Help tab

motion_label = tk.Label(main_tab, text="_____________________________________________________________________________________________________________")
motion_label.grid(row=4, column=0, columnspan=4)

# Label specifying the default motion command
motion_label = tk.Label(main_tab, text="Automation Options")
motion_label.grid(row=5, column=0, columnspan=4)

# Add entry fields and buttons to the GUI

E_label = tk.Label(main_tab, text="Filament Thickness (E):")
E_label.grid(row=6, column=0)
E_entry = tk.Entry(main_tab)
E_entry.grid(row=6, column=1)

W_label = tk.Label(main_tab, text="Filament Width (W):")
W_label.grid(row=6, column=2)
W_entry = tk.Entry(main_tab)
W_entry.grid(row=6, column=3)

NumberofTurns_label = tk.Label(main_tab, text="Number of Turns:")
NumberofTurns_label.grid(row=7, column=0)
NumberofTurns_entry = tk.Entry(main_tab)
NumberofTurns_entry.grid(row=7, column=1)

NumberofLayers_label = tk.Label(main_tab, text="Number of Layers:")
NumberofLayers_label.grid(row=7, column=2)
NumberofLayers_entry = tk.Entry(main_tab)
NumberofLayers_entry.grid(row=7, column=3)

# Simple Tilt controls (inline, lightweight)
tilt_container = tk.Frame(main_tab)
tilt_container.grid(row=6, column=4, columnspan=4, sticky="n", pady=(0, 0))
tilt_frame = tk.Frame(tilt_container)
tilt_frame.pack()
tilt_label = tk.Label(tilt_frame, text="Tilt Angle (°) :")
tilt_label.pack(side="left", padx=(0, 6))
tilt_entry = tk.Entry(tilt_frame, width=6)
tilt_entry.insert(0, "20")
tilt_entry.pack(side="left")

add_button = tk.Button(main_tab, text="Add Point", command=add_point)
add_button.grid(row=8, column=0, sticky="ew", padx=30, pady=20)

circ_button = tk.Button(main_tab, text="CIRC", command=lambda: select_motion_command("CIRC"))
circ_button.grid(row=8, column=1, sticky="ew", padx=30, pady=20)

clear_button = tk.Button(main_tab, text="Clear All", command=clear_all)
clear_button.grid(row=8, column=2, sticky="ew", padx=30, pady=20)

auto_button = tk.Button(main_tab, text="Automate", command=automate)
auto_button.grid(row=8, column=3, sticky="ew", padx=30, pady=20)

output_text = tk.Text(main_tab, height=10, width=80)
output_text.grid(row=9, column=0, columnspan=4, padx=20)

export_button = tk.Button(main_tab, text="Export KRL Code", command=save_krl_code)
export_button.grid(row=11, column=0, columnspan=4, pady=10)

import_button = tk.Button(main_tab, text="Import Points", command=import_points)
import_button.grid(row=10, column=4)

save_button = tk.Button(main_tab, text="Save Points", command=save_points)
save_button.grid(row=9, column=4, pady=10)

# Create a button to open the commentary popup
commentary_button = tk.Button(main_tab, text="Add Commentary", command=open_commentary_popup)
commentary_button.grid(row=10, column=3, pady=10)

# Keyboard shortcuts for undo/redo
root.bind_all("<Control-z>", undo_action)
root.bind_all("<Control-y>", redo_action)

# Removed standalone Add Approach button (moved into Functions menu)

# Create a variable to store the selected file format
file_format_var = tk.StringVar(value="KRL (.src)")

# Radio buttons for selecting file format
src_radio = tk.Radiobutton(main_tab, text="KRL (.src)", variable=file_format_var, value="KRL (.src)")
src_radio.grid(row=10, column=1, sticky="w")

txt_radio = tk.Radiobutton(main_tab, text="Text (.txt)", variable=file_format_var, value="Text (.txt)")
txt_radio.grid(row=10, column=2, sticky="w")

canvas_label = tk.Label(main_tab, text="Canvas For Visual Representation")
canvas_label.grid(row=0, column=4, columnspan=4)

canvas = tk.Canvas(main_tab, width=canvas_width, height=canvas_height, bg="white")
canvas.grid(row=1, rowspan=3, column=4, padx=10, pady=10)

# Add a vertical scrollbar
v_scrollbar = tk.Scrollbar(main_tab, orient=tk.VERTICAL, command=canvas.yview)
v_scrollbar.grid(row=1, rowspan=3, column=5, sticky='ns')

# Add a horizontal scrollbar
h_scrollbar = tk.Scrollbar(main_tab, orient=tk.HORIZONTAL, command=canvas.xview)
h_scrollbar.grid(row=4, column=4, sticky='ew')

# Configure the canvas to use the scrollbars
canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

# Canvas navigation: wheel zooms around the pointer, left-drag moves the view,
# double-click fits the whole drawing
canvas.bind("<MouseWheel>", zoom_canvas)
canvas.bind("<ButtonPress-1>", start_pan)
canvas.bind("<B1-Motion>", do_pan)
canvas.bind("<ButtonRelease-1>", end_pan)
canvas.bind("<Double-Button-1>", fit_view)

# Removed standalone Alternate Layer Direction checkbox (moved into Functions menu)

# Removed standalone Auto‑Generate Base button (moved into Functions menu)

# Populate the top-level Help tab with centered instruction buttons
help_container = tk.Frame(help_tab)
help_container.place(relx=0.5, rely=0.5, anchor='center')

btn_general = tk.Button(help_container, text="General Instructions", command=instructions, width=56)
btn_general.pack(fill='x', padx=20, pady=50)

btn_points = tk.Button(help_container, text="Points Order Instructions", command=pt_instructions, width=56)
btn_points.pack(fill='x', padx=20, pady=50)

btn_import = tk.Button(help_container, text="Import/Save Instructions", command=import_instructions, width=56)
btn_import.pack(fill='x', padx=20, pady=50)

btn_automation = tk.Button(help_container, text="Automation Functions Instructions", command=automation_instructions, width=56)
btn_automation.pack(fill='x', padx=20, pady=50)

## Tools tab content removed (Undo/Redo moved to Functions menu)

# Started with a project file (the main app opens hand-made cuboid bases here)
_project_args = [a for a in sys.argv[1:] if a.lower().endswith(".json") and os.path.isfile(a)]
if _project_args:
    root.after(200, lambda: open_project_from(_project_args[0]))

root.mainloop()