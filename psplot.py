#!/usr/bin/env python

from threading import currentThread
from PyQt5.QtCore import Qt, pyqtSignal, QT_VERSION_STR
from PyQt5.QtGui import QKeySequence, QKeyEvent, QColor, QPalette, QVector3D
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QCompleter,
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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
from PyQt5.QtDataVisualization import (
    Q3DCamera,
    Q3DTheme,
    Q3DScatter,
    QAbstract3DGraph,
    QAbstract3DSeries,
    QScatter3DSeries,
    QScatterDataItem,
    QScatterDataProxy,
)
import csv
from collections import deque
import numpy as np
import pandas as pd

# pyqtgraph should always be imported after importing pyqt
import pyqtgraph as pg
import os
import random
import serial
import serial.tools.list_ports
import sys
import time
from typing import List, Optional, Tuple, Dict


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
        self.ctr = 0

        # HARDCODED SETTINGS
        self.wavelengths = [
            940,
            1050,
            1200,
            1300,
            1450,
            1550,
            1650,
            1720,
        ]  # in nanometers, 20nm FWHM
        self.baudrate = 9600
        self.baseline = None
        self.serial = None
        self.datasetloaded = None
        ## To keep track
        # used for also plotting previouse values
        self.old_data = deque(maxlen=3)
        # to keep track of the amount of calibrations done
        self.calibration_counter = 0
        # holds labers for each row
        self.row_labels = []
        # holds all of the names for all of the samples
        self.sample_labels = set()

        # Widgets
        self.widget = QWidget()  # Container widget

        ## input output (selecting serial and saving)
        # selecting serial
        self.serialList = ComboBox()
        self.serialList.onPopup.connect(self.serialScan)
        self.serialList.activated.connect(self.serialConnect)
        # make it take up the maximum possible space
        self.serialList.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        # serial notification
        self.serialNotif = QLabel()

        # loading and saving
        self.loadDatasetBtn = QPushButton("Load dataset from file")

        # export and calibrate
        self.exportBtn = QPushButton("Export dataset to file")
        self.exportBtn.clicked.connect(self.exportCsv)

        # serial horizonal layout
        self.horizontalSerialLayout = QHBoxLayout()
        self.horizontalSerialLayout.addWidget(self.serialList)
        self.horizontalSerialLayout.addWidget(self.serialNotif)

        # load and save horizontal layout
        self.horizontalLoadSaveLayout = QHBoxLayout()
        self.horizontalLoadSaveLayout.addWidget(self.loadDatasetBtn)
        self.horizontalLoadSaveLayout.addWidget(self.exportBtn)

        self.inoutBoxLayout = QVBoxLayout()
        self.inoutBoxLayout.addLayout(self.horizontalSerialLayout)
        self.inoutBoxLayout.addLayout(self.horizontalLoadSaveLayout)
        self.inoutBox = QGroupBox("data in/out")
        self.inoutBox.setLayout(self.inoutBoxLayout)

        ## taking a measurement
        # calibration
        self.calibrateBtn = QPushButton("Calibrate with spectralon")
        self.calibrateBtn.clicked.connect(self.calibrate)

        self.clearCalibrationBtn = QPushButton("Clear Calibration")
        self.clearCalibrationBtn.clicked.connect(self.clearCalibration)
        self.clearCalibrationBtn.setDisabled(True)

        # the next two buttons will be enabled after a calibration has been performed
        self.regularMeasurementBtn = QPushButton(
            "Take measurement\n(shortcut: spacebar)"
        )
        self.regularMeasurementBtn.setToolTip(
            "a calibration measurement needs to be taken first"
        )
        self.regularMeasurementBtn.clicked.connect(self.takeRegularMeasurement)
        self.regularMeasurementBtn.setDisabled(True)

        self.sampleNameInput = QLineEdit()
        self.sampleNameInput.setPlaceholderText("sample name")
        self.sampleNameInput.setClearButtonEnabled(True)
        self.sampleNameInput.textChanged.connect(self.sampleNameInputChanged)
        # this is connected to takeregularmeasurement after a callibration measurement has been performed
        # self.sampleNameInput.returnPressed.connect(self.takeRegularMeasurement)

        self.sampleNameSelection = QComboBox()
        self.sampleNameSelection.setDuplicatesEnabled(False)
        self.sampleNameSelection.currentTextChanged.connect(
            self.sampleNameSelectionChanged
        )
        self.sampleNameSelection.setPlaceholderText("select sample name")

        self.calibrationLayout = QHBoxLayout()
        self.calibrationLayout.addWidget(self.calibrateBtn)
        self.calibrationLayout.addWidget(self.clearCalibrationBtn)

        self.sampleNameLayout = QHBoxLayout()
        self.sampleNameLayout.addWidget(self.sampleNameInput, 50)
        self.sampleNameLayout.addWidget(self.sampleNameSelection, 50)

        self.measureBoxLayout = QVBoxLayout()
        self.measureBoxLayout.addLayout(self.calibrationLayout)
        self.measureBoxLayout.addLayout(self.sampleNameLayout)
        self.measureBoxLayout.addWidget(self.regularMeasurementBtn)

        self.measureBox = QGroupBox("measuring")
        self.measureBox.setLayout(self.measureBoxLayout)

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
        self.yMax = 1.1
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

        # add 3d plot
        self.threeDdata: Dict[Tuple[int], list[QScatterDataItem]] = dict()
        self.threeDdata_colors = []
        self.threeDgraph = Q3DScatter()
        self.threeDgraph_container = QWidget.createWindowContainer(self.threeDgraph)
        self.threeDgraph.axisX().setTitle("1050nm")
        self.threeDgraph.axisY().setTitle("1450")
        self.threeDgraph.axisZ().setTitle("1650nm")
        self.threeDgraph.scene()
        # set the camera
        # self.threeDgraph.setMeasureFps(True)
        self.threeDgraph.setOrthoProjection(True)
        self.threeDgraph.scene().activeCamera().setCameraPreset(
            Q3DCamera.CameraPresetIsometricLeft
        )

        # styling
        self.threeDgraph.setShadowQuality(QAbstract3DGraph.ShadowQuality(0))
        currentTheme = self.threeDgraph.activeTheme()
        currentTheme.setType(Q3DTheme.Theme(0))
        currentTheme.setBackgroundEnabled(True)
        currentTheme.setLabelBackgroundEnabled(True)
        currentTheme.setAmbientLightStrength(0.6)
        currentTheme.setGridEnabled(True)
        back = QColor(self.palette().window().color())
        currentTheme.setBackgroundColor(back)
        currentTheme.setWindowColor(back)

        # holds all of the scatterdataseries
        self.scatter_proxy = QScatterDataProxy()
        self.scatter_proxy2 = QScatterDataProxy()

        #  series = QScatter3DSeries(self.scatter_proxy)
        #  #  series.setItemLabelFormat(
        #  #          "@xTitle: @xLabel | @yTitle: @yLabel | @zTitle: @zLabel")
        #  series.setItemLabelFormat("@xLabel | @yLabel | @zLabel")
        #  series.setMeshSmooth(True)
        #  series.setBaseColor(QColor(0,255,255))

        #  self.threeDgraph.addSeries(series)
        #  self.data = [QScatterDataItem(QVector3D(i,i,i)) for i in range(10)]
        #
        #  self.threeDgraph.seriesList()[0].dataProxy().resetArray(self.data)

        # graph horizonal layout
        self.horizontalGraphLayout = QHBoxLayout()
        self.horizontalGraphLayout.setSpacing(10)
        self.horizontalGraphLayout.addWidget(self.pw, 50)
        self.horizontalGraphLayout.addWidget(self.threeDgraph_container, 50)

        ## Table output
        self.tableHeader = ["sample name"] + [str(x) for x in self.wavelengths]
        self.table = Table()
        self.table.setColumnCount(len(self.tableHeader))
        self.table.setHorizontalHeaderLabels(self.tableHeader)
        self.table.setColumnWidth(0, 200)
        self.table.itemChanged.connect(self.tableChanged)

        ## Buttons
        # center, auto-restoreAxis and clear

        self.axisRestoreBtn = QPushButton("Restore axis")
        self.axisRestoreBtn.clicked.connect(self.restoreAxisPlot)

        self.axisCenterBtn = QPushButton("Center axis")
        self.axisCenterBtn.clicked.connect(self.centerAxisPlot)

        self.axisAutoRestoreChbx = QCheckBox("auto-restore axis")
        self.axisAutoRestoreChbx.clicked.connect(self.restoreAxisPlotChbxClick)

        self.axisAutoRangeChbx = QCheckBox("auto-center axis")
        self.axisAutoRangeChbx.clicked.connect(self.centerAxisPlotChbxClick)

        self.clearPlotBtn = QPushButton("Clear graph")
        self.clearPlotBtn.clicked.connect(self.clearGraph)

        self.horizontalBtnLayout = QHBoxLayout()
        #  self.horizontalBtnLayout.addWidget(self.loadDatasetChbx)
        self.horizontalBtnLayout.addWidget(self.axisRestoreBtn)
        self.horizontalBtnLayout.addWidget(self.axisCenterBtn)
        self.horizontalBtnLayout.addWidget(self.axisAutoRestoreChbx)
        self.horizontalBtnLayout.addWidget(self.axisAutoRangeChbx)
        self.horizontalBtnLayout.addWidget(self.clearPlotBtn)
        #  self.horizontalBtnLayout.addWidget(self.clearCalibrationBtn)

        # add all layouts
        self.layout = QVBoxLayout()
        self.layout.setSpacing(10)
        self.layout.addWidget(self.inoutBox)
        self.layout.addWidget(self.measureBox)
        self.layout.addLayout(self.horizontalGraphLayout)
        self.layout.addLayout(self.horizontalBtnLayout)
        self.layout.addWidget(self.table)
        #  self.layout.addWidget(self.exportBtn)
        #  self.layout.addWidget(self.calibrateBtn)
        #  self.layout.setContentsMargins(30, 60, 60, 30)
        self.widget.setLayout(self.layout)

        self.setWindowTitle("PSPlot")
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
            self.serial = serial.Serial(port, baudrate=self.baudrate, timeout=1)
            print(f"Opened serial port {self.serial.portstr}")
            self.serialNotif.setText("Using real data")
            time.sleep(1)
            self.serial.readline()  # Consume the "Plastic scanner initialized" line
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
        self.axes.cla()

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
            self.takeRegularMeasurement()

    def takeRegularMeasurement(self):
        data = self.getMeasurement()
        self.addMeasurement(data)
        self.plot(data)
        self.threeD([data[1], data[4], data[6]])

    def addCalibrationMeasurement(self, data: List[float]) -> None:
        self.addToTable(data, True)

    def addMeasurement(self, data: List[float]) -> None:
        name = self.sampleNameInput.text()
        if name not in self.sample_labels:
            self.sample_labels.add(name)
            self.sampleNameSelection.addItem(name)
            completer = QCompleter(list(self.sample_labels))
            completer.setCaseSensitivity(False)
            self.sampleNameInput.setCompleter(completer)

        self.sampleNameSelection.setCurrentText(name)

        # use calibration if possible
        if self.baseline is not None:
            dataCalibrated = [dat / base for dat, base in zip(data, self.baseline)]
            #  data = dataCalibrated

        self.addToTable(data, name)

        self.old_data.append(data)

    def addToTable(
        self, data: List[float], name: str = "", calibrated_measurement: bool = False
    ) -> None:
        # add row
        nRows = self.table.rowCount()
        self.table.setRowCount(nRows + 1)
        self.table.setItem(
            nRows, 0, QTableWidgetItem(name)
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
            # print(data)
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

    def getADC(self) -> List[float]:
        if self.serial is not None:
            # send serial command
            self.serial.write(b"adc\n")

            # read response
            line = self.serial.readline()
            line = line.decode()

            # parse data
            data = line.strip("> ").strip("\r\n").split("\t")
            data = [float(x) for x in data if x != ""]
        else:
            # dummy data with random noise
            data = data = [
                0.0078,
            ]
            data = [x + random.uniform(0.0015, 0.0080) for x in data]

        return data

    def calibrate(self) -> None:
        button = QMessageBox.question(
            self, "Calibration", "Is the spectralon sample on the sensor?"
        )
        if self.calibration_counter == 0:
            self.clearCalibrationBtn.setEnabled(True)
            self.regularMeasurementBtn.setEnabled(True)
            self.regularMeasurementBtn.setToolTip("")
            self.sampleNameInput.returnPressed.connect(self.takeRegularMeasurement)

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
        return " ".join([f"{i:.7f}" for i in data])

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
                    except (
                        AttributeError
                    ):  # sometimes table.item() returns None - bug in fw/serial comm?
                        val = ""
                    row.append(val)
                writer.writerow(row)

    def tableChanged(self, item):
        # if it was a label that changed, add it to the list of labels
        if item.column() == 0:
            name = item.text()
            if name not in self.sample_labels:
                self.sample_labels.add(name)
                self.sampleNameSelection.addItem(name)

    def sampleNameInputChanged(self, input_text):
        if input_text in self.sample_labels:
            self.sampleNameSelection.setCurrentText(input_text)
        else:
            self.prevent_loop = True
            self.sampleNameSelection.setCurrentText("")

    def sampleNameSelectionChanged(self, sample_name):
        if not self.prevent_loop:
            self.sampleNameInput.setText(sample_name)
            self.prevent_loop = False

    def plot(self, data: Optional[List[float]] = None) -> None:
        self.pw.clear()
        self.baseline = np.array(self.baseline)

        # add the baseline of the last calibration
        if self.baseline is not None:
            normalizedbasline = self.baseline / self.baseline
            pc = self.pw.plot(self.wavelengths, normalizedbasline, pen=(255, 0, 0))

        for dat in self.old_data:
            dat = np.array(dat)
            normalizedolddat = dat / self.baseline
            pc = self.pw.plot(
                self.wavelengths,
                normalizedolddat,
                pen=(0, 100, 0),
                symbolBrush=(0, 255, 0),
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
            data = np.array(data)
            normalizeddata = data / self.baseline
            pc = self.pw.plot(self.wavelengths, normalizeddata, pen=pen)
            pc.setSymbol("o")

        if self.axisAutoRestoreChbx.isChecked():
            self.restoreAxisPlot()
        if self.axisAutoRangeChbx.isChecked():
            self.centerAxisPlot()

    def loadDataset(self):
        # the goal here is to load a dataset to visualize in the 3D scatterplot
        # import the dataframe
        df_raw = pd.read_csv(
            "https://raw.githubusercontent.com/Plastic-Scanner/data/main/data/20230117_DB2.1_second_dataset/measurement.csv"
        )
        # calculate the mean of the last 8 columns of the "spec" readings
        spec_df = df_raw.query("ID == 'spectralon'")
        spectralon_wavelengths = spec_df.iloc[:, -8:].mean()

        # preprocess known dataset
        def apply_snv_transform(row):
            specific_wavelengths = row[-8:]
            return self.snv_transform(specific_wavelengths, spectralon_wavelengths)

        # Apply the function to each row of the dataframe
        df_raw.iloc[:, -8:] = df_raw.iloc[:, -8:].apply(apply_snv_transform, axis=1)
        df_raw["PlasticNumber"] = df_raw["PlasticType"].map(
            {"PET": 1, "HDPE": 2, "PVC": 3, "LDPE": 4, "PP": 5, "PS": 6, "other": 7}
        )
        # print(df_raw["PlasticNumber"])

        types_to_train = ["PET", "HDPE", "PP", "PS"]
        self.df_train = df_raw[df_raw.PlasticType.isin(types_to_train)]

        self.datasetloaded = True

    def showDataset(self):
        if self.datasetloaded is None:
            self.loadDataset()
        for sample in self.df_train.index:
            self.axes.scatter(
                self.df_train["nm1050"],
                self.df_train["nm1450"],
                self.df_train["nm1650"],
                c=self.df_train["PlasticNumber"],
            )

    def threeD(
        self,
        data: List[float],
        color: Tuple[int] = (125, 125, 125),
        name: str = "",
    ) -> None:
        if len(color) != 3 or len(data) != 3:
            raise ValueError("argument may only contain 3 items")

        self.ctr += 1
        color = [(255, 0, 0), (0, 255, 0)][self.ctr % 2]
        name = ["red", "green"][self.ctr % 2]

        if color not in self.threeDdata:
            self.threeDdata[color] = []
            # the list just exists to make sure that the colors maintain their order
            self.threeDdata_colors.append(color)
            # add a series and make it the correct color
            if self.ctr % 2:
                series = QScatter3DSeries(self.scatter_proxy)
            else:
                series = QScatter3DSeries(self.scatter_proxy2)
            series.setName(name)
            series.setItemLabelFormat("@xLabel | @yLabel | @zLabel | @seriesName")
            series.setMeshSmooth(True)
            series.setBaseColor(QColor(*color))
            self.threeDgraph.addSeries(series)

        self.threeDdata[color].append(QScatterDataItem(QVector3D(*data)))

        #  self.threeDdata[color].append(QScatterDataItem(QVector3D(*data)))

        for idx, currcolor in enumerate(self.threeDdata_colors):
            #  print(f"{currcolor=}")
            self.threeDgraph.seriesList()[idx].dataProxy().resetArray(
                self.threeDdata[currcolor]
            )

            #  self.threeDgraph.seriesList()[0].dataProxy().resetArray(self.threeDdata[currcolor])

        #  if self.loadDatasetChbx.isChecked():
        #      self.axes.cla()
        #      self.showDataset()

        #  data = np.array(data)
        #  self.baseline = np.array(self.baseline)
        #  corrected = self.snv_transform(data,self.baseline)
        #  print("hier")
        #  self.axes.scatter(corrected[1],corrected[4],corrected[6], c= "red")

    def snv_transform(self, input_wavelengths, spectralon_wavelengths):
        # Divide specific wavelengths by reference wavelengths
        input_wavelengths = input_wavelengths / spectralon_wavelengths

        # Subtract the mean from each wavelength measurement
        input_wavelengths = input_wavelengths - input_wavelengths.mean()

        # Divide the resulting values by the standard deviation
        output_wavelengths = input_wavelengths / input_wavelengths.std()

        return output_wavelengths


if __name__ == "__main__":
    print(f"App is running on QT version {QT_VERSION_STR}")
    app = pg.mkQApp()

    # this should add some optimisations for high-DPI screens
    # https://pyqtgraph.readthedocs.io/en/latest/how_to_use.html#hidpi-displays
    QT_version = float("".join(QT_VERSION_STR.split(".")[:2]))
    if QT_version >= 5.14 and QT_version < 6:
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
        app.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    elif QT_version >= 5.14 and QT_version < 5.14:
        app.setAttribute(Qt.AA_EnableHighDpiScaling)
        app.setAttribute(Qt.AA_UseHighDpiPixmaps)

    window = PsPlot()
    window.show()
    app.exec()
