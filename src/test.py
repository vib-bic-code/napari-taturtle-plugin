import sys

from qtpy.QtCore import *
from qtpy.QtGui import *
from qtpy.QtWidgets import QApplication, QWidget, QLabel, QLineEdit, QFormLayout, \
    QVBoxLayout, QHBoxLayout, QPushButton, QRadioButton, QButtonGroup

def window():
   app = QApplication(sys.argv)
   win = QWidget()

   l1 = QLabel("Name")
   nm = QLineEdit()

   l2 = QLabel("Address")
   add1 = QLineEdit()
   add2 = QLineEdit()
   fbox = QFormLayout()
   fbox.addRow(l1, nm)
   vbox = QVBoxLayout()

   vbox.addWidget(add1)
   vbox.addWidget(add2)
   fbox.addRow(l2, vbox)

   # Create a button group for the radio buttons
   gender_group = QButtonGroup()

   r1 = QRadioButton("Male")
   r2 = QRadioButton("Female")

   # Add the radio buttons to the group
   gender_group.addButton(r1)
   gender_group.addButton(r2)

   hbox = QHBoxLayout()
   hbox.addWidget(r1)
   hbox.addWidget(r2)
   hbox.addStretch()
   fbox.addRow(QLabel("Sex"), hbox)
   fbox.addRow(QPushButton("Submit"), QPushButton("Cancel"))

   win.setLayout(fbox)
   win.setWindowTitle("PyQt")
   win.show()
   sys.exit(app.exec())

if __name__ == '__main__':
   window()