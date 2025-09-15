import tkinter as tk
from tkinter import messagebox, filedialog, PhotoImage
import os
import sys
import subprocess

# Counter for numbering the KRL codes
krl_counter = 1
# List to store the coordinates of the points
point_coordinates = []
# List to store the motion commands associated with each point
point_commands = []
# Variables to store the current position and increments
current_x = 0
current_y = 0
current_z = 0
# Define dummy_x and dummy_y as global variables
dummy_x = None
dummy_y = None
# Initial scaling factor
scaling_factor = 3
# Variable to store the selected motion command
selected_motion_command = "PTP"  # Default is PTP

def generate_krl_code(x, y, z, motion_command, velocity=None, velocity_unit=None, a=None, b=None, c=None):
    global krl_counter
    krl_code = ""

    # Generate KRL code based on the selected motion command and provided axes values
    krl_code += f"{motion_command} {{X {x}, Y {y}, Z {z},"
    if a is not None:
        krl_code += f" A {a},"
    if b is not None:
        krl_code += f" B {b},"
    if c is not None:
        krl_code += f" C {c}}}"
    if velocity is not None:
        krl_code += f" Vel={velocity} {velocity_unit}"  # Include velocity unit
    krl_code += "\n"
    krl_counter += 1
    return krl_code



def validate_coordinates(x, y, z):
    try:
        x = float(x)
        y = float(y)
        z = float(z)
        return True
    except ValueError:
        return False

def update_krl_code():
    global current_x, current_y, current_z, dummy_x, dummy_y

    # Validate input coordinates
    x = x_entry.get()
    y = y_entry.get()
    z = z_entry.get()
    if not validate_coordinates(x, y, z):
        messagebox.showwarning("Invalid Input", "Please enter valid numerical values for X, Y, and Z coordinates.")
        return

    # Initialize dummy coordinates if not defined
    if dummy_x is None or dummy_y is None:
        dummy_x, dummy_y = current_x, current_y

    # Check if increments or direct coordinates are provided
    if x_increment_entry.get() and y_increment_entry.get() and z_increment_entry.get():
        # Get the increments from the input fields
        increment_x = float(x_increment_entry.get())
        increment_y = float(y_increment_entry.get())
        increment_z = float(z_increment_entry.get())
        # Calculate the new coordinates by adding increments
        current_x += increment_x
        current_y += increment_y
        current_z += increment_z
    else:
        # Get the coordinates directly
        current_x = float(x_entry.get())
        current_y = float(y_entry.get())
        current_z = float(z_entry.get())

    # Get velocity for the current point, if provided
    velocity = velocity_entry.get()
    # Convert velocity to float if provided
    velocity_value = float(velocity) if velocity else None

    # Get velocity unit based on the selected radio button
    velocity_unit = velocity_unit_var.get()
    # Set the velocity unit string based on the selected radio button
    if velocity_unit == "percentage":
        velocity_unit_str = "%"
    elif velocity_unit == "m_s":
        velocity_unit_str = "m/s"
    else:
        velocity_unit_str = ""  # Default to empty string if none selected

    # Get values for A, B, and C axes
    a_value = a_entry.get()
    b_value = b_entry.get()
    c_value = c_entry.get()

    # Convert A, B, and C values to floats if they are provided
    a = float(a_value) if a_value else None
    b = float(b_value) if b_value else None
    c = float(c_value) if c_value else None

    # Generate KRL code for the current coordinates with the selected motion command, velocity, and velocity unit
    krl_code = generate_krl_code(current_x, current_y, current_z, selected_motion_command, velocity_value, velocity_unit_str, a, b, c)

    # Append the generated KRL code to the text widget
    output_text.insert(tk.END, krl_code)

    # Update the visualization on the canvas
    draw_point(current_x, current_y)
    if dummy_x is not None and dummy_y is not None:
        draw_line(dummy_x, dummy_y, current_x, current_y, selected_motion_command)  # Draw line from dummy to current

    # Store the current coordinates
    point_coordinates.append((current_x, current_y, current_z))
    point_commands.append(selected_motion_command)  # Store the selected motion command

    # Update the dummy coordinates
    dummy_x = current_x
    dummy_y = current_y

    # Update krl_code_without_init with the generated KRL code
    krl_code_without_init = generate_krl_code(current_x, current_y, current_z, selected_motion_command, velocity_value, velocity_unit_str, a, b, c)




def clear_all():
    global point_coordinates, point_commands, current_x, current_y, current_z, dummy_x, dummy_y

    # Clear all points and lines from the canvas
    canvas.delete("all")

    # Reset data structures
    point_coordinates = []
    point_commands = []
    current_x = 0
    current_y = 0
    current_z = 0
    dummy_x = None
    dummy_y = None

    # Update text widget to reflect cleared state
    output_text.delete("1.0", tk.END)

# Function to handle the input of points for CIRC and SPL commands
def input_points_for_command(motion_command):
    # Create a pop-up window to input points
    popup = tk.Toplevel(root)
    popup.title(f"Input Points for {motion_command} Command")

    a = float(a_entry.get())
    b = float(b_entry.get())
    c = float(c_entry.get())

    # Labels for Point 1
    point1_label = tk.Label(popup, text=f"Start Point:")
    point1_label.grid(row=0, column=0, padx=5, pady=5)
    x1_label = tk.Label(popup, text="X:")
    x1_label.grid(row=0, column=1)
    x1_entry = tk.Entry(popup)
    x1_entry.grid(row=0, column=2)
    y1_label = tk.Label(popup, text="Y:")
    y1_label.grid(row=0, column=3)
    y1_entry = tk.Entry(popup)
    y1_entry.grid(row=0, column=4)
    z1_label = tk.Label(popup, text="Z:")
    z1_label.grid(row=0, column=5)
    z1_entry = tk.Entry(popup)
    z1_entry.grid(row=0, column=6)

    # Set the default values for Point 1 (if available)
    if point_coordinates:
        x1_entry.insert(0, str(point_coordinates[-1][0]))
        y1_entry.insert(0, str(point_coordinates[-1][1]))
        z1_entry.insert(0, str(point_coordinates[-1][2]))

    # Labels for Middle Point
    middle_label = tk.Label(popup, text="Middle Point:")
    middle_label.grid(row=1, column=0, padx=5, pady=5)
    x_middle_label = tk.Label(popup, text="X:")
    x_middle_label.grid(row=1, column=1)
    x_middle_entry = tk.Entry(popup)
    x_middle_entry.grid(row=1, column=2)
    y_middle_label = tk.Label(popup, text="Y:")
    y_middle_label.grid(row=1, column=3)
    y_middle_entry = tk.Entry(popup)
    y_middle_entry.grid(row=1, column=4)
    z_middle_label = tk.Label(popup, text="Z:")
    z_middle_label.grid(row=1, column=5)
    z_middle_entry = tk.Entry(popup)
    z_middle_entry.grid(row=1, column=6)

    # Labels for Point 3
    point3_label = tk.Label(popup, text=f"End Point:")
    point3_label.grid(row=2, column=0, padx=5, pady=5)
    x3_label = tk.Label(popup, text="X:")
    x3_label.grid(row=2, column=1)
    x3_entry = tk.Entry(popup)
    x3_entry.grid(row=2, column=2)
    y3_label = tk.Label(popup, text="Y:")
    y3_label.grid(row=2, column=3)
    y3_entry = tk.Entry(popup)
    y3_entry.grid(row=2, column=4)
    z3_label = tk.Label(popup, text="Z:")
    z3_label.grid(row=2, column=5)
    z3_entry = tk.Entry(popup)
    z3_entry.grid(row=2, column=6)

    # Function to handle the input
    def ok_click():
        # Get the input values
        x1 = x1_entry.get()
        y1 = y1_entry.get()
        z1 = z1_entry.get()
        x_middle = x_middle_entry.get()
        y_middle = y_middle_entry.get()
        z_middle = z_middle_entry.get()
        x3 = x3_entry.get()
        y3 = y3_entry.get()
        z3 = z3_entry.get()
        # Validate the input
        if x1 and y1 and z1 and x_middle and y_middle and z_middle and x3 and y3 and z3:
            try:
                # Convert input values to floats
                x1 = float(x1)
                y1 = float(y1)
                z1 = float(z1)
                x_middle = float(x_middle)
                y_middle = float(y_middle)
                z_middle = float(z_middle)
                x3 = float(x3)
                y3 = float(y3)
                z3 = float(z3)
                # Generate the KRL code
                krl_code = f"{motion_command} {{X {x_middle}, Y {y_middle}, Z {z_middle}}},{{X {x3}, Y {y3}, Z {z3}, A {a}, B {b}, C {c}}}"
                # Append the KRL code to the output text widget
                output_text.insert(tk.END, krl_code + "\n")
                # Draw a red point at the middle point
                draw_point(x_middle, y_middle, color="red")
                # Draw a red point at the last point
                draw_point(x3, y3, color="red")
                # If the command is CIRC, draw a curve between the last two points
                if motion_command == "CIRC" and len(point_coordinates) > 0:
                    # Get the coordinates of the last point
                    x0, y0, _ = point_coordinates[-1]
                    # Draw a curve between the last two points
                    draw_curve(x0, y0, x1, y1, x_middle, y_middle, x3, y3, selected_motion_command)
                    # Add a dummy point at the end of the curve
                    global dummy_x, dummy_y
                    dummy_x = x3
                    dummy_y = y3
                    draw_point(dummy_x, dummy_y, color="red")  # Draw a red point for the dummy point
                # Close the pop-up window
                popup.destroy()
            except ValueError:
                tk.messagebox.showwarning("Invalid Input", "Please enter valid numerical values for coordinates.")
        else:
            # If any of the fields are empty, show a warning message
            tk.messagebox.showwarning("Missing Input", "Please enter values for all points.")

    # Button to confirm the input
    ok_button = tk.Button(popup, text="OK", command=ok_click)
    ok_button.grid(row=3, column=0, columnspan=7)


# Function to draw a curve between the last two points
def draw_curve(x0, y0, x1, y1, x2, y2, x3, y3, motion_command, color="green"):
    # Apply scaling factor to the coordinates
    scaled_x0 = x0 * scaling_factor
    scaled_y0 = y0 * scaling_factor
    scaled_x1 = x1 * scaling_factor
    scaled_y1 = y1 * scaling_factor
    scaled_x2 = x2 * scaling_factor
    scaled_y2 = y2 * scaling_factor
    scaled_x3 = x3 * scaling_factor
    scaled_y3 = y3 * scaling_factor

    # Draw a Bezier curve on the canvas
    canvas.create_line(scaled_x0, scaled_y0, scaled_x1, scaled_y1, scaled_x2, scaled_y2, scaled_x3, scaled_y3, fill=color)
    
    # Calculate the midpoint of the curve
    midpoint_x = (scaled_x0 + 3 * scaled_x1 + 3 * scaled_x2 + scaled_x3) / 8
    midpoint_y = (scaled_y0 + 3 * scaled_y1 + 3 * scaled_y2 + scaled_y3) / 8
    
    # Display the motion command type above the curve
    canvas.create_text(midpoint_x, midpoint_y, text=motion_command, fill="black", anchor='n')
    
    # Update the scroll region
    update_scroll_region()


# Function to handle the selection of motion commands
def select_motion_command(motion_command):
    global selected_motion_command
    selected_motion_command = motion_command
    # If the selected command is CIRC or SPL, prompt the user to input points
    if motion_command in ["CIRC"]:
        input_points_for_command(motion_command)
    elif motion_command in ["SPL"]:
        messagebox.showinfo("Experimental Feature", "SPLINE Function is still experimental and in development.\n\nNot Currently Accessible.")


def draw_point(x, y, color="red"):
    # Apply scaling factor to the coordinates
    scaled_x = x * scaling_factor
    scaled_y = y * scaling_factor
    
    # Draw a point on the canvas
    canvas.create_oval(scaled_x - 2, scaled_y - 2, scaled_x + 2, scaled_y + 2, fill=color)
    update_scroll_region()

def draw_line(x1, y1, x2, y2, motion_command):
    # Apply scaling factor to the coordinates
    scaled_x1 = x1 * scaling_factor
    scaled_y1 = y1 * scaling_factor
    scaled_x2 = x2 * scaling_factor
    scaled_y2 = y2 * scaling_factor
    
    # Draw a line between two points on the canvas
    canvas.create_line(scaled_x1, scaled_y1, scaled_x2, scaled_y2, fill="blue")
    
    # Calculate the midpoint of the line
    midpoint_x = (scaled_x1 + scaled_x2) / 2
    midpoint_y = (scaled_y1 + scaled_y2) / 2
    
    # Display the motion command type above the line
    canvas.create_text(midpoint_x, midpoint_y, text=motion_command, fill="black", anchor='n')

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
; Define base and tool
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

root = tk.Tk()
root.title("Dynamic KRL Code Generator")

def go_back_to_selector():
    try:
        selector_script = os.path.join(os.path.dirname(__file__), 'Main_Window_Program_Selector_.py')
        if os.path.exists(selector_script):
            subprocess.Popen([sys.executable, selector_script])
        else:
            messagebox.showwarning("Not Found", "Main_Window_Program_Selector_.py was not found.")
    except Exception as ex:
        messagebox.showerror("Error", f"Failed to open selector: {ex}")
    finally:
        root.destroy()

# Default values
default_increment = 0
default_ori = 180
tool_z = 125

# Back button at far left; title centered above inputs (columns 1–3)
back_btn = tk.Button(root, text="← Back", command=go_back_to_selector)
back_btn.grid(row=0, column=0, sticky="w", padx=(0, 10))

for col_idx in (1, 2, 3):
    try:
        root.grid_columnconfigure(col_idx, weight=1)
    except Exception:
        pass

# Label specifying the input type
input_label = tk.Label(root, text="Input your points (Only use for PTP and LIN)")
input_label.grid(row=0, column=1, columnspan=3, sticky="n")

# Input fields for X, Y, Z coordinates
x_label = tk.Label(root, text="X:")
x_label.grid(row=1, column=0)
x_entry = tk.Entry(root)
x_entry.insert(0, default_increment)
x_entry.grid(row=1, column=1)

y_label = tk.Label(root, text="Y:")
y_label.grid(row=2, column=0)
y_entry = tk.Entry(root)
y_entry.insert(0, default_increment)
y_entry.grid(row=2, column=1)

z_label = tk.Label(root, text="Z:")
z_label.grid(row=3, column=0)
z_entry = tk.Entry(root)
z_entry.insert(0, tool_z)
z_entry.grid(row=3, column=1)

# Input fields for X, Y, Z increments
x_increment_label = tk.Label(root, text="X Increment:")
x_increment_label.grid(row=1, column=2)
x_increment_entry = tk.Entry(root)
x_increment_entry.grid(row=1, column=3)

y_increment_label = tk.Label(root, text="Y Increment:")
y_increment_label.grid(row=2, column=2)
y_increment_entry = tk.Entry(root)
y_increment_entry.grid(row=2, column=3)

z_increment_label = tk.Label(root, text="Z Increment:")
z_increment_label.grid(row=3, column=2)
z_increment_entry = tk.Entry(root)
z_increment_entry.grid(row=3, column=3)

# Label specifying the default motion command
motion_label = tk.Label(root, text="Specify Axes Orientaion")
motion_label.grid(row=4, column=0, columnspan=4)

# Add entry fields for A, B, and C axes to the GUI

a_label = tk.Label(root, text="A:")
a_label.grid(row=5, column=0)
a_entry = tk.Entry(root)
a_entry.insert(0, default_ori)
a_entry.grid(row=5, column=1)

b_label = tk.Label(root, text="B:")
b_label.grid(row=5, column=2)
b_entry = tk.Entry(root)
b_entry.insert(0, default_increment)
b_entry.grid(row=5, column=3)

c_label = tk.Label(root, text="C:")
c_label.grid(row=6, column=0)
c_entry = tk.Entry(root)
c_entry.insert(0, default_ori)
c_entry.grid(row=6, column=1)

# Label and entry for velocity input
velocity_label = tk.Label(root, text="Velocity:")
velocity_label.grid(row=6, column=2)
velocity_entry = tk.Entry(root)
velocity_entry.grid(row=6, column=3)

# Radio buttons for selecting velocity unit
velocity_unit_label = tk.Label(root, text="Velocity Unit:")
velocity_unit_label.grid(row=6, column=4)
velocity_unit_var = tk.StringVar(value="percentage")  # Default to percentage
percentage_radio = tk.Radiobutton(root, text="%", variable=velocity_unit_var, value="percentage")
percentage_radio.grid(row=5, column=5)
m_s_radio = tk.Radiobutton(root, text="m/s", variable=velocity_unit_var, value="m_s")
m_s_radio.grid(row=6, column=5)


# Label spacing
motion_label = tk.Label(root, text="_____________________________________________________________________________________________________________")
motion_label.grid(row=7, column=0, columnspan=4)

# Label specifying the default motion command
motion_label = tk.Label(root, text="Specify Motion Command (Default PTP)")
motion_label.grid(row=8, column=0, columnspan=4)

# Buttons to select motion commands
button_width = 10  # Set the width for all buttons
ptp_button = tk.Button(root, text="PTP", command=lambda: select_motion_command("PTP"), width=button_width)
ptp_button.grid(row=9, column=0)

lin_button = tk.Button(root, text="LIN", command=lambda: select_motion_command("LIN"), width=button_width)
lin_button.grid(row=9, column=1)

circ_button = tk.Button(root, text="CIRC", command=lambda: select_motion_command("CIRC"), width=button_width)
circ_button.grid(row=9, column=2)

spl_button = tk.Button(root, text="SPL", command=lambda: select_motion_command("SPL"), width=button_width)
spl_button.grid(row=9, column=3)

# Button to update KRL code
update_button = tk.Button(root, text="Update KRL Code", command=update_krl_code)
update_button.grid(row=10, column=0, columnspan=2, pady=10)

# Button to clear all
clear_all_button = tk.Button(root, text="Clear All", command=clear_all)
clear_all_button.grid(row=10, column=2, columnspan=2, pady=10)

# Create a button to open the commentary popup
commentary_button = tk.Button(root, text="Add Commentary", command=open_commentary_popup)
commentary_button.grid(row=11, column=5, pady=10)

# Text widget to display generated KRL code
output_text = tk.Text(root, height=10, width=65)
output_text.grid(row=11, columnspan=4)

# Create a button to save the KRL code
save_button = tk.Button(root, text="Export KRL Code", command=save_krl_code)
save_button.grid(row=13, column=0, columnspan=4, pady=10)

# Create a variable to store the selected file format
file_format_var = tk.StringVar(value="KRL (.src)")

# Radio buttons for selecting file format
src_radio = tk.Radiobutton(root, text="KRL (.src)", variable=file_format_var, value="KRL (.src)")
src_radio.grid(row=12, column=1, sticky="w")

txt_radio = tk.Radiobutton(root, text="Text (.txt)", variable=file_format_var, value="Text (.txt)")
txt_radio.grid(row=12, column=2, sticky="w")

# Canvas for visualization
canvas_label = tk.Label(root, text="Canvas For Visual Representation")
canvas_label.grid(row=0, column=6, columnspan=4)

canvas = tk.Canvas(root, width=400, height=300, bg="white")
canvas.grid(row=1, rowspan=3, column=6, padx=10, pady=10)

# Add a vertical scrollbar
v_scrollbar = tk.Scrollbar(root, orient=tk.VERTICAL, command=canvas.yview)
v_scrollbar.grid(row=1, rowspan=3, column=7, sticky='ns')

# Add a horizontal scrollbar
h_scrollbar = tk.Scrollbar(root, orient=tk.HORIZONTAL, command=canvas.xview)
h_scrollbar.grid(row=4, column=6, sticky='ew')

# Configure the canvas to use the scrollbars
canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

root.mainloop()

