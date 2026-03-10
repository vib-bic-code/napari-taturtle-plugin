from magicgui import magicgui
from PyQt5.QtWidgets import QApplication, QFormLayout, QLabel, QVBoxLayout, QWidget

# Define the function with magicgui
@magicgui(auto_call=False)
def enable_crop_widget2(do_crop: bool = False):
    pass

# Create a Qt application
app = QApplication([])

# Create an instance of the FunctionGui widget
enable_crop_gui = enable_crop_widget2()

# Create a main widget and layout
main_widget = QWidget()
layout = QVBoxLayout()

# Create a form layout
form_layout = QFormLayout()

# Access the native widget of the FunctionGui
enable_crop_widget = enable_crop_gui.native

# Add the FunctionGui to the form layout using the native widget
form_layout.addRow(QLabel('Crop'), enable_crop_widget)

# Add the form layout to the main layout
layout.addLayout(form_layout)

# Set the layout for the main widget
main_widget.setLayout(layout)

# Show the main widget
main_widget.show()

# Run the application
app.exec_()
