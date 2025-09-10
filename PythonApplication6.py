import tkinter as tk
from tkinter import messagebox, filedialog
import copy

# Variables to store the points
points = []

# Variables to store the circ points
points_circ = []

# Motion command types for each line
motion_commands = []

# Orientations for each line
orientations = []

# Counter for numbering the KRL codes
krl_counter = 1

# Flag for whether Automate function is executed
auto_flag = 0

#For Center Change
xc = 0 
yc = 0
zc = 0

# Canvas dimensions
canvas_width = 400
canvas_height = 300

# Initial scaling factor
scaling_factor = 3

# Add a global variable to track if a CIRC command has been executed
circ_executed = False


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


def generate_krl_code(points, motion_commands, points_circ, orientations):
    krl_code = ""

    # Guard against empty input
    if not points:
        return krl_code

    # Handle the origin point separately
    origin_point = points[0]
    krl_code += f"PTP {{X {origin_point[0]}, Y {origin_point[1]}, Z {origin_point[2]}, A {orientations[0][0]}, B {orientations[0][1]}, C {orientations[0][2]}, S 2., T 43.}}\n"

    i = 1
    j = 0
    n = 1

    for k in motion_commands:
        if k == "LIN":
            krl_code += f"LIN {{X {points[i][0]}, Y {points[i][1]}, Z {points[i][2]}, A {orientations[n][0]}, B {orientations[n][1]}, C {orientations[n][2]}}}\n"
            i += 1
            n += 1
        elif k == "CIRC":
            # Use orientation of the CIRC end point. Orientations list currently stores two entries per CIRC.
            krl_code += f"CIRC {{X {points_circ[j][0]}, Y {points_circ[j][1]}, Z {points_circ[j][2]}}},{{X {points_circ[j + 1][0]}, Y {points_circ[j + 1][1]}, Z {points_circ[j + 1][2]}, A {orientations[n + 1][0]}, B {orientations[n + 1][1]}, C {orientations[n + 1][2]}}}\n"
            j += 2
            n += 2

    return krl_code

def update_krl_code():
    global auto_flag
    auto_flag = 1
    # Generate KRL code for the points and motion commands
    krl_code = generate_krl_code(points, motion_commands, points_circ, orientations)
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
    global points, circ_executed, motion_commands
    x_str = x_entry.get()
    y_str = y_entry.get()
    z_str = z_entry.get()
    a_str = a_entry.get()
    b_str = b_entry.get()
    c_str = c_entry.get()

    if not validate_coordinates(x_str, y_str, z_str, a_str , b_str, c_str):
        messagebox.showwarning("Invalid Input", "Please enter valid numerical values for X, Y, and Z coordinates or A, B, and C orientations.")
        return

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
    global circ_executed, krl_counter
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
        global krl_counter
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
                # Generate the KRL code
                krl_code = f"CIRC {{X {middle_x}, Y {middle_y}, Z {middle_z}}},{{X {end_x}, Y {end_y}, Z {end_z}, A {a}, B {b}, C {c}}}\n"
                # Append the KRL code to the output text widget
                points_circ.append((float(middle_x), float(middle_y), float(middle_z)))
                orientations.append((float(a), float(b), float(c)))
                motion_commands.append("CIRC")
                points_circ.append((float(end_x), float(end_y), float(end_z)))
                orientations.append((float(a), float(b), float(c)))
                output_text.insert(tk.END, krl_code)
                # Increment the KRL counter
                krl_counter += 1
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
    global selected_motion_command, circ_executed
    selected_motion_command = motion_command
    # If the selected command is CIRC, prompt the user to input points
    if motion_command == "CIRC":
        input_points_for_circ()
        # Set the flag indicating that a CIRC command has been executed
        circ_executed = True

def format_point(pt):
    return f"{{X {pt[0]}, Y {pt[1]}, Z {pt[2]}, A 180.0, B 0.0, C 180.0}}"


def automate():
    global points, points_circ, motion_commands

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

    # Calculate value for Dummy CIRC before OG point
    dummy_circ_y = ((points[1][1] + points_circ[1][1]) / 2) - (1.4 * e)
    dummy_circ_x = ((points[0][0] + points[4][0]) / 2) - e
    
    x = points[0][0]
    y = points[0][1]
    points_initiale = copy.deepcopy(points)
    points_circular_initiale = copy.deepcopy(points_circ)
    dummy_x_reset = copy.deepcopy(dummy_circ_x)
    dummy_y_reset = copy.deepcopy(dummy_circ_y)
    
    for layer in range(layers + 1):  # Ensure it includes the final layer
        print(f"layer: {layer}")
        m = 1
        n = 0
        
        points = copy.deepcopy(points_initiale)
        points_circ = copy.deepcopy(points_circular_initiale)
        dummy_circ_x = copy.deepcopy(dummy_x_reset)
        dummy_circ_y = copy.deepcopy(dummy_y_reset)

        if layer > 0:
            for k in motion_commands:
                if k == "LIN":
                    points[m][2] += w * layer
                    m += 1
                elif k == "CIRC":
                    points_circ[n][2] += w * layer
                    points_circ[n + 1][2] += w * layer
                    n += 2

        if layer > 0:
            points[0][2] += w * layer

        layer_output_lines = []

        for turn in range(turns + 1):
            print(f"turn: {turn}")
            i = 1
            j = 0

            if turn == 0:
                layer_output_lines.append(f"PTP {{X {points[0][0]}, Y {points[0][1]}, Z {points[0][2]}, A {a}, B {b}, C {c}, S 2., T 43.}}")

            if turn > 0:
                points[0][1] -= e
                layer_output_lines.append(f"CIRC {{X {dummy_circ_x}, Y {dummy_circ_y}, Z {points[0][2]}}},{{X {points[0][0]}, Y {points[0][1]}, Z {points[0][2]}, A {a}, B {b}, C {c}}}")

            if turn > 0:
                for k in motion_commands:
                    if k == "LIN":
                        if turn <= turns:
                            if i == 1:
                                points[i][1] -= e
                            elif i == 2:
                                points[i][0] += e
                            elif i == 3:
                                points[i][1] += e
                            elif i == 4:
                                points[i][0] -= e
                                draw_point(dummy_circ_x, dummy_circ_y)
                                draw_line(points[i][0], points[i][1], dummy_circ_x, dummy_circ_y, "CIRC")
                                draw_line(dummy_circ_x, dummy_circ_y, points[0][0], points[0][1], "CIRC")
                                dummy_circ_x -= (0.6 * e)
                                dummy_circ_y -= (0.6 * e)
                            layer_output_lines.append(f"LIN {{X {points[i][0]}, Y {points[i][1]}, Z {points[i][2]}, A {a}, B {b}, C {c}}}")
                            i += 1
                        else:
                            layer_output_lines.append(f"LIN {{X {points[i][0]}, Y {points[i][1]}, Z {points[i][2]}, A {a}, B {b}, C {c}}}")

                    elif k == "CIRC":
                        if turn <= turns:
                            if j == 0:
                                points_circ[j][0] += (e / 2)
                                points_circ[j][1] -= (e / 2)
                                points_circ[j + 1][0] += e
                            elif j == 2:
                                points_circ[j][0] += (e / 2)
                                points_circ[j][1] += (e / 2)
                                points_circ[j + 1][1] += e
                            elif j == 4:
                                points_circ[j][0] -= (e / 2)
                                points_circ[j][1] += (e / 2)
                                points_circ[j + 1][0] -= e
                            layer_output_lines.append(f"CIRC {{X {points_circ[j][0]}, Y {points_circ[j][1]}, Z {points_circ[j][2]}}},{{X {points_circ[j + 1][0]}, Y {points_circ[j + 1][1]}, Z {points_circ[j + 1][2]}, A {a}, B {b}, C {c}}}")
                            j += 2
                        else:
                            layer_output_lines.append(f"CIRC {{X {points_circ[j][0]}, Y {points_circ[j][1]}, Z {points_circ[j][2]}}},{{X {points_circ[j + 1][0]}, Y {points_circ[j + 1][1]}, Z {points_circ[j + 1][2]}, A {a}, B {b}, C {c}}}")
                visualize_cuboid()
            elif turn == 0:
                for k in motion_commands:
                    if k == "LIN":
                        if turn <= turns:
                            layer_output_lines.append(f"LIN {{X {points[i][0]}, Y {points[i][1]}, Z {points[i][2]}, A {a}, B {b}, C {c}}}")
                            i += 1
                        else:
                            layer_output_lines.append(f"LIN {{X {points[i][0]}, Y {points[i][1]}, Z {points[i][2]}, A {a}, B {b}, C {c}}}")

                    elif k == "CIRC":
                        if turn <= turns:
                            layer_output_lines.append(f"CIRC {{X {points_circ[j][0]}, Y {points_circ[j][1]}, Z {points_circ[j][2]}}},{{X {points_circ[j + 1][0]}, Y {points_circ[j + 1][1]}, Z {points_circ[j + 1][2]}, A {a}, B {b}, C {c}}}")
                            j += 2
                        else:
                            layer_output_lines.append(f"CIRC {{X {points_circ[j][0]}, Y {points_circ[j][1]}, Z {points_circ[j][2]}}},{{X {points_circ[j + 1][0]}, Y {points_circ[j + 1][1]}, Z {points_circ[j + 1][2]}, A {a}, B {b}, C {c}}}")
                visualize_cuboid()

        # Build reversed sequence for odd layers if checkbox is enabled
        if layer % 2 == 1 and alternate_layer_direction_var.get():
            motion_lines = [line for line in layer_output_lines if line.startswith(("LIN", "CIRC"))]
            reconstructed_lines = []
            circ_blocks = []
            circ_to_prev_lin = []
            lin_lines = [line for line in motion_lines if line.startswith("LIN")]

            prev_lin = None
            for line in motion_lines:
                if line.startswith("LIN"):
                    prev_lin = line
                elif line.startswith("CIRC"):
                    circ_blocks.append(line)
                    circ_to_prev_lin.append((line, prev_lin))

            if lin_lines:
                last_lin_coords = lin_lines[-1][4:].strip()
                reconstructed_lines.append("PTP " + last_lin_coords[:-1] + ", S 2., T 43.}")

            if circ_blocks:
                last_circ = circ_blocks[-1]
                circ_parts = last_circ[5:].split("},{")
                if len(circ_parts) == 2:
                    circ_end = circ_parts[1].strip()
                    reconstructed_lines.append(f"LIN {{{circ_end}}}")

            reversed_pairs = list(reversed(circ_to_prev_lin))
            for idx, (circ, lin_before) in enumerate(reversed_pairs):
                circ_parts = circ[5:].split("},{")
                if len(circ_parts) == 2 and lin_before is not None:
                    intermediate = circ_parts[0].strip().strip("{}")
                    lin_coords = lin_before[4:].strip().strip("{}")
                    reconstructed_lines.append(f"CIRC {{{intermediate}}},{{{lin_coords}}}")
                    if idx + 1 < len(reversed_pairs):
                        next_circ = reversed_pairs[idx + 1][0]
                        next_circ_parts = next_circ[5:].split("},{")
                        if len(next_circ_parts) == 2:
                            next_end = next_circ_parts[1].strip().strip("{}")
                            reconstructed_lines.append(f"LIN {{{next_end}}}")
                    else:
                        if lin_lines:
                            first_lin_point = lin_lines[0][4:].strip().strip("{}")
                            reconstructed_lines.append(f"LIN {{{first_lin_point}}}")

            layer_output_lines = reconstructed_lines

        for line in layer_output_lines:
            output_text.insert(tk.END, line + "\n")


    
def clear_for_auto():
    global krl_counter
    krl_counter = 1
    canvas.delete("all")
    output_text.delete("1.0", tk.END)

def clear_all():
    global points, points_circ, motion_commands, krl_counter
    points = []
    points_circ = []
    motion_commands = []
    krl_counter = 1
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
; Define base, tool and vel
BASE_DATA[1] = {{X 0.0, Y 0.0, Z 50.0, A 0.0, B 0.0, C 0.0}}
$BASE = BASE_DATA[1]
TOOL_DATA[1] = {{X 0.0, Y 0.0, Z 20.0, A 0.0, B 0.0, C 0.0}}
$TOOL = TOOL_DATA[1]
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
    xr_entry.insert(0, "660")  # default value

    tk.Label(popup, text="Center Yr:").grid(row=1, column=0, padx=20)
    yr_entry = tk.Entry(popup); yr_entry.grid(row=1, column=1, padx=50, pady=30)
    yr_entry.insert(0, "-125")  # default value

    tk.Label(popup, text="Center Zr:").grid(row=2, column=0, padx=20)
    zr_entry = tk.Entry(popup); zr_entry.grid(row=2, column=1, padx=50, pady=30)
    zr_entry.insert(0, "120")  # default value

    tk.Label(popup, text="Cuboid Length (X):").grid(row=3, column=0, padx=20)
    length_entry = tk.Entry(popup); length_entry.grid(row=3, column=1, padx=50, pady=30)

    tk.Label(popup, text="Cuboid Width (Y):").grid(row=4, column=0, padx=20)
    width_entry  = tk.Entry(popup); width_entry.grid(row=4, column=1, padx=50, pady=30)

    tk.Label(popup, text="Tool Height (Z offset):").grid(row=5, column=0, padx=20)
    th_entry     = tk.Entry(popup); th_entry.grid(row=5, column=1, padx=50, pady=30)

    def generate_points():
        try:
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
        output_text.insert(tk.END, f"PTP {{X {start_top_right[0]}, Y {start_top_right[1]}, Z {Z}, A {A}, B {B}, C {C}}}\n")

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

    messagebox.showinfo("How to import external points?", "To import external points from an external file rather than inputing them 1 by 1 through the program, you will click on the 'Import Points' button and select a Text File (.txt) where all of your 11 points are saved.\n\nPlease follow the format in the example below in your text file to avoid any errors:\nFormat: {X Y Z A B C Motion_command}\n\n0.0 0.0 125.0 180.0 0.0 180.0\n50.0 0.0 125.0 180.0 0.0 180.0 LIN\n60.0 10.0 125.0 70.0 30.0 125.0 180.0 0.0 180.0 CIRC\n70.0 80.0 125.0 180.0 0.0 180.0 LIN\n60.0 100.0 125.0 50.0 110.0 125.0 180.0 0.0 180.0 CIRC\n0.0 110.0 125.0 180.0 0.0 180.0 LIN\n-10.0 100.0 125.0 -20.0 80.0 125.0 180.0 0.0 180.0 CIRC\n-20.0 30.0 125.0 180.0 0.0 180.0 LIN\n\nN.b: You can create your desired cuboid once through the program and then use the 'Save Points' button which saves the points with their orientations in a text file (.txt) with the desired format mentioned above.\n\nThis file can then be imported later to be used through the program.")

root = tk.Tk()
root.title("Cuboidal KRL Code Generator")

# Default values
default_x = 745
default_y = 10
default_increment = 0
default_ori = 180
tool_z = 125

input_label = tk.Label(root, text="Enter 11 points (Maximum) to form a cuboid:")
input_label.grid(row=0, column=0, columnspan=4)

# Input fields for X, Y, Z coordinates & A, B , C orientations
x_label = tk.Label(root, text="X:")
x_label.grid(row=1, column=0)
x_entry = tk.Entry(root)
x_entry.insert(0, default_x)
x_entry.grid(row=1, column=1)

y_label = tk.Label(root, text="Y:")
y_label.grid(row=2, column=0)
y_entry = tk.Entry(root)
y_entry.insert(0, default_y)
y_entry.grid(row=2, column=1)

z_label = tk.Label(root, text="Z:")
z_label.grid(row=3, column=0)
z_entry = tk.Entry(root)
z_entry.insert(0, tool_z)
z_entry.grid(row=3, column=1)

a_label = tk.Label(root, text="A:")
a_label.grid(row=1, column=2)
a_entry = tk.Entry(root)
a_entry.insert(0, default_ori)
a_entry.grid(row=1, column=3)

b_label = tk.Label(root, text="B:")
b_label.grid(row=2, column=2)
b_entry = tk.Entry(root)
b_entry.insert(0, default_increment)
b_entry.grid(row=2, column=3)

c_label = tk.Label(root, text="C:")
c_label.grid(row=3, column=2)
c_entry = tk.Entry(root)
c_entry.insert(0, default_ori)
c_entry.grid(row=3, column=3)

center_button = tk.Button(root, text="Change Center", command=change_center)
center_button.grid(row=8, column=4)

Instructions_button = tk.Button(root, text="General Instructions", command=instructions)
Instructions_button.grid(row=6, column=4)

pt_instr_button = tk.Button(root, text="Points Order Instructions", command=pt_instructions)
pt_instr_button.grid(row=7, column=4, pady=10)

im_instr_button = tk.Button(root, text="Import/Save Instructions", command=import_instructions)
im_instr_button.grid(row=11, column=4)

motion_label = tk.Label(root, text="_____________________________________________________________________________________________________________")
motion_label.grid(row=4, column=0, columnspan=4)

# Label specifying the default motion command
motion_label = tk.Label(root, text="Automation Options")
motion_label.grid(row=5, column=0, columnspan=4)

# Add entry fields and buttons to the GUI

E_label = tk.Label(root, text="Filament Thickness (E):")
E_label.grid(row=6, column=0)
E_entry = tk.Entry(root)
E_entry.grid(row=6, column=1)

W_label = tk.Label(root, text="Filament Width (W):")
W_label.grid(row=6, column=2)
W_entry = tk.Entry(root)
W_entry.grid(row=6, column=3)

NumberofTurns_label = tk.Label(root, text="Number of Turns:")
NumberofTurns_label.grid(row=7, column=0)
NumberofTurns_entry = tk.Entry(root)
NumberofTurns_entry.grid(row=7, column=1)

NumberofLayers_label = tk.Label(root, text="Number of Layers:")
NumberofLayers_label.grid(row=7, column=2)
NumberofLayers_entry = tk.Entry(root)
NumberofLayers_entry.grid(row=7, column=3)

add_button = tk.Button(root, text="Add Point", command=add_point)
add_button.grid(row=8, column=0, sticky="ew", padx=30, pady=20)

circ_button = tk.Button(root, text="CIRC", command=lambda: select_motion_command("CIRC"))
circ_button.grid(row=8, column=1, sticky="ew", padx=30, pady=20)

clear_button = tk.Button(root, text="Clear All", command=clear_all)
clear_button.grid(row=8, column=2, sticky="ew", padx=30, pady=20)

auto_button = tk.Button(root, text="Automate", command=automate)
auto_button.grid(row=8, column=3, sticky="ew", padx=30, pady=20)

output_text = tk.Text(root, height=10, width=80)
output_text.grid(row=9, column=0, columnspan=4, padx=20)

export_button = tk.Button(root, text="Export KRL Code", command=save_krl_code)
export_button.grid(row=11, column=0, columnspan=4, pady=10)

import_button = tk.Button(root, text="Import Points", command=import_points)
import_button.grid(row=10, column=4)

save_button = tk.Button(root, text="Save Points", command=save_points)
save_button.grid(row=9, column=4, pady=10)

# Create a button to open the commentary popup
commentary_button = tk.Button(root, text="Add Commentary", command=open_commentary_popup)
commentary_button.grid(row=10, column=3, pady=10)

# Create a button to open the approach popup
approach_button = tk.Button(root, text="Add Approach", command=open_approach_popup)
approach_button.grid(row=11, column=3, pady=10)

# Create a variable to store the selected file format
file_format_var = tk.StringVar(value="KRL (.src)")

# Radio buttons for selecting file format
src_radio = tk.Radiobutton(root, text="KRL (.src)", variable=file_format_var, value="KRL (.src)")
src_radio.grid(row=10, column=1, sticky="w")

txt_radio = tk.Radiobutton(root, text="Text (.txt)", variable=file_format_var, value="Text (.txt)")
txt_radio.grid(row=10, column=2, sticky="w")

canvas_label = tk.Label(root, text="Canvas For Visual Representation")
canvas_label.grid(row=0, column=4, columnspan=4)

canvas = tk.Canvas(root, width=canvas_width, height=canvas_height, bg="white")
canvas.grid(row=1, rowspan=3, column=4, padx=10, pady=10)

# Add a vertical scrollbar
v_scrollbar = tk.Scrollbar(root, orient=tk.VERTICAL, command=canvas.yview)
v_scrollbar.grid(row=1, rowspan=3, column=5, sticky='ns')

# Add a horizontal scrollbar
h_scrollbar = tk.Scrollbar(root, orient=tk.HORIZONTAL, command=canvas.xview)
h_scrollbar.grid(row=4, column=4, sticky='ew')

# Configure the canvas to use the scrollbars
canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

# Add a Alternate layers checkbox
alternate_layer_direction_var = tk.BooleanVar(value=True)

alternate_checkbox = tk.Checkbutton(root, text="Alternate Layer Direction", variable=alternate_layer_direction_var)
alternate_checkbox.grid(row=9, column=5, columnspan=2, padx=10, pady=5)

# after you create your approach_button:
generate_button = tk.Button(root, text="Auto‑Generate Base", command=open_generate_popup)
generate_button.grid(row=8, column=5, padx=10, pady=20)



root.mainloop()