import tkinter as tk

def calculate_cuboid(event=None):
    try:
        # Get values from entry fields
        filament_thickness = float(entry_filament_height.get())  # Swap with filament_height
        num_turns = int(entry_num_turns.get())
        layer_height = float(entry_filament_thickness.get())  # Swap with filament_thickness
        num_layers = int(entry_num_layers.get())
        
        # Get dimensions of the cuboid
        x_dimension = float(entry_x_dimension.get())
        y_dimension = float(entry_y_dimension.get())
        z_dimension = float(entry_z_dimension.get())
        
        # Calculate width/depth of walls
        wall_width_depth = filament_thickness * num_turns
        
        # Calculate total height of cuboid
        total_height = layer_height * num_layers
        
        # Get radius of rounded corners
        corner_radius = float(entry_corner_radius.get())
        
        # Validate corner radius
        if corner_radius <= 0:
            raise ValueError("Corner radius must be greater than zero")
        elif corner_radius > min(x_dimension, y_dimension) / 2:
            raise ValueError("Corner radius is too large")
        
        # Update result label
        result_label.config(text=f"Width/Depth of Walls: {wall_width_depth} mm\nTotal Height of Cuboid: {total_height} mm")
        
        # Update visual illustration
        update_visual(wall_width_depth, total_height, x_dimension, y_dimension, z_dimension, corner_radius)
    except ValueError as e:
        result_label.config(text=str(e))

# Other functions remain unchanged

# Create main window
root = tk.Tk()
root.title("3D Printed Cuboid Calculator")

# Create entry fields for input values
label_filament_height = tk.Label(root, text="Filament Height (mm):")  # Updated label
label_filament_height.grid(row=0, column=0)  # Updated position
entry_filament_height = tk.Entry(root)
entry_filament_height.grid(row=0, column=1)

label_num_turns = tk.Label(root, text="Number of Turns:")
label_num_turns.grid(row=1, column=0)
entry_num_turns = tk.Entry(root)
entry_num_turns.grid(row=1, column=1)

label_filament_thickness = tk.Label(root, text="Filament/Layer Height (mm):")  # Updated label
label_filament_thickness.grid(row=2, column=0)  # Updated position
entry_filament_thickness = tk.Entry(root)
entry_filament_thickness.grid(row=2, column=1)

# Add entry fields for dimensions
label_x_dimension = tk.Label(root, text="X Dimension (cm):")
label_x_dimension.grid(row=3, column=0)
entry_x_dimension = tk.Entry(root)
entry_x_dimension.grid(row=3, column=1)

label_y_dimension = tk.Label(root, text="Y Dimension (cm):")
label_y_dimension.grid(row=4, column=0)
entry_y_dimension = tk.Entry(root)
entry_y_dimension.grid(row=4, column=1)

label_z_dimension = tk.Label(root, text="Z Dimension (cm):")
label_z_dimension.grid(row=5, column=0)
entry_z_dimension = tk.Entry(root)
entry_z_dimension.grid(row=5, column=1)

# Add entry field for Number of Layers
label_num_layers = tk.Label(root, text="Number of Layers:")
label_num_layers.grid(row=6, column=0)
entry_num_layers = tk.Entry(root)
entry_num_layers.grid(row=6, column=1)

# Add entry field for Corner Radius
label_corner_radius = tk.Label(root, text="Corner Radius (cm):")
label_corner_radius.grid(row=7, column=0)
entry_corner_radius = tk.Entry(root)
entry_corner_radius.grid(row=7, column=1)

# Bind entry fields to calculate_cuboid function
entry_filament_height.bind("<KeyRelease>", calculate_cuboid)
entry_num_turns.bind("<KeyRelease>", calculate_cuboid)
entry_filament_thickness.bind("<KeyRelease>", calculate_cuboid)  # Updated binding
entry_x_dimension.bind("<KeyRelease>", calculate_cuboid)
entry_y_dimension.bind("<KeyRelease>", calculate_cuboid)
entry_z_dimension.bind("<KeyRelease>", calculate_cuboid)
entry_num_layers.bind("<KeyRelease>", calculate_cuboid)  # Added binding
entry_corner_radius.bind("<KeyRelease>", calculate_cuboid)  # Added binding

# Remaining GUI elements remain unchanged

# Run Tkinter event loop
root.mainloop()
