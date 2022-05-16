#!/usr/bin/env python
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QDockWidget,
    QListWidget,
    QTableWidget,
    QTableWidgetItem,
    QHBoxLayout,
    QVBoxLayout,
    QTextEdit
)
import pyqtgraph as pg
import numpy as np
import serial

class Spectraplot(QMainWindow):
    def __init__(self):
        super().__init__()

        # HARDCODED SETTINGS
        self.wavelengths = [855, 940, 1050, 1200, 1300, 1450, 1550, 1650]    # in nanometers, 20nm FWHM

        baudrate = 9600
        inputFile = "/dev/ttyACM0"
        
        try:
            self.serial = serial.Serial(inputFile, baudrate=baudrate, timeout=0.5)
            print(f"Opened serial port {self.serial.portstr}")
            self.serial.readline()  # Consume the "Plastic scanner initialized line"

        except:
            print(f"Can't open serial port {inputFile}")
            print("using dummy data")
            self.serial = None

        # Widgets
        self.widget = QWidget()     # Container widget
        
        ## Plot
        self.pw = pg.PlotWidget(background=None)
        self.pi = self.pw.getPlotItem()
        self.pc = self.pw.plot(self.wavelengths, np.zeros(8), symbol="o")
        self.pw.setXRange(self.wavelengths[0], self.wavelengths[-1], padding=0.1)

        self.pi.hideButtons()
        self.pi.setMenuEnabled(False)
        xPadding = min(self.wavelengths) * 0.1
        self.pi.setLimits(
            xMin=min(self.wavelengths) - xPadding, 
            xMax=max(self.wavelengths) + xPadding,
            )
        self.pi.setLabel('bottom', "Wavelength [nm]")
        self.pi.setLabel('left', "NIR output", units='V')
        self.pi.setTitle('Reflectance')

        ## Table output
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.wavelengths))
        self.table.setHorizontalHeaderLabels([str(x) for x in self.wavelengths])

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.pw)
        self.layout.addWidget(self.table)
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
        
        elif (e.key() == Qt.Key.Key_Space):
            data = self.getMeasurement()
            dataStr = self.listToString(data)
                        
            # append to table
            nRows = self.table.rowCount()
            self.table.setRowCount(nRows+1)
            for col, val in enumerate(dataStr.split()):
                cell = QTableWidgetItem(val)
                self.table.setItem(nRows, col, cell)
            self.table.scrollToBottom()
            self.plot(data)
                

    def getMeasurement(self):
        if self.serial is not None:
            # send serial command
            self.serial.write(b"scan\n")

            # read response
            line = self.serial.readline()
            line = line.decode()

            # parse data
            data = line.strip('> ').strip('\r\n').split('\t')
            data = [float(x) for x in data if x != '']
        else:
            # dummy data
            data = [123.1233, 234.2344, 456.4566, 567.5677, 678.6788, 789.7899, 890.8900, 901.9011]
        return data

    def listToString(self, data):
        return " ".join([f"{i:.4f}" for i in data])

    def plot(self, data):
        self.pc.setData(self.wavelengths, data)


if __name__ == "__main__":

    app = QApplication(sys.argv)
    window = Spectraplot()
    window.show()
    app.exec()
