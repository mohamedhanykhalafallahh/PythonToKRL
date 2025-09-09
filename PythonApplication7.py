import tkinter as tk
from tkinter import messagebox

def generate_krl_code(radius):
    # Calculate end points based on the radius
    end_point_x = radius  # X-coordinate of the end point
    end_point_y = 0       # Y-coordinate of the end point

    # Calculate direction vector (perpendicular to the plane of the circle)
    direction_x = 0
    direction_y = 0
    direction_z = 1

    # Simple KRL code template to draw a circle
    krl_code = f"""
    ; Move to start point (rightmost point of the circle)
    LIN {radius}, 0, 0

    ; Draw the circle using CIRC command
    CIRC_REL {end_point_x}, {end_point_y}, 0, {direction_x}, {direction_y}, {direction_z}
    """
    return krl_code


def draw_circle():
    try:
        radius = float(entry.get())
        if radius <= 0:
            raise ValueError("The radius must be positive.")
        canvas.delete("all")
        canvas.create_oval(
            canvas_width/2 - radius, canvas_height/2 - radius,
            canvas_width/2 + radius, canvas_height/2 + radius,
            outline="black", width=2
        )
        # Generate KRL code and display it
        krl_code = generate_krl_code(radius)
        krl_text.delete("1.0", tk.END)
        krl_text.insert(tk.END, krl_code)
    except ValueError as e:
        messagebox.showerror("Invalid Input", str(e))

# Create the main window
root = tk.Tk()
root.title("Circle Drawer")

# Create and place the input field
tk.Label(root, text="Enter the radius of the circle:").pack(pady=10)
entry = tk.Entry(root)
entry.pack(pady=5)

# Create and place the draw button
draw_button = tk.Button(root, text="Draw Circle", command=draw_circle)
draw_button.pack(pady=10)

# Create and place the canvas
canvas_width = 400
canvas_height = 400
canvas = tk.Canvas(root, width=canvas_width, height=canvas_height, bg="white")
canvas.pack(pady=20)

# Create and place the text widget to display KRL code
krl_text = tk.Text(root, height=10, width=50)
krl_text.pack(pady=10)

# Run the application
root.mainloop()
