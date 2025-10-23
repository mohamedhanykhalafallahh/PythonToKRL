import tkinter as tk
from tkinter import messagebox, filedialog
from tkinter import ttk
import copy
import math
import sys
import os
import subprocess

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

# Initial scaling factor
scaling_factor = 3

# Global variable to track A-axis orientation for smooth transitions
current_a_angle = 180.0   # Current A angle

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
        'output_text': output_text.get("1.0", tk.END)
    }

def _restore_state(snap):
    global points, points_circ, motion_commands, orientations
    points = copy.deepcopy(snap['points'])
    points_circ = copy.deepcopy(snap['points_circ'])
    motion_commands = copy.deepcopy(snap['motion_commands'])
    orientations = copy.deepcopy(snap['orientations'])
    canvas.delete("all")
    output_text.delete("1.0", tk.END)
    output_text.insert(tk.END, snap['output_text'])
    visualize_cuboid()

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

def calculate_transition_a_angle(dx, dy):
    """Calculate exact A-angle for transitions and update global current_a_angle"""
    global current_a_angle
    
    # Calculate exact angle based on movement direction
    target_angle = math.degrees(math.atan2(dy, dx))
    target_angle = normalize_angle(target_angle)
    
    # Update global current_a_angle so LIN movements can follow
    current_a_angle = target_angle
    
    return current_a_angle


def generate_krl_code(points, motion_commands, points_circ, orientations, a, b, c, tilt_angle_deg):
    krl_code = ""

    # Guard against empty input
    if not points:
        return krl_code

    # Handle the origin point separately - use interface values for PTP start
    origin_point = points[0]
    krl_code += f"PTP {{X {origin_point[0]}, Y {origin_point[1]}, Z {origin_point[2]}, A {a}, B {tilt_angle_deg}, C {c}, S 2., T 43.}}\n"

    i = 1
    j = 0

    for k in motion_commands:
        if k == "LIN":
            # Keep A-angle constant from previous movement (no rotation during LIN)
            lin_a = get_current_a_angle()  # Use current A-angle without change
            krl_code += f"LIN {{X {points[i][0]}, Y {points[i][1]}, Z {points[i][2]}, A {lin_a:.1f}, B {tilt_angle_deg}, C {c}}}\n"
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
            krl_code += f"CIRC {{X {points_circ[j][0]}, Y {points_circ[j][1]}, Z {points_circ[j][2]}}},{{X {points_circ[j + 1][0]}, Y {points_circ[j + 1][1]}, Z {points_circ[j + 1][2]}, A {A_angle:.1f}, B {tilt_angle_deg}, C {c}}}\n"
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

def draw_point(x, y, color="red"):
    # Apply scaling factor to the coordinates (invert Y for canvas)
    scaled_x = x * scaling_factor
    scaled_y = -y * scaling_factor
    
    # Draw a point on the canvas
    canvas.create_oval(scaled_x - 2, scaled_y - 2, scaled_x + 2, scaled_y + 2, fill=color)
    update_scroll_region()

def draw_line(x1, y1, x2, y2, motion_command):
    # Apply scaling factor to the coordinates (invert Y for canvas)
    scaled_x1 = x1 * scaling_factor
    scaled_y1 = -y1 * scaling_factor
    scaled_x2 = x2 * scaling_factor
    scaled_y2 = -y2 * scaling_factor
    
    # Draw a line between two points on the canvas
    canvas.create_line(scaled_x1, scaled_y1, scaled_x2, scaled_y2, fill="blue")
    
    # Calculate the midpoint of the line
    midpoint_x = (scaled_x1 + scaled_x2) / 2
    midpoint_y = (scaled_y1 + scaled_y2) / 2
    
    # Display the motion command type above the line
    canvas.create_text(midpoint_x, midpoint_y, text=motion_command, fill="black", anchor='n')

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
            draw_line(start_point[0], start_point[1], points_circ[j][0], points_circ[j][1], k)
            draw_line(points_circ[j][0], points_circ[j][1], points_circ[j+1][0], points_circ[j+1][1], k)
            start_point = points_circ[j+1]
            j+=2

    # Draw points
    for point in points:
        draw_point(point[0], point[1])
    # Draw points
    for point in points_circ:
        draw_point(point[0], point[1])

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

    # Snapshot before mutating state
    _push_undo_snapshot()
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
                output_text.insert(tk.END, f"LIN {{X {x}, Y {y}, Z {z}, A {a}, B {b}, C {c}}}\n")
            else:
                output_text.insert(tk.END, f"PTP {{X {x}, Y {y}, Z {z}, A {a}, B {b}, C {c}, S 2., T 43.}}\n")
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
    else:
        messagebox.showwarning("Too Many Points", "You can only enter up to 11 points to form a cuboid.")

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
                krl_code = f"CIRC {{X {middle_x}, Y {middle_y}, Z {middle_z}}},{{X {end_x}, Y {end_y}, Z {end_z}, A {A_angle:.1f}, B {b}, C {c}}}\n"
                # Append the KRL code to the output text widget
                points_circ.append((float(middle_x), float(middle_y), float(middle_z)))
                orientations.append((float(a), float(b), float(c)))
                motion_commands.append("CIRC")
                points_circ.append((float(end_x), float(end_y), float(end_z)))
                orientations.append((float(a), float(b), float(c)))
                output_text.insert(tk.END, krl_code)
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

def format_point(pt):
    return f"{{X {pt[0]}, Y {pt[1]}, Z {pt[2]}, A 180.0, B 0.0, C 180.0}}"


def automate():
    global points, points_circ, motion_commands

    _push_undo_snapshot()
    clear_for_auto()

    # Ensure all points are lists
    points = [list(point) for point in points]
    points_circ = [list(point) for point in points_circ]

    # Retrieve input values
    e = E_entry.get()
    w = W_entry.get()
    turns = NumberofTurns_entry.get()
    layers = NumberofLayers_entry.get()
    a = float(a_entry.get())
    b = float(b_entry.get())
    c = float(c_entry.get())
    # Read tilt angle (fallback to 10 if invalid)
    try:
        tilt_angle_deg = float(tilt_entry.get())
    except Exception:
        tilt_angle_deg = 10.0
    tilt_angle_deg = max(5.0, min(tilt_angle_deg, 20.0))
    
    # Check for input errors
    if not e or not w or not turns or not layers:
        messagebox.showerror("Input Error", "Please fill in all the required fields in Automation Options.")
        return

    # Convert input values to appropriate types
    e = float(e)
    w = float(w)
    turns = int(turns)
    layers = int(layers)
    e = -e

    print("Automate action executed with values:")
    print(f"E: {e}, W: {w}, Turns: {turns}, Layers: {layers}")

    # Call the new alternating spiral function
    automate_alternating_spiral(e, w, turns, layers, a, b, c, tilt_angle_deg)

def automate_alternating_spiral(e, w, turns, layers, a, b, c, tilt_angle_deg):
    """New alternating spiral automation function"""
    global points, points_circ, motion_commands
    
    # Storage for points of each turn in each layer
    # Structure: saved_points[layer][turn] = {'points': [...], 'points_circ': [...], 'motion_commands': [...]}
    saved_points = {}
    
    # Calculate value for Dummy CIRC before OG point
    dummy_circ_y = ((points[1][1] + points_circ[1][1]) / 2) - (1.4 * e)
    dummy_circ_x = ((points[0][0] + points[4][0]) / 2) - e
    
    points_initiale = copy.deepcopy(points)
    points_circular_initiale = copy.deepcopy(points_circ)
    dummy_x_reset = copy.deepcopy(dummy_circ_x)
    dummy_y_reset = copy.deepcopy(dummy_circ_y)
    
    # First, generate all layers normally and save the points
    for layer in range(layers + 1):
        print(f"Generating layer: {layer}")
        saved_points[layer] = {}
        
        # Reset points for this layer
        points = copy.deepcopy(points_initiale)
        points_circ = copy.deepcopy(points_circular_initiale)
        dummy_circ_x = copy.deepcopy(dummy_x_reset)
        dummy_circ_y = copy.deepcopy(dummy_y_reset)

        # Apply Z offset for this layer
        if layer > 0:
            m = 1
            n = 0
            for k in motion_commands:
                if k == "LIN":
                    points[m][2] += w * layer
                    m += 1
                elif k == "CIRC":
                    points_circ[n][2] += w * layer
                    points_circ[n + 1][2] += w * layer
                    n += 2
            points[0][2] += w * layer

        # Generate all turns for this layer and save them
        for turn in range(turns + 1):
            print(f"  Generating turn: {turn}")
            
            # Create a copy of current points for this turn
            turn_points = copy.deepcopy(points)
            turn_points_circ = copy.deepcopy(points_circ)
            turn_motion_commands = copy.deepcopy(motion_commands)
            
            # Apply E offsets for this turn
            if turn > 0:
                # Apply the same E offset logic as before
                turn_points[0][1] -= e * turn

                # Apply E offsets to other points based on motion commands
                i = 1
                j = 0
                for k in motion_commands:
                    if k == "LIN":
                        if i == 1:
                            turn_points[i][1] -= e * turn
                        elif i == 2:
                            turn_points[i][0] += e * turn
                        elif i == 3:
                            turn_points[i][1] += e * turn
                        elif i == 4:
                            turn_points[i][0] -= e * turn
                        i += 1
                    elif k == "CIRC":
                        if j == 0:
                            turn_points_circ[j][0] += (e * turn / 2)
                            turn_points_circ[j][1] -= (e * turn / 2)
                            turn_points_circ[j + 1][0] += e * turn
                        elif j == 2:
                            turn_points_circ[j][0] += (e * turn / 2)
                            turn_points_circ[j][1] += (e * turn / 2)
                            turn_points_circ[j + 1][1] += e * turn
                        elif j == 4:
                            turn_points_circ[j][0] -= (e * turn / 2)
                            turn_points_circ[j][1] += (e * turn / 2)
                            turn_points_circ[j + 1][0] -= e * turn
                        j += 2
            
            # Save this turn's data
            saved_points[layer][turn] = {
                'points': turn_points,
                'points_circ': turn_points_circ,
                'motion_commands': turn_motion_commands
            }
    
    # Now generate the output using alternating spiral pattern
    for layer in range(layers + 1):
        print(f"Outputting layer: {layer}")
        
        # Add layer comment
        layer_comment = f"; ===== LAYER {layer} ====="
        if layer % 2 == 0:
            layer_comment += " (OUTWARD SPIRAL)"
        else:
            layer_comment += " (INWARD SPIRAL)"
        output_text.insert(tk.END, layer_comment + "\n")
        
        if layer % 2 == 0:  # Even layers: normal outward spiral
            turn_order = list(range(turns + 1))  # 0, 1, 2, 3
        else:  # Odd layers: inward spiral
            turn_order = list(range(turns, -1, -1))  # 3, 2, 1, 0
        
        for turn_idx, turn in enumerate(turn_order):
            print(f"  Outputting turn: {turn}")
            
            # Add turn comment
            turn_comment = f"; L{layer} T{turn} - "
            if turn_idx == 0:
                turn_comment += "START"
            else:
                prev_turn = turn_order[turn_idx - 1]
                turn_comment += f"TRANSITION from T{prev_turn}"
            output_text.insert(tk.END, turn_comment + "\n")
            
            # Get the saved data for this turn
            turn_data = saved_points[layer][turn]
            turn_points = turn_data['points']
            turn_points_circ = turn_data['points_circ']
            turn_motion_commands = turn_data['motion_commands']
            
            # Generate the output for this turn
            if turn_idx == 0:  # First turn in this layer
                if layer == 0:  # Very first turn of the entire sequence
                    # PTP to start point for the very beginning
                    if tilt_along_travel_var.get():
                        # Reset A-angle for comfortable PTP start
                        current_a_angle = 180.0
                        output_text.insert(tk.END, f"PTP {{X {turn_points[0][0]}, Y {turn_points[0][1]}, Z {turn_points[0][2]}, A {a}, B {tilt_angle_deg}, C {c}, S 2., T 43.}}\n")
                    else:
                        # Reset A-angle for comfortable PTP start
                        current_a_angle = float(a)
                        output_text.insert(tk.END, f"PTP {{X {turn_points[0][0]}, Y {turn_points[0][1]}, Z {turn_points[0][2]}, A {a}, B {b}, C {c}, S 2., T 43.}}\n")
                else:  # First turn of subsequent layers - use CIRC transition from previous layer
                    # Add layer transition comment
                    output_text.insert(tk.END, f"; L{layer-1} -> L{layer} TRANSITION\n")
                    
                    # Get the last point of the previous layer's last turn
                    prev_layer = layer - 1
                    if prev_layer % 2 == 0:  # Previous layer was even (outward)
                        prev_turn_order = list(range(turns + 1))
                    else:  # Previous layer was odd (inward)
                        prev_turn_order = list(range(turns, -1, -1))
                    
                    prev_last_turn = prev_turn_order[-1]  # Last turn of previous layer
                    prev_data = saved_points[prev_layer][prev_last_turn]
                    prev_points = prev_data['points']
                    prev_points_circ = prev_data['points_circ']
                    last_point_prev_layer = get_last_point_of_turn(prev_points, prev_points_circ, prev_data['motion_commands'])
                    
                    # Create CIRC transition from previous layer's last point to current layer's first point
                    # Pass turn_points[1] to calculate correct A-angle for the next edge
                    create_circ_transition(last_point_prev_layer, turn_points[0], turn_points[1], a, b, c, tilt_angle_deg)
            else:  # Not the first turn - need transition
                # Create transition from previous turn's end to current turn's start
                prev_turn = turn_order[turn_idx - 1]
                prev_data = saved_points[layer][prev_turn]
                prev_points = prev_data['points']
                prev_points_circ = prev_data['points_circ']
                
                # Find the last point of the previous turn (end of 11-point path)
                last_point_prev = get_last_point_of_turn(prev_points, prev_points_circ, prev_data['motion_commands'])
                
                # Create CIRC transition from last point of previous turn to first point of current turn
                # Pass turn_points[1] to calculate correct A-angle for the next edge
                create_circ_transition(last_point_prev, turn_points[0], turn_points[1], a, b, c, tilt_angle_deg)
            
            # Update global points for visualization
            points = copy.deepcopy(turn_points)
            points_circ = copy.deepcopy(turn_points_circ)
            motion_commands = copy.deepcopy(turn_motion_commands)
            
            # Generate the 11-point path for this turn
            generate_turn_path(turn_points, turn_points_circ, turn_motion_commands, a, b, c, tilt_angle_deg)
            
            # Update visualization after each turn
            visualize_cuboid()
    
    # Final visualization update
    visualize_cuboid()

def get_last_point_of_turn(turn_points, turn_points_circ, turn_motion_commands):
    """Get the last point of a turn's 11-point path"""
    i = 1
    j = 0
    last_point = turn_points[0]  # Start with first point
    
    for k in turn_motion_commands:
        if k == "LIN":
            last_point = turn_points[i]
            i += 1
        elif k == "CIRC":
            last_point = turn_points_circ[j + 1]  # End point of CIRC
            j += 2
    
    return last_point

def create_circ_transition(from_point, to_point, next_point, a, b, c, tilt_angle_deg):
    """Create a CIRC transition between two points with intermediate point"""
    # Create proper rounded transitions like the working corners
    # The key is to use perpendicular offset, not inline offset
    
    # Calculate the midpoint
    mid_x = (from_point[0] + to_point[0]) / 2
    mid_y = (from_point[1] + to_point[1]) / 2
    mid_z = (from_point[2] + to_point[2]) / 2
    
    # Calculate the direction vector
    dx = to_point[0] - from_point[0]
    dy = to_point[1] - from_point[1]
    
    # Calculate distance for proper scaling
    distance = math.sqrt(dx*dx + dy*dy)
    
    if distance == 0:
        return  # No transition needed if points are the same
    
    # Normalize the direction vector
    dx_norm = dx / distance
    dy_norm = dy / distance
    
    # Create perpendicular vector (90 degrees clockwise)
    # This creates the outward curve like the working corners
    perp_x = dy_norm
    perp_y = -dx_norm
    
    # Use distance-proportional offset for smooth curves
    offset_distance = distance * 0.2  # 20% of the distance for very smooth curves
    
    # Calculate intermediate point using perpendicular offset
    # This creates the same smooth, outward-curving effect as the corners
    intermediate_x = mid_x + (perp_x * offset_distance)
    intermediate_y = mid_y + (perp_y * offset_distance)
    intermediate_z = mid_z
    
    # Visualize the transition on canvas
    # Draw the intermediate point in a different color to distinguish transitions
    draw_point(intermediate_x, intermediate_y, "purple")
    
    # Draw the transition lines
    draw_line(from_point[0], from_point[1], intermediate_x, intermediate_y, "CIRC")
    draw_line(intermediate_x, intermediate_y, to_point[0], to_point[1], "CIRC")
    
    # Calculate A angle based on the NEXT EDGE direction (from to_point to next_point)
    # This ensures the tool is oriented correctly for the upcoming straight edge
    dx = next_point[0] - to_point[0]
    dy = next_point[1] - to_point[1]
    
    # Use transition A-angle calculation to update global current_a_angle
    A_angle = calculate_transition_a_angle(dx, dy)
    
    # Generate the CIRC command with calculated A, interface B tilt, and interface C
    output_text.insert(tk.END, f"CIRC {{X {intermediate_x}, Y {intermediate_y}, Z {intermediate_z}}},{{X {to_point[0]}, Y {to_point[1]}, Z {to_point[2]}, A {A_angle:.1f}, B {tilt_angle_deg}, C {c}}}\n")


def generate_turn_path(turn_points, turn_points_circ, turn_motion_commands, a, b, c, tilt_angle_deg):
    """Generate the 11-point path for a single turn"""
    i = 1
    j = 0
    
    for k in turn_motion_commands:
        if k == "LIN":
            if tilt_along_travel_var.get():
                # Pen-like movement: tool follows the path direction
                if i > 0:  # Make sure we have a previous point
                    # Calculate movement direction
                    dx = turn_points[i][0] - turn_points[i-1][0]  # X movement
                    dy = turn_points[i][1] - turn_points[i-1][1]  # Y movement
                    
                    # Keep A-angle constant from previous movement (no rotation during LIN)
                    lin_a = get_current_a_angle()  # Use current A-angle without change
                    
                    # Apply constant tilt for pen-like movement
                    # Keep B-axis constant at tilt angle, only rotate A-axis
                    lin_b = tilt_angle_deg  # Constant tilt from interface
                    lin_c = c  # Use interface C value
                else:
                    # Default starting orientation
                    lin_a = a  # Use interface A value
                    lin_b = tilt_angle_deg  # Use interface tilt
                    lin_c = c  # Use interface C value
                
                # Pen-like movement: tool follows the path direction
                output_text.insert(tk.END, f"LIN {{X {turn_points[i][0]}, Y {turn_points[i][1]}, Z {turn_points[i][2]}, A {lin_a:.1f}, B {lin_b:.1f}, C {lin_c:.1f}}}\n")
            else:
                output_text.insert(tk.END, f"LIN {{X {turn_points[i][0]}, Y {turn_points[i][1]}, Z {turn_points[i][2]}, A {a}, B {b}, C {c}}}\n")
            i += 1
        elif k == "CIRC":
            # Calculate A angle based on the NEXT edge direction (not the CIRC diagonal)
            # This ensures the tool orientation matches the straight edge after the corner
            
            middle_x = turn_points_circ[j][0]
            middle_y = turn_points_circ[j][1]
            end_x = turn_points_circ[j + 1][0]
            end_y = turn_points_circ[j + 1][1]
            
            # Look ahead to the next LIN point to get the actual edge direction
            if i < len(turn_points):  # If there's a next LIN point
                next_x = turn_points[i][0]
                next_y = turn_points[i][1]
                # Calculate direction from CIRC end to next LIN point (the actual edge)
                dx = next_x - end_x
                dy = next_y - end_y
            else:
                # Last CIRC, use direction to first point (closing the loop)
                next_x = turn_points[0][0]
                next_y = turn_points[0][1]
                dx = next_x - end_x
                dy = next_y - end_y
            
            # Use exact A-angle calculation based on next edge direction
            A_angle = calculate_smooth_a_angle(dx, dy)
            
            if tilt_along_travel_var.get():
                # Use calculated A, interface B tilt, and interface C
                output_text.insert(tk.END, f"CIRC {{X {turn_points_circ[j][0]}, Y {turn_points_circ[j][1]}, Z {turn_points_circ[j][2]}}},{{X {turn_points_circ[j + 1][0]}, Y {turn_points_circ[j + 1][1]}, Z {turn_points_circ[j + 1][2]}, A {A_angle:.1f}, B {tilt_angle_deg}, C {c}}}\n")
            else:
                # Use calculated A, interface B tilt, and interface C
                output_text.insert(tk.END, f"CIRC {{X {turn_points_circ[j][0]}, Y {turn_points_circ[j][1]}, Z {turn_points_circ[j][2]}}},{{X {turn_points_circ[j + 1][0]}, Y {turn_points_circ[j + 1][1]}, Z {turn_points_circ[j + 1][2]}, A {A_angle:.1f}, B {tilt_angle_deg}, C {c}}}\n")
            j += 2
    
def clear_for_auto():
    global current_a_angle
    _push_undo_snapshot()
    current_a_angle = 180.0  # Reset A angle to default
    canvas.delete("all")
    output_text.delete("1.0", tk.END)

def clear_all():
    global points, points_circ, motion_commands, current_a_angle
    _push_undo_snapshot()
    points = []
    points_circ = []
    motion_commands = []
    current_a_angle = 180.0  # Reset A angle to default
    canvas.delete("all")
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
    # Get the KRL code from the output text widget
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

    # Write the KRL code to the file if a file path is provided
    if file_path:
        # Extract the base filename without the extension
        file_name = file_path.split('/')[-1].split('.')[0]

        # Create the header with the correct DEF name
        header = f"""&ACCESS RVP
&REL 299
&PARAM EDITMASK = *
&PARAM TEMPLATE = C:\\KRC\\Roboter\\Template\\vorgabe
&PARAM DISKPATH = KRC:\\R1\\Program
DEF {file_name}( )
;FOLD INI;%{{PE}}
  ;FOLD BASISTECH INI
    GLOBAL INTERRUPT DECL 3 WHEN $STOPMESS==TRUE DO IR_STOPM ( )
    INTERRUPT ON 3 
    BAS (#INITMOV,0 )
  ;ENDFOLD (BASISTECH INI)
  ;FOLD SPOTTECH INI
    USERSPOT(#INIT)
  ;ENDFOLD (SPOTTECH INI)
  ;FOLD GRIPPERTECH INI
    USER_GRP(0,DUMMY,DUMMY,GDEFAULT)
  ;ENDFOLD (GRIPPERTECH INI)
  ;FOLD USER INI
    ;Make your modifications here
  ;ENDFOLD (USER INI)
;ENDFOLD (INI)
;FOLD PTP HOME  Vel= 100 % DEFAULT;%{{PE}}%MKUKATPBASIS,%CMOVE,%VPTP,%P 1:PTP, 2:HOME, 3:, 5:100, 7:DEFAULT
$BWDSTART = FALSE
PDAT_ACT=PDEFAULT
FDAT_ACT=FHOME
BAS (#PTP_PARAMS,100 )
$H_POS=XHOME
PTP  XHOME
;ENDFOLD
; Define base with Tool 3 - Optimized for comfortable robot positioning
BASE_DATA[1] = {{X 0.0, Y 0.0, Z 200.0, A 0.0, B 0.0, C 0.0}}
$BASE = BASE_DATA[1]
; Define Tool 3 with calibrated TCP values (MHK-TOOL)
TOOL_DATA[3] = {{X -6.601, Y 131.225, Z 165.955, A 0.0, B 0.0, C 0.0}}
$TOOL = TOOL_DATA[3]
; Set frame data for proper tool usage
FDAT_ACT = {{TOOL_NO 3, BASE_NO 1, IPO_FRAME #BASE}}
; Set approximation for smooth motion
$APO.CDIS = 5.0
$APO.CPTP = 50
; Velocities and accelerations
BAS (#VEL_PTP, 100)
BAS (#VEL_CP, 2)
BAS (#ACC_CP, 100)
$ACC_AXIS[1]=100
$ACC_AXIS[2]=100
$ACC_AXIS[3]=100
$ACC_AXIS[4]=100
$ACC_AXIS[5]=100
$ACC_AXIS[6]=100\n"""

        # Combine the header with the KRL code
        full_code = header + krl_code + "END"

        # Write the full code to the file
        with open(file_path, "w") as file:
            file.write(full_code)

        # Show a message box indicating that the KRL code has been saved
        messagebox.showinfo("KRL Code Exported", "The KRL code has been exported successfully.")

def import_points():
    file_path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
    if file_path:
        try:
            _push_undo_snapshot()
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

                # Save remaining points and motion commands
                for k in motion_commands:
                    if k == "LIN":
                        x, y, z = points[i]
                        a, b, c = orientations[i]
                        file.write(f"{x} {y} {z} {a} {b} {c} LIN\n")
                        i += 1
                    elif k == "CIRC":
                        x1, y1, z1 = points_circ[j]
                        x2, y2, z2 = points_circ[j + 1]
                        a1, b1, c1 = orientations[j + 1]  # Get A, B, C for the second point of CIRC
                        file.write(f"{x1} {y1} {z1} {x2} {y2} {z2} {a1} {b1} {c1} CIRC\n")
                        j += 2  # Move to the next pair of points in points_circ

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
            output_text.insert(tk.END, '; ' + comment + '\n')
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
                    output_text.insert(tk.END, f"PTP {{X {xa}, Y {ya}, Z {za}, A {aa}, B {ba}, C {ca}, S 2., T 43.}}\n")
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
    xr_entry.insert(0, "685")  # default value - adjusted for coordinate shift (+23)

    tk.Label(popup, text="Center Yr:").grid(row=1, column=0, padx=20)
    yr_entry = tk.Entry(popup); yr_entry.grid(row=1, column=1, padx=50, pady=30)
    yr_entry.insert(0, "25")  # default value - adjusted for coordinate shift (+153)

    tk.Label(popup, text="Center Zr:").grid(row=2, column=0, padx=20)
    zr_entry = tk.Entry(popup); zr_entry.grid(row=2, column=1, padx=50, pady=30)
    zr_entry.insert(0, "50")  # Comfortable working height relative to optimized base

    tk.Label(popup, text="Cuboid Length (X):").grid(row=3, column=0, padx=20)
    length_entry = tk.Entry(popup); length_entry.grid(row=3, column=1, padx=50, pady=30)

    tk.Label(popup, text="Cuboid Width (Y):").grid(row=4, column=0, padx=20)
    width_entry  = tk.Entry(popup); width_entry.grid(row=4, column=1, padx=50, pady=30)

    tk.Label(popup, text="Tool Height (Z offset):").grid(row=5, column=0, padx=20)
    th_entry     = tk.Entry(popup); th_entry.grid(row=5, column=1, padx=50, pady=30)

    def generate_points():
        try:
            _push_undo_snapshot()
            Xr = float(xr_entry.get())
            Yr = float(yr_entry.get())
            Zr = float(zr_entry.get())
            L  = float(length_entry.get())
            W  = float(width_entry.get())
            Th = float(th_entry.get())
        except ValueError:
            messagebox.showerror("Input Error", "Please enter valid numbers")
            return

        # Derived constants
        Z = Zr + Th
        A, B, C = 180.0, 0.0, 180.0

        # Corner rounding radius (variable): 15% of min(L,W), with limits
        min_edge = max(min(L, W), 1.0)
        r_base = 0.15 * min_edge
        # Clamp radius to avoid self-intersection or vanishing arcs
        r = max(2.0, min(r_base, min_edge / 3.0))

        # Precompute rectangle edges and useful centers for arcs
        top_y    = Yr + W/2
        bottom_y = Yr - W/2
        left_x  = Xr - L/2
        right_x = Xr + L/2

        # Key points along edges (approach points r from each true corner)
        start_top_right = (right_x - r, top_y)           # 1
        top_left_approach = (left_x + r, top_y)          # 2
        left_top_approach = (left_x, top_y - r)         # 4 (end of first CIRC)
        left_bottom_approach = (left_x, bottom_y + r)   # 5
        bottom_left_approach = (left_x + r, bottom_y)   # 7 (end of second CIRC)
        bottom_right_approach = (right_x - r, bottom_y) # 8
        right_bottom_approach = (right_x, bottom_y + r)  # 10 (end of third CIRC)
        right_top_approach = (right_x, top_y - r)        # 11

        # Arc centers for 90° fillets
        center_TL = (left_x + r, top_y - r)
        center_BL = (left_x + r, bottom_y + r)
        center_BR = (right_x - r, bottom_y + r)

        # 45° midpoints on each arc (via points for CIRC)
        inv_sqrt2 = 2 ** -0.5
        mid_TL = (center_TL[0] - r*inv_sqrt2, center_TL[1] + r*inv_sqrt2)  # from top->left
        mid_BL = (center_BL[0] - r*inv_sqrt2, center_BL[1] - r*inv_sqrt2)  # from left->bottom (corrected)
        mid_BR = (center_BR[0] + r*inv_sqrt2, center_BR[1] - r*inv_sqrt2)  # from bottom->right

        # Clear all existing data before generating new
        clear_all()

        # --- Build lists consistent with manual/import flows ---
        # PTP 1
        points.append((start_top_right[0], start_top_right[1], Z))
        orientations.append((A, B, C))
        output_text.insert(tk.END, f"PTP {{X {start_top_right[0]}, Y {start_top_right[1]}, Z {Z}, A {A}, B {B}, C {C}, S 2., T 43.}}\n")

        # LIN 2 (top edge toward TL)
        points.append((top_left_approach[0], top_left_approach[1], Z))
        orientations.append((A, B, C))
        motion_commands.append("LIN")
        output_text.insert(tk.END, f"LIN {{X {top_left_approach[0]}, Y {top_left_approach[1]}, Z {Z}, A {A}, B {B}, C {C}}}\n")

        # CIRC 3–4 (round TL corner)
        points_circ.extend([
            (mid_TL[0], mid_TL[1], Z),
            (left_top_approach[0], left_top_approach[1], Z)
        ])
        # Append two orientation entries for CIRC (middle and end)
        orientations.append((A, B, C))
        orientations.append((A, B, C))
        motion_commands.append("CIRC")
        output_text.insert(tk.END, f"CIRC {{X {mid_TL[0]}, Y {mid_TL[1]}, Z {Z}}},{{X {left_top_approach[0]}, Y {left_top_approach[1]}, Z {Z}, A {A}, B {B}, C {C}}}\n")

        # LIN 5 (left edge toward BL)
        points.append((left_bottom_approach[0], left_bottom_approach[1], Z))
        orientations.append((A, B, C))
        motion_commands.append("LIN")
        output_text.insert(tk.END, f"LIN {{X {left_bottom_approach[0]}, Y {left_bottom_approach[1]}, Z {Z}, A {A}, B {B}, C {C}}}\n")

        # CIRC 6–7 (round BL corner)
        points_circ.extend([
            (mid_BL[0], mid_BL[1], Z),
            (bottom_left_approach[0], bottom_left_approach[1], Z)
        ])
        orientations.append((A, B, C))
        orientations.append((A, B, C))
        motion_commands.append("CIRC")
        output_text.insert(tk.END, f"CIRC {{X {mid_BL[0]}, Y {mid_BL[1]}, Z {Z}}},{{X {bottom_left_approach[0]}, Y {bottom_left_approach[1]}, Z {Z}, A {A}, B {B}, C {C}}}\n")

        # LIN 8 (bottom edge toward BR)
        points.append((bottom_right_approach[0], bottom_right_approach[1], Z))
        orientations.append((A, B, C))
        motion_commands.append("LIN")
        output_text.insert(tk.END, f"LIN {{X {bottom_right_approach[0]}, Y {bottom_right_approach[1]}, Z {Z}, A {A}, B {B}, C {C}}}\n")

        # CIRC 9–10 (round BR corner)
        points_circ.extend([
            (mid_BR[0], mid_BR[1], Z),
            (right_bottom_approach[0], right_bottom_approach[1], Z)
        ])
        orientations.append((A, B, C))
        orientations.append((A, B, C))
        motion_commands.append("CIRC")
        output_text.insert(tk.END, f"CIRC {{X {mid_BR[0]}, Y {mid_BR[1]}, Z {Z}}},{{X {right_bottom_approach[0]}, Y {right_bottom_approach[1]}, Z {Z}, A {A}, B {B}, C {C}}}\n")

        # LIN 11 (right edge toward TR)
        right_top = (right_top_approach[0], right_top_approach[1], Z)
        points.append(right_top)
        orientations.append((A, B, C))
        motion_commands.append("LIN")
        output_text.insert(tk.END, f"LIN {{X {right_top[0]}, Y {right_top[1]}, Z {Z}, A {A}, B {B}, C {C}}}\n")

        popup.destroy()
        visualize_cuboid()

    tk.Button(popup, text="Generate", command=generate_points).grid(row=6, column=0, columnspan=2, pady=10)


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
        "Auto-Orient Along Travel: When enabled, orientations use coordinate-based tilting:\n"
        "• A=180° (constant for all movements)\n"
        "• B=±tilt angle for X translations (inverted direction)\n"
        "• C=180°±tilt angle for Y translations (calculated from base C=180°)\n"
        "Tilt angle can be set near the Functions menu. Disable to use your own A/B/C.\n\n"
        "Benefits:\n"
        "• Logical tilting: B-axis for X movements, C-axis for Y movements\n"
        "• No circular motion issues (no rotation around axis centers)\n"
        "• Consistent approach angle in appropriate direction\n"
        "• Tool orientation matches movement direction\n"
        "• Better suited for layer-by-layer 2D printing\n"
        "• More predictable tool orientation\n\n"
        "Tips:\n"
        "• Use tilt angle 10-20° for best results\n"
        "• Use small E (filament thickness) to avoid over-extrusion\n"
        "• Keep base path consistent (LIN/CIRC order) for best automation"
    )

root = tk.Tk()
root.title("Cuboidal KRL Code Generator")

def go_back_to_selector():
    try:
        # Attempt to open the main selector script in a new process
        selector_script = os.path.join(os.path.dirname(__file__), 'Main_Window_Program_Selector_.py')
        if os.path.exists(selector_script):
            subprocess.Popen([sys.executable, selector_script])
        else:
            messagebox.showwarning("Not Found", "Main_Window_Program_Selector_.py was not found.")
    except Exception as ex:
        messagebox.showerror("Error", f"Failed to open selector: {ex}")
    finally:
        # Close current window
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
functions_menu.add_command(label="Add Approach\t (Ctrl+Shift+A)", command=open_approach_popup)
functions_menu.add_separator()
functions_menu.add_command(label="Change Center\t (Ctrl+Shift+C)", command=change_center)
functions_menu.add_separator()
functions_menu.add_command(label="Auto‑Generate Base\t (Ctrl+Shift+G)", command=open_generate_popup)

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

root.mainloop()