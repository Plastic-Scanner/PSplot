#!/usr/bin/env python
import csv
from collections import deque
import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal, QT_VERSION_STR
from PyQt6.QtGui import QKeySequence, QKeyEvent, QColor, QPalette, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import pyqtgraph as pg
import random
import serial
import serial.tools.list_ports
import sys
from typing import List, Optional


class ComboBox(QComboBox):
    onPopup = pyqtSignal()

    def showPopup(self) -> None:
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

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def keyPressEvent(self, event) -> None:
        super().keyPressEvent(event)

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_C:
                copied_cells = sorted(self.selectedIndexes())

                copy_text = ""
                max_column = copied_cells[-1].column()
                for c in copied_cells:
                    copy_text += self.item(c.row(), c.column()).text()
                    if c.column() == max_column:
                        copy_text += "\n"
                    else:
                        copy_text += "\t"

                QApplication.clipboard().setText(copy_text)


class PsPlot(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowIcon(QIcon('logo3-01.png'))

        # HARDCODED SETTINGS
        self.wavelengths = [
            855,
            940,
            1050,
            1300,
            1450,
            1550,
            1650,
            1720,
        ]  # in nanometers, 20nm FWHM
        self.baudrate = 9600
        self.baseline = None
        self.serial = None

        ## To keep track
        # used for also plotting previouse values
        self.old_data = deque(maxlen=3)
        # to keep track of the amount of calibrations done
        self.calibration_counter = 0
        # holds labers for each row
        self.row_labels = []

        # Widgets
        self.widget = QWidget()  # Container widget

        ## Serial selection
        self.serialList = ComboBox()
        self.serialList.onPopup.connect(self.serialScan)
        self.serialList.activated.connect(self.serialConnect)
        # make it take up the maximum possible space
        self.serialList.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        # serial notification
        self.serialNotif = QLabel()

        # serial horizonal layout
        self.horizontalSerialLayout = QHBoxLayout()
        self.horizontalSerialLayout.addWidget(self.serialList)
        self.horizontalSerialLayout.addWidget(self.serialNotif)

        ## Plot
        self.pw = pg.PlotWidget(background=None)

        self.pi = self.pw.getPlotItem()
        self.pi.hideButtons()
        self.pi.setMenuEnabled(False)
        self.pi.showGrid(x=True, y=True, alpha=0.5)
        self.pi.setMouseEnabled(x=False, y=True)

        self.pc = self.pw.plot()
        self.pc.setSymbol("o")

        self.xPadding = min(self.wavelengths) * 0.1
        self.yPadding = 0.015
        self.yMin = 0
        self.yMax = 0.35
        self.pi.setLimits(
            xMin=min(self.wavelengths) - self.xPadding,
            xMax=max(self.wavelengths) + self.xPadding,
            yMin=0 - self.yPadding,
        )
        self.pi.setLabel("left", "NIR output", units="V", unitPrefix="m")
        self.pi.setLabel("bottom", "Wavelength (nm)")
        self.pi.getAxis("bottom").enableAutoSIPrefix(False)
        self.pi.setTitle("Reflectance")

        self.pw.setXRange(self.wavelengths[0], self.wavelengths[-1], padding=0.1)
        self.pw.setYRange(self.yMin, self.yMax, padding=self.yPadding)

        ## Table output
        self.tableHeader = ["sample name"] + [str(x) for x in self.wavelengths]
        self.table = Table()
        self.table.setColumnCount(len(self.tableHeader))
        self.table.setHorizontalHeaderLabels(self.tableHeader)
        self.table.setColumnWidth(0, 200)

        ## Buttons
        # center, auto-restoreAxis and clear
        self.axisRestoreBtn = QPushButton("Restore axis")
        self.axisRestoreBtn.clicked.connect(self.restoreAxisPlot)

        self.axisAutoRestoreChbx = QCheckBox("auto-restore axis")
        self.axisAutoRestoreChbx.clicked.connect(self.restoreAxisPlotChbxClick)

        self.axisAutoRangeChbx = QCheckBox("auto-center axis")
        self.axisAutoRangeChbx.clicked.connect(self.centerAxisPlotChbxClick)

        self.clearPlotBtn = QPushButton("Clear graph")
        self.clearPlotBtn.clicked.connect(self.clearGraph)

        self.clearCalibrationBtn = QPushButton("Clear Calibration")
        self.clearCalibrationBtn.clicked.connect(self.clearCalibration)

        self.horizontalBtnLayout = QHBoxLayout()
        self.horizontalBtnLayout.addWidget(self.axisRestoreBtn)
        self.horizontalBtnLayout.addWidget(self.axisAutoRestoreChbx)
        self.horizontalBtnLayout.addWidget(self.axisAutoRangeChbx)
        self.horizontalBtnLayout.addWidget(self.clearPlotBtn)
        self.horizontalBtnLayout.addWidget(self.clearCalibrationBtn)

        # export and calibrate
        self.exportBtn = QPushButton("Export CSV")
        self.exportBtn.clicked.connect(self.exportCsv)

        self.calibrateBtn = QPushButton("Calibrate with spectralon")
        self.calibrateBtn.clicked.connect(self.calibrate)

        # add all layouts
        self.layout = QVBoxLayout()
        self.layout.addLayout(self.horizontalSerialLayout)
        self.layout.addWidget(self.pw)
        self.layout.addLayout(self.horizontalBtnLayout)
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

        # Connect to the serial device (first, newest detected)
        self.serialScan()
        self.serialList.setCurrentIndex(0)
        self.serialConnect(0)

        self.pw.setFocus()
        self.widget.setTabOrder(self.pw, self.serialList)

    def serialScan(self) -> None:
        """Scans for available serial devices and updates the list"""

        self.serialList.clear()
        self.serialList.insertItem(0, "None")
        for dev in list(serial.tools.list_ports.comports()):
            self.serialList.insertItem(0, dev.device)

    def serialConnect(self, index: int) -> None:
        """Connects to the serial device (e.g. /dev/ttyACM0)"""

        if self.serial is not None:
            self.serial.close()  # Close previously opened port, if exist

        port = self.serialList.currentText()

        try:
            self.serial = serial.Serial(port, baudrate=self.baudrate, timeout=0.5)
            print(f"Opened serial port {self.serial.portstr}")
            self.serial.readline()  # Consume the "Plastic scanner initialized line"
            self.serialNotif.setText("Using real data")
        except serial.serialutil.SerialException:
            print(f"Cannot open serial port '{port}', using dummy data")
            self.serial = None
            self.serialNotif.setText("Using dummy data")
        except Exception as e:
            print(f"Can't open serial port '{port}', using dummy data")
            self.serial = None
            self.serialNotif.setText("Using dummy data")

    def center(self) -> None:
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def centerAxisPlotChbxClick(self) -> None:
        self.pw.setFocus()
        if self.axisAutoRangeChbx.isChecked():
            self.axisAutoRestoreChbx.setChecked(0)
            self.centerAxisPlot()

    def centerAxisPlot(self) -> None:
        # when coming from self.plot checking if it is checked is now done twice
        self.pi.getViewBox().autoRange()
        all_plotted_data = [x for y in self.old_data for x in y] + (self.baseline or [])
        self.pi.getViewBox().setYRange(
            min=min(all_plotted_data) - self.yPadding,
            max=max(all_plotted_data) + self.yPadding,
        )

    def restoreAxisPlotChbxClick(self) -> None:
        self.pw.setFocus()
        if self.axisAutoRestoreChbx.isChecked():
            self.axisAutoRangeChbx.setChecked(0)
            self.restoreAxisPlot()

    def restoreAxisPlot(self) -> None:
        self.pw.setXRange(self.wavelengths[0], self.wavelengths[-1], padding=0.1)
        self.pw.setYRange(self.yMin, self.yMax, padding=self.yPadding)

    def clearGraph(self) -> None:
        self.old_data.clear()
        self.pw.clear()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() == Qt.Key.Key_Escape or e.key() == Qt.Key.Key_Q:
            self.close()

        elif (
            e.key() == Qt.Key.Key_Up
            or e.key() == Qt.Key.Key_W
            or e.key() == Qt.Key.Key_Plus
        ):
            self.pi.getViewBox().scaleBy((1, 0.9))

        elif (
            e.key() == Qt.Key.Key_Down
            or e.key() == Qt.Key.Key_S
            or e.key() == Qt.Key.Key_Minus
        ):
            self.pi.getViewBox().scaleBy((1, 1.1))

        elif e.key() == Qt.Key.Key_Left or e.key() == Qt.Key.Key_A:
            self.pi.getViewBox().translateBy((-10, 0))

        elif e.key() == Qt.Key.Key_Right or e.key() == Qt.Key.Key_D:
            self.pi.getViewBox().translateBy((+10, 0))

        elif e.key() == Qt.Key.Key_Home:
            self.pw.setXRange(self.wavelengths[0], self.wavelengths[-1], padding=0.1)
            self.pw.setYRange(self.yMin, self.yMax, padding=self.yPadding)

        elif e.key() == Qt.Key.Key_Space:
            data = self.getMeasurement()
            self.addMeasurement(data)
            self.plot(data)

    def addCalibrationMeasurement(self, data: List[float]) -> None:
        self.addToTable(data, True)

    def addMeasurement(self, data: List[float]) -> None:
        # use calibration if possible
        if self.baseline is not None:
            dataCalibrated = [dat / base for dat, base in zip(data, self.baseline)]
            #  data = dataCalibrated

        self.addToTable(data)

        self.old_data.append(data)

    def addToTable(
        self, data: List[float], calibrated_measurement: bool = False
    ) -> None:
        # add row
        nRows = self.table.rowCount()
        self.table.setRowCount(nRows + 1)
        self.table.setItem(
            nRows, 0, QTableWidgetItem("")
        )  # sample name (user-editable, empty by default)
        if calibrated_measurement:
            self.row_labels.append(f"c {self.calibration_counter}")
        else:
            self.row_labels.append(str(nRows + 1 - self.calibration_counter))
        self.table.setVerticalHeaderLabels(self.row_labels)

        # add value for every column of new row
        dataStr = self.listToString(data)
        for col, val in enumerate(dataStr.split(), start=1):
            cell = QTableWidgetItem(val)
            cell.setFlags(
                cell.flags() & ~Qt.ItemFlag.ItemIsEditable
            )  # disable editing of cells

            # use a different color if the measurement was taken for calibration
            if calibrated_measurement:
                cell.setForeground(
                    self.table.palette().color(QPalette.ColorRole.Highlight)
                )
            self.table.setItem(nRows, col, cell)

        self.table.scrollToBottom()

    def getMeasurement(self) -> List[float]:
        if self.serial is not None:
            # send serial command
            self.serial.write(b"scan\n")

            # read response
            line = self.serial.readline()
            line = line.decode()

            # parse data
            data = line.strip("> ").strip("\r\n").split("\t")
            data = [float(x) for x in data if x != ""]
        else:
            # dummy data with random noise
            data = data = [
                0.2278,
                0.2264,
                0.2178,
                0.2379,
                0.2276,
                0.2281,
                0.2298,
                0.2264,
            ]
            data = [x + random.uniform(0.0015, 0.0080) for x in data]

        return data

    def calibrate(self) -> None:
        button = QMessageBox.question(
            self, "Calibration", "Is the spectralon sample on the sensor?"
        )
        if button == QMessageBox.StandardButton.Yes:
            self.baseline = self.getMeasurement()
            self.calibration_counter += 1
            self.addCalibrationMeasurement(self.baseline)
            self.old_data.clear()

        self.plot()

    def clearCalibration(self) -> None:
        self.baseline = None
        self.plot(self.old_data[-1])

    def listToString(self, data: List[float]) -> str:
        return " ".join([f"{i:.4f}" for i in data])

    def exportCsv(self) -> None:
        fname, _ = QFileDialog.getSaveFileName(self, "Save File")
        with open(fname, "w", newline="") as csvfile:
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

    def plot(self, data: Optional[List[float]] = None) -> None:
        self.pw.clear()

        # add the baseline of the last calibration
        if self.baseline is not None:
            pc = self.pw.plot(self.wavelengths, self.baseline, pen=(255, 0, 0))

        for dat in self.old_data:
            pc = self.pw.plot(
                self.wavelengths, dat, pen=(0, 100, 0), symbolBrush=(0, 255, 0)
            )
            pc.setSymbol("x")

        lineC = tuple(
            self.pw.palette().color(QPalette.ColorRole.WindowText).getRgb()[:-1]
        )
        markC = tuple(
            self.pw.palette().color(QPalette.ColorRole.Highlight).getRgb()[:-1]
        )
        pen = pg.mkPen(color=lineC, symbolBrush=markC, symbolPen="o", width=2)
        if data is not None:
            pc = self.pw.plot(self.wavelengths, data, pen=pen)
            pc.setSymbol("o")

        if self.axisAutoRestoreChbx.isChecked():
            self.restoreAxisPlot()
        if self.axisAutoRangeChbx.isChecked():
            self.centerAxisPlot()


if __name__ == "__main__":
    print(f"App is running on QT version {QT_VERSION_STR}")
    # this should add some optimisations for high-DPI screens
    # https://pyqtgraph.readthedocs.io/en/latest/how_to_use.html#hidpi-displays
    app = pg.mkQApp()
    window = PsPlot()
    window.show()
    app.exec()
