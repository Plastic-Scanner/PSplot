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
        
        self.pw = pg.PlotWidget(background=None)
        self.pi = self.pw.getPlotItem()
        self.pi.hideButtons()
        self.layout = QHBoxLayout()
        self.layout.addWidget(self.pw)
        self.layout.setContentsMargins(30, 30, 30, 30)
        self.widget.setLayout(self.layout)
        
        
        self.setWindowTitle("My plotter")
        self.resize(1000, 600)
        self.setMinimumSize(600, 350)
        self.center()
        self.setCentralWidget(self.widget)


        # EXPERIMENT
        wavelengths = [610, 680, 730, 760, 810, 860]    # in nanometers, 20nm FWHM
        data = [239.23, 233.81, 187.27, 176.41, 172.35, 173.78]

        self.pw.plot(wavelengths, data, symbol="o")
        self.pw.setXRange(wavelengths[0], wavelengths[-1])

        myxticks = zip(range(len(wavelengths)), wavelengths)
        print(range(len(wavelengths)))
        print([str(w) for w in wavelengths])
        
        # self.pw.getAxis('bottom').setTicks([])

        ticks = [list(zip(range(len(wavelengths)), wavelengths))]
        pw = pg.PlotWidget()
        xax = pw.getAxis('bottom')
        xax.setTicks(ticks)
        
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
