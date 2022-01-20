import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QDockWidget,
    QListWidget,
    QHBoxLayout
)
import pyqtgraph as pg
import numpy as np

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Widgets
        self.widget = QWidget()     # Container widget
        
        self.labelWidget = QLabel("Hello World!")

        self.plotWidget = pg.PlotWidget()
        self.plotWidget.setXRange(0, 20, padding=0)
        self.plotWidget.setYRange(0, 10, padding=0)
        

        self.layout = QHBoxLayout()
        self.layout.addWidget(self.labelWidget)
        self.layout.addWidget(self.plotWidget)
        self.layout.setContentsMargins(10,10,30,30)
        self.widget.setLayout(self.layout)
        
        self.setWindowTitle("My plotter")
        self.resize(1000, 600)
        self.setMinimumSize(600, 350)
        self.center()
        self.setCentralWidget(self.widget)

        # x = np.random.normal(size=100)
        # y = np.random.normal(size=100)
        # self.plotWidget.plot(x, y, pen=None, symbol='o')


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
