#!/usr/bin/env python
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
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
    QTextEdit,
    QPushButton,
    QFileDialog,
    QMessageBox
)
import pyqtgraph as pg
import numpy as np
import serial
import csv

class Table(QTableWidget):
    """
    this class extends QTableWidget
    * supports copying multiple cell's text onto the clipboard
    * formatted specifically to work with multiple-cell paste into programs
      like google sheets, excel, or numbers
    Taken and modified from https://stackoverflow.com/a/68598423/5539470 
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_C:
                copied_cells = sorted(self.selectedIndexes())

                copy_text = ''
                max_column = copied_cells[-1].column()
                for c in copied_cells:
                    copy_text += self.item(c.row(), c.column()).text()
                    if c.column() == max_column:
                        copy_text += '\n'
                    else:
                        copy_text += '\t'
                    
                QApplication.clipboard().setText(copy_text)

class Spectraplot(QMainWindow):
    def __init__(self):
        super().__init__()

        # HARDCODED SETTINGS
        self.wavelengths = [855, 940, 1050, 1300, 1450, 1550, 1650, 1720]    # in nanometers, 20nm FWHM
        baudrate = 9600
        inputFile = "/dev/ttyACM0"
        # inputFile = "COM5"
        self.baseline = None
        
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
        self.pc = self.pw.plot()
        self.pc.setSymbol("o")
        self.pi.hideButtons()
        self.pi.setMenuEnabled(False)
        self.pi.setMouseEnabled(x=False, y=True)
        self.xPadding = min(self.wavelengths) * 0.1
        self.yPadding = 0.01
        self.pi.setLimits(
            xMin=min(self.wavelengths) - self.xPadding, 
            xMax=max(self.wavelengths) + self.xPadding,
            yMin= 0 - self.yPadding,
            )
        self.pi.setLabel('bottom', "Wavelength [nm]")
        self.pi.setLabel('left', "NIR output", units='V', unitPrefix="m")
        self.pi.setTitle('Reflectance')
        
        self.pw.setXRange(self.wavelengths[0], self.wavelengths[-1], padding=0.1)
        self.pw.setYRange(0, 0.3, padding=self.yPadding)
        self.pw.disableAutoRange()

        ## Table output
        self.tableHeader = ["sample name"] + [str(x) for x in self.wavelengths]
        self.table = Table()
        self.table.setColumnCount(len(self.tableHeader))
        self.table.setHorizontalHeaderLabels(self.tableHeader)

        ## Buttons
        self.exportBtn = QPushButton("E&xport CSV")
        self.exportBtn.clicked.connect(self.exportCsv)

        self.calibrateBtn = QPushButton("C&alibrate with spectralon")
        self.calibrateBtn.clicked.connect(self.calibrate)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.pw)
        self.layout.addWidget(self.table)
        self.layout.addWidget(self.exportBtn)
        self.layout.addWidget(self.calibrateBtn)
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
            self.pi.getViewBox().scaleBy((1, 0.9))

        elif (e.key() == Qt.Key.Key_Down or
              e.key() == Qt.Key.Key_S or
              e.key() == Qt.Key.Key_Minus):
            self.pi.getViewBox().scaleBy((1, 1.1))

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
            if self.baseline is not None:
                dataCalibrated = []
                for x in range(len(data)):
                    dataCalibrated.append(data[x]/self.baseline[x])
                dataStr = self.listToString(dataCalibrated)
                # append to table
                nRows = self.table.rowCount()
                self.table.setRowCount(nRows+1)
                self.table.setItem(nRows, 0, QTableWidgetItem(""))    # sample name (user-editable, empty by default)
                for col, val in enumerate(dataStr.split(), start=1):
                    cell = QTableWidgetItem(val)
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable) # disable editing of cells
                    self.table.setItem(nRows, col, cell)
                self.table.scrollToBottom()
                self.plot(dataCalibrated)
            else:
                dataStr = self.listToString(data)
                nRows = self.table.rowCount()
                self.table.setRowCount(nRows+1)
                self.table.setItem(nRows, 0, QTableWidgetItem(""))    # sample name (user-editable, empty by default)
                for col, val in enumerate(dataStr.split(), start=1):
                    cell = QTableWidgetItem(val)
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable) # disable editing of cells
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
    
    def calibrate(self):
        button = QMessageBox.question(self, "Calibration", "Is the spectralon sample on the sensor?")
        if button == QMessageBox.StandardButton.Yes:
            self.baseline = self.getMeasurement()

        # Change default zoom/scaling
        self.pw.setYRange(0, 1.5, padding=self.yPadding)

    def listToString(self, data):
        return " ".join([f"{i:.4f}" for i in data])

    def exportCsv(self):
        fname, _ = QFileDialog.getSaveFileName(self, 'Save File')
        with open(fname, 'w', newline='') as csvfile:
            rows = self.table.rowCount()
            cols = self.table.columnCount()
            writer = csv.writer(csvfile)
            writer.writerow(self.wavelengths)
            for i in range(rows):
                row = []
                for j in range(cols):
                    try:
                        val = self.table.item(i, j).text()
                    except AttributeError:  # sometimes table.item() returns None - bug in fw/serial comm?
                        val = ""
                    row.append(val)
                writer.writerow(row)

    def plot(self, data):
        self.pc.setData(self.wavelengths, data)


if __name__ == "__main__":

    app = QApplication(sys.argv)
    window = Spectraplot()
    window.show()
    app.exec()
