import tkinter as tk
from tkinter import PhotoImage, messagebox
import os

def open_sub_program(program_type):
    if program_type == "Cuboid":
        os.system(r"D:\University\Python\python.exe C:/Users/moham/source/repos/PythonApplication6/PythonApplication6.py")
    elif program_type == "Cylindrical":
        messagebox.showinfo("Experimental Feature", "Cylindrical program is still experimental and in development.")
    elif program_type == "Free form":
        os.system(r"D:\University\Python\python.exe C:/Users/moham/source/repos/PythonApplication5/PythonApplication5.py")
        
    else:
        messagebox.showerror("Error", "Invalid program type selected.")


# Create the main window
root = tk.Tk()
root.title("Program Selector")

# Function to handle button clicks
def button_click(program_type):
    open_sub_program(program_type)

# Load program images
cuboid_image = PhotoImage(file="cuboid_image.png")
cylindrical_image = PhotoImage(file="cylinderical_image.png")
free_form_image = PhotoImage(file="free_form_image.png")

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
cuboid_button = tk.Button(root, image=cuboid_image, command=lambda: button_click("Cuboid"))
cuboid_button.grid(row=4, column=0, padx=10, pady=10)

cylindrical_button = tk.Button(root, image=cylindrical_image, command=lambda: button_click("Cylindrical"))
cylindrical_button.grid(row=4, column=1, padx=10, pady=10)

free_form_button = tk.Button(root, image=free_form_image, command=lambda: button_click("Free form"))
free_form_button.grid(row=4, column=2, padx=10, pady=10)

# Label specifying the default motion command
motion_label = tk.Label(root, text="_____________________________________________________________________________________________________________")
motion_label.grid(row=5, column=0, columnspan=4)

# Create a PhotoImage object from an image file
image_path = "C:/Users/moham/source/repos/PythonApplication5/KUKAPIC.png"
image = PhotoImage(file=image_path)

# Create a Label widget to display the image
image_label = tk.Label(root, image=image)
image_label.grid(row=6, rowspan=8, column=1, padx=10, pady=10)

# Execute the Tkinter event loop
root.mainloop()
