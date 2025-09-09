import tkinter as tk
from tkinter import PhotoImage, messagebox
import os
import sys
import subprocess
from pathlib import Path


def resource_path(relative_name):
    base_path = Path(__file__).resolve().parent
    return str(base_path / relative_name)


def open_sub_program(program_type):
    try:
        if program_type == "Cuboid":
            script = resource_path("PythonApplication6.py")
            subprocess.Popen([sys.executable, script], shell=False)
        elif program_type == "Cylindrical":
            messagebox.showinfo("Experimental Feature", "Cylindrical program is still experimental and in development.")
        elif program_type == "Free form":
            script = resource_path("PythonApplication5.py")
            if os.path.exists(script):
                subprocess.Popen([sys.executable, script], shell=False)
            else:
                messagebox.showinfo("Unavailable", "Free form program is not available in this repository.")
        else:
            messagebox.showerror("Error", "Invalid program type selected.")
    except Exception as e:
        messagebox.showerror("Launch Error", f"Failed to launch program: {e}")


# Create the main window
root = tk.Tk()
root.title("Program Selector")

# Function to handle button clicks
def button_click(program_type):
    open_sub_program(program_type)


def load_image_safe(filename):
    try:
        path = resource_path(filename)
        return PhotoImage(file=path)
    except Exception:
        # Fallback: create a tiny transparent image placeholder
        try:
            # 1x1 transparent GIF via base64 is not supported by PhotoImage directly without base64 decode,
            # so return None and let the button use text fallback.
            return None
        except Exception:
            return None

# Load program images (relative paths with graceful fallback)
cuboid_image = load_image_safe("cuboid_image.png")
cylindrical_image = load_image_safe("cylinderical_image.png")
free_form_image = load_image_safe("free_form_image.png")

# Add a centered title label
title_label = tk.Label(root, text="Welcome to the KRL Generator", font=("Arial", 16, "bold"))
title_label.grid(row=0, columnspan=3)

# Add a label asking users to choose their desired program
instruction_label = tk.Label(root, text="Please choose your desired program:", font=("Arial", 12))
instruction_label.grid(row=1, columnspan=3)

# Label specifying the default motion command
motion_label = tk.Label(root, text="_____________________________________________________________________________________________________________")
motion_label.grid(row=2, column=0, columnspan=4)

# Add labels for each button
cuboid_label = tk.Label(root, text="Cuboidal", font=("Arial", 12))
cuboid_label.grid(row=3, column=0)

cylindrical_label = tk.Label(root, text="Cylindrical", font=("Arial", 12))
cylindrical_label.grid(row=3, column=1)

free_form_label = tk.Label(root, text="Free form", font=("Arial", 12))
free_form_label.grid(row=3, column=2)

# Create buttons for program selection
cuboid_button = tk.Button(root, image=cuboid_image if cuboid_image else None, text=("Cuboid" if cuboid_image is None else ""), command=lambda: button_click("Cuboid"))
cuboid_button.grid(row=4, column=0, padx=10, pady=10)

cylindrical_button = tk.Button(root, image=cylindrical_image if cylindrical_image else None, text=("Cylindrical" if cylindrical_image is None else ""), command=lambda: button_click("Cylindrical"))
cylindrical_button.grid(row=4, column=1, padx=10, pady=10)

free_form_button = tk.Button(root, image=free_form_image if free_form_image else None, text=("Free form" if free_form_image is None else ""), command=lambda: button_click("Free form"))
free_form_button.grid(row=4, column=2, padx=10, pady=10)

# Label specifying the default motion command
motion_label = tk.Label(root, text="_____________________________________________________________________________________________________________")
motion_label.grid(row=5, column=0, columnspan=4)

# Create a PhotoImage object from an image file (splash)
splash = load_image_safe("KUKAPIC.png")

# Create a Label widget to display the image (or text fallback)
if splash:
    image_label = tk.Label(root, image=splash)
else:
    image_label = tk.Label(root, text="KUKA", font=("Arial", 24, "bold"))
image_label.grid(row=6, rowspan=8, column=1, padx=10, pady=10)

# Execute the Tkinter event loop
root.mainloop()
