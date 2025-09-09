import tkinter as tk
from tkinter import messagebox

# Counter for numbering the KRL codes
krl_counter = 1
# List to store the coordinates of the points
point_coordinates = []
# Variables to store the current position and increments
current_x = 0
current_y = 0
current_z = 0

def generate_krl_code(x, y, z):
    global krl_counter
    # Generate KRL code for moving to the specified coordinate
    krl_code = f"Point {krl_counter}: PTP X{x} Y{y} Z{z} ;\n"
    krl_counter += 1
    return krl_code

def update_krl_code():
    global current_x, current_y, current_z
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
    # Generate KRL code for the current coordinates
    krl_code = generate_krl_code(current_x, current_y, current_z)
    # Append the generated KRL code to the text widget
    output_text.insert(tk.END, krl_code)
    # Update the visualization on the canvas
    draw_point(current_x, current_y)
    if len(point_coordinates) > 0:
        draw_line(point_coordinates[-1][0], point_coordinates[-1][1], current_x, current_y)
    point_coordinates.append((current_x, current_y))
    adjust_canvas_scale()

def undo_last_point():
    global krl_counter, current_x, current_y, current_z
    if len(point_coordinates) > 1:  # Ensure there is at least one point left after deletion
        # Remove the last point from the list of coordinates
        last_point = point_coordinates.pop()
        # Decrement the counter
        krl_counter -= 1
        # Update current position to the coordinates of the last point in the list
        if point_coordinates:
            current_x, current_y = point_coordinates[-1]
        # Clear the canvas
        canvas.delete("all")
        # Redraw all points and lines up to the last one
        for i in range(len(point_coordinates)):
            draw_point(point_coordinates[i][0], point_coordinates[i][1])
            if i < len(point_coordinates) - 1:
                draw_line(point_coordinates[i][0], point_coordinates[i][1], point_coordinates[i+1][0], point_coordinates[i+1][1])
        # Update the canvas scaling
        adjust_canvas_scale()
        
        # Rebuild the entire KRL code
        krl_code = ""
        for i, (x, y) in enumerate(point_coordinates, start=1):
            krl_code += f"Point {i}: PTP X{x} Y{y} Z0 ;\n"
        # Update the text widget with the new KRL code
        output_text.delete("1.0", tk.END)
        output_text.insert(tk.END, krl_code)
    else:
        # Cannot delete the origin point
        messagebox.showwarning("Cannot Undo", "Cannot delete the origin point.")



def draw_point(x, y):
    # Draw a point on the canvas
    canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="red")

def draw_line(x1, y1, x2, y2):
    # Draw a line between two points on the canvas
    canvas.create_line(x1, y1, x2, y2, fill="blue")

def adjust_canvas_scale():
    # Adjust the scaling of the canvas to fit all points within the visible area
    min_x = min(point[0] for point in point_coordinates)
    min_y = min(point[1] for point in point_coordinates)
    max_x = max(point[0] for point in point_coordinates)
    max_y = max(point[1] for point in point_coordinates)
    canvas.config(scrollregion=(min_x - 10, min_y - 10, max_x + 10, max_y + 10))

root = tk.Tk()
root.title("Dynamic KRL Code Generator")

# Default values
default_increment = 0

# Input fields for X, Y, Z coordinates
x_label = tk.Label(root, text="X:")
x_label.grid(row=0, column=0)
x_entry = tk.Entry(root)
x_entry.insert(0, default_increment)
x_entry.grid(row=0, column=1)

y_label = tk.Label(root, text="Y:")
y_label.grid(row=1, column=0)
y_entry = tk.Entry(root)
y_entry.insert(0, default_increment)
y_entry.grid(row=1, column=1)

z_label = tk.Label(root, text="Z:")
z_label.grid(row=2, column=0)
z_entry = tk.Entry(root)
z_entry.insert(0, default_increment)
z_entry.grid(row=2, column=1)

# Input fields for X, Y, Z increments
x_increment_label = tk.Label(root, text="X Increment:")
x_increment_label.grid(row=0, column=2)
x_increment_entry = tk.Entry(root)
x_increment_entry.grid(row=0, column=3)

y_increment_label = tk.Label(root, text="Y Increment:")
y_increment_label.grid(row=1, column=2)
y_increment_entry = tk.Entry(root)
y_increment_entry.grid(row=1, column=3)

z_increment_label = tk.Label(root, text="Z Increment:")
z_increment_label.grid(row=2, column=2)
z_increment_entry = tk.Entry(root)
z_increment_entry.grid(row=2, column=3)

# Button to update KRL code
update_button = tk.Button(root, text="Update KRL Code", command=update_krl_code)
update_button.grid(row=3, columnspan=2)

# Button to undo last point
undo_button = tk.Button(root, text="Undo Last Point", command=undo_last_point)
undo_button.grid(row=3, column=2, columnspan=2)

# Text widget to display generated KRL code
output_text = tk.Text(root, height=10, width=40)
output_text.grid(row=4, columnspan=4)

# Canvas for visualization
canvas = tk.Canvas(root, width=400, height=300, bg="white")
canvas.grid(row=0, rowspan=4, column=4, padx=10, pady=10)

root.mainloop()
