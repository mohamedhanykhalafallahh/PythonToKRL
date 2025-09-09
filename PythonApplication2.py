import tkinter as tk

def generate_krl_code_for_layer(layer_coordinates):
    krl_code = ""
    for coord in layer_coordinates:
        # Generate KRL code for moving to the next coordinate
        krl_code += f"PTP X{coord[0]} Y{coord[1]} Z{coord[2]} ;\n"
    return krl_code

def generate_krl_code():
    shape_coordinates = []
    for entry in coordinate_entries:
        try:
            x, y, z = map(float, entry.get().split())
            shape_coordinates.append((x, y, z))
        except ValueError:
            output_text.config(text="Invalid input. Please enter coordinates in the format 'X Y Z'")
            return

    shape_krl_code = generate_krl_code_for_layer(shape_coordinates)
    output_text.config(text=shape_krl_code)

def add_coordinate_entry():
    new_entry = tk.Entry(input_frame)
    new_entry.grid(row=len(coordinate_entries) + 2, column=0, columnspan=4, padx=5, pady=5, sticky="ew")
    coordinate_entries.append(new_entry)

root = tk.Tk()
root.title("KRL Code Generator")

coordinate_entries = []

input_frame = tk.Frame(root)
input_frame.grid(row=0, column=0, padx=10, pady=10)

output_frame = tk.Frame(root)
output_frame.grid(row=0, column=1, padx=10, pady=10)

instruction_label = tk.Label(input_frame, text="Enter coordinates for the shape (X Y Z), one coordinate per line:")
instruction_label.grid(row=0, column=0, columnspan=4, padx=5, pady=5)

add_entry_button = tk.Button(input_frame, text="Add Coordinate Entry", command=add_coordinate_entry)
add_entry_button.grid(row=1, column=0, columnspan=2, padx=5, pady=5)

generate_button = tk.Button(input_frame, text="Generate KRL Code", command=generate_krl_code)
generate_button.grid(row=1, column=2, columnspan=2, padx=5, pady=5)

output_label = tk.Label(output_frame, text="Generated KRL Code:")
output_label.grid(row=0, column=0, padx=5, pady=5)

output_text = tk.Label(output_frame, text="", justify="left", wraplength=400)
output_text.grid(row=1, column=0, padx=5, pady=5)

add_coordinate_entry()

root.mainloop()
