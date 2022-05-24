#!/usr/bin/env python
import sys
from PyQt6.QtCore import Qt, pyqtSignal
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
    QMessageBox,
    QComboBox
)
import pyqtgraph as pg
import numpy as np
import serial
import csv
import serial.tools.list_ports


class ComboBox(QComboBox):
    onPopup = pyqtSignal()

    def showPopup(self):
        self.onPopup.emit()
        super(ComboBox, self).showPopup()


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
        self.baudrate = 9600
        self.baseline = None
        self.serial = None


        # Widgets
        self.widget = QWidget()     # Container widget
        
        ## Serial selection
        self.serialList = ComboBox()
        self.serialList.addItem("None")
        self.serialList.setInsertPolicy(QComboBox.InsertPolicy.InsertAtTop)
        self.serialList.onPopup.connect(self.serialScan)
        self.serialList.activated.connect(self.serialConnect)

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
        self.yMin = 0
        self.yMax = 0.35
        self.pi.setLimits(
            xMin=min(self.wavelengths) - self.xPadding, 
            xMax=max(self.wavelengths) + self.xPadding,
            yMin= 0 - self.yPadding,
            )
        self.pi.setLabel('bottom', "Wavelength [nm]")
        self.pi.setLabel('left', "NIR output", units='V', unitPrefix="m")
        self.pi.setTitle('Reflectance')
        
        self.pw.setXRange(self.wavelengths[0], self.wavelengths[-1], padding=0.1)
        self.pw.setYRange(self.yMin, self.yMax, padding=self.yPadding)
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
        self.layout.addWidget(self.serialList)
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
        
        # Connect to serial device
        if self.serialList.count() > 0:
            self.serialConnect(self.serialList.itemText(0))     # open the first serial device
   
    def serialScan(self):
        """ Scans for available serial devices and updates the list """ 
        
        self.serialList.clear()
        self.serialList.addItem("None")
        for dev in list(serial.tools.list_ports.comports()):
            self.serialList.addItem(dev.device)


    def serialConnect(self, index):
        """ Connects to the serial device (e.g. /dev/ttyACM0) """

        if self.serial is not None:
            self.serial.close()                 # Close previously opened port, if exist

        port = self.serialList.currentText()
        
        try:
            self.serial = serial.Serial(port, baudrate=self.baudrate, timeout=0.5)
            print(f"Opened serial port {self.serial.portstr}")
            self.serial.readline()  # Consume the "Plastic scanner initialized line"
        except Exception as e:
            print(f"Can't open serial port '{port}', using dummy data")
            self.serial = None
        
   
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
            self.pw.setXRange(self.wavelengths[0], self.wavelengths[-1], padding=0.1)
            self.pw.setYRange(self.yMin, self.yMax, padding=self.yPadding)
        
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
            data = [0.2278, 0.2264, 0.2178, 0.2379, 0.2276, 0.2281, 0.2298, 0.2264]

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
