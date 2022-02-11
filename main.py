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

        # EXPERIMENT
        wavelengths = [610, 680, 730, 760, 810, 860]    # in nanometers, 20nm FWHM
        data = [239.23, 233.81, 187.27, 176.41, 172.35, 173.78]

        # Widgets
        self.widget = QWidget()     # Container widget
        
        self.pw = pg.PlotWidget(background=None)
        self.pi = self.pw.getPlotItem()

        self.pw.plot(wavelengths, data, symbol="o")
        self.pw.setXRange(wavelengths[0], wavelengths[-1], padding=0.1)

        self.pi.hideButtons()
        self.pi.setMenuEnabled(False)
        self.pi.setLimits(
            xMin=min(wavelengths) - min(wavelengths)*0.1 , 
            xMax=max(wavelengths) + max(wavelengths)*0.1, 
            yMin=min(data) - min(data)*0.1,
            yMax=max(data) + max(data)*0.1,
            )
        self.pi.setLabel('bottom', "Wavelength", units='nm')
        self.pi.setLabel('left', "NIR output", units='idk')
        self.pi.setTitle('Reflectance')

        xdict = dict(enumerate([str(x) for x in wavelengths]))
        ax = self.pi.getAxis('bottom').setTicks([xdict.items()])

        self.layout = QHBoxLayout()
        self.layout.addWidget(self.pw)
        self.layout.setContentsMargins(30, 60, 60, 30)
        self.widget.setLayout(self.layout)
        
        self.setWindowTitle("My plotter")
        self.resize(1000, 600)
        self.setMinimumSize(600, 350)
        self.center()
        self.setCentralWidget(self.widget)
        
    def center(self):
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def keyPressEvent(self, e):
        if (e.key() == Qt.Key.Key_Escape or
            e.key() == Qt.Key.Key_Q):
            self.close()

        elif (e.key() == Qt.Key.Key_Up or
              e.key() == Qt.Key.Key_W or
              e.key() == Qt.Key.Key_Plus):
            self.pi.getViewBox().scaleBy((0.9, 0.9))

        elif (e.key() == Qt.Key.Key_Down or
              e.key() == Qt.Key.Key_S or
              e.key() == Qt.Key.Key_Minus):
            self.pi.getViewBox().scaleBy((1.1, 1.1))

        elif (e.key() == Qt.Key.Key_Left or
              e.key() == Qt.Key.Key_A):
            self.pi.getViewBox().translateBy((-10, 0))

        elif (e.key() == Qt.Key.Key_Right or
              e.key() == Qt.Key.Key_D):
            self.pi.getViewBox().translateBy((+10, 0))

        elif (e.key() == Qt.Key.Key_Home):
            self.pi.getViewBox().autoRange(padding=0.1)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec()
