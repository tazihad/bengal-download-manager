import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QToolBar, QStatusBar
)
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtCore import Qt

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Set the window title and geometry (position and size)
        self.setWindowTitle("Bengal Download Manager")
        self.setGeometry(200, 150, 800, 400)

        label = QLabel("Hello World!", self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(label)

        toolbar = QToolBar(self)
        self.addToolBar(toolbar)
        toolbar.setMovable(False)

        self.setStatusBar(QStatusBar(self))

        actions = [
            "Add URL", "Resume", "Stop", "Stop All", 
            "Delete", "Delete Completed", "Options"
        ]

        # Loop over the actions and add each one to the toolbar
        for action_name in actions:
            action = QAction(QIcon(), action_name, self)
            toolbar.addAction(action)


if __name__ == "__main__":

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
