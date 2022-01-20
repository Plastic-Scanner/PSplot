import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # UI initialization
        self.setWindowTitle("My plotter")
        self.resize(800, 600)
        self.center()
        # self.setCentralWidget()

    def center(self):
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def keyPressEvent(self, e):
        if (e.key() == Qt.Key.Key_Escape.value or
            e.key() == Qt.Key.Key_Q.value):
            self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()
    app.exec()
