#!/usr/bin/env python

from threading import currentThread
from PyQt5.QtCore import Qt, pyqtSignal, QT_VERSION_STR
from PyQt5.QtGui import (
    QKeySequence,
    QKeyEvent,
    QColor,
    QPalette,
    QVector3D,
    QIcon,
    QWindow,
)
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QCompleter,
    QCheckBox,
    QDockWidget,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
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
        self.setWindowIcon(QIcon("logo3-01.png"))

        self.ctr = 0
        self.prevent_loop = False
        self.overwrite_no_callibration_warning = False
        self.fullscreen = False

        self.dataset_url = "https://raw.githubusercontent.com/Plastic-Scanner/data/main/data/20230117_DB2.1_second_dataset/measurement.csv"

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
        self.sample_materials = {
            "PP",
            "PET",
            "PS",
            "HDPE",
            "LDPE",
            "PVC",
            "spectralon",
            "unknown",
        }

        ## To keep track
        # used for also plotting previouse values
        self.old_data = deque(maxlen=3)
        # to keep track of the amount of calibrations done
        self.calibration_counter = 0
        # holds labers for each row
        self.row_labels = []
        # holds all of the names for all of the samples
        self.sample_labels = set()
        # colorblind friendly colors taken and adjusted from https://projects.susielu.com/viz-palette
        # ["#ffd700", "#ffb14e", "#fa8775", "#ea5f94", "#cd34b5", "#9d02d7", "#0000ff", "#2194F9"]
        self.color_tableau = (
            QColor(255, 215, 0),
            QColor(255, 177, 78),
            QColor(250, 135, 117),
            QColor(234, 95, 148),
            QColor(205, 52, 181),
            QColor(157, 2, 215),
            QColor(0, 0, 255),
            QColor(33, 148, 249),
        )
        self.theeDPlotAllowedLabel = [
            "PP",
            "PET",
            "PS",
            "HDPE",
            "LDPE",
            "PVC",
            "unknown",
            "other",
        ]
        self.threeDPlotColormap = {
            x: y for x, y in zip(self.theeDPlotAllowedLabel, self.color_tableau)
        }

        ## setting up the UI elements
        # input output (selecting serial and saving)
        self._setupInOutUI()
        # taking a measurement
        self._setupMeasureUI()
        # 2d Plot
        self._setupTwoDPlotUI()
        # 3d plot
        self._setupThreeDPlotUI()
        # histogram
        self._setupHistogramUI()
        # layout for graphs
        self.graphLayout = QHBoxLayout()
        self.graphLayout.setSpacing(20)
        self.graphLayout.addLayout(self.twoDPlotLayout, 50)
        self.graphLayout.addLayout(self.threeDPlotLayout, 50)
        self.graphLayout.addLayout(self.histogramPlotLayout, 50)
        # self.graphLayout.addWidget(self.threeDPlotWidget, 50)
        ## Table to display output
        self.tableHeader = ["name", "material"] + [str(x) for x in self.wavelengths]
        self.table = Table()
        self.table.setColumnCount(len(self.tableHeader))
        self.table.setHorizontalHeaderLabels(self.tableHeader)
        self.table.itemChanged.connect(self.tableChanged)
        # make the first 2 columns extra wide
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 200)

        ## add all layouts to mainLayout
        # Container widget
        self.widget = QWidget(self)
        self.setCentralWidget(self.widget)
        self.mainLayout = QVBoxLayout()
        self.mainLayout.setSpacing(10)
        self.mainLayout.addWidget(self.inoutBox)
        self.mainLayout.addWidget(self.measureBox)
        self.mainLayout.addLayout(self.graphLayout)
        self.mainLayout.addWidget(self.table)
        self.widget.setLayout(self.mainLayout)

        self.setWindowTitle("PSPlot")
        self.resize(1000, 600)
        self.setMinimumSize(600, 350)
        self.center()

        # Connect to the serial device (first, newest detected)
        self.serialScan()
        self.serialList.setCurrentIndex(0)
        self.serialConnect(0)

        # TODO update this to include all new widgets
        self.twoDPlotWidget.setFocus()
        self.widget.setTabOrder(self.twoDPlotWidget, self.serialList)

    def _setupInOutUI(self):
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
        self.loadDatasetLocalBtn = QPushButton("Load dataset from file")
        self.loadDatasetLocalBtn.clicked.connect(self.loadDatasetLocal)

        self.loadDatasetOnlineBtn = QPushButton("Load dataset from github")
        self.loadDatasetOnlineBtn.clicked.connect(self.loadDatasetOnline)

        # export and calibrate
        self.exportDataBtn = QPushButton("Export dataset to file")
        self.exportDataBtn.clicked.connect(self.exportCsv)

        # serial horizontal layout
        self.horizontalSerialLayout = QHBoxLayout()
        self.horizontalSerialLayout.addWidget(self.serialList)
        self.horizontalSerialLayout.addWidget(self.serialNotif)

        # load and save horizontal layout
        self.horizontalLoadSaveLayout = QHBoxLayout()
        self.horizontalLoadSaveLayout.addWidget(self.loadDatasetOnlineBtn)
        self.horizontalLoadSaveLayout.addWidget(self.loadDatasetLocalBtn)
        self.horizontalLoadSaveLayout.addWidget(self.exportDataBtn)

        self.inoutBoxLayout = QVBoxLayout()
        self.inoutBoxLayout.addLayout(self.horizontalSerialLayout)
        self.inoutBoxLayout.addLayout(self.horizontalLoadSaveLayout)
        self.inoutBox = QGroupBox("data in/out")
        self.inoutBox.setLayout(self.inoutBoxLayout)

    def _setupMeasureUI(self):
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
        # comment out the next line in case you only want to allow measurements after a calibration
        # self.regularMeasurementBtn.setDisabled(True)

        self.sampleNameInfoLabel = QLabel()
        self.sampleNameInfoLabel.setText("Sample name:")

        self.sampleNameSelection = QComboBox()
        self.sampleNameSelection.setDuplicatesEnabled(False)
        self.sampleNameSelection.setEditable(True)
        self.sampleNameSelection.currentIndexChanged.connect(
            self.sampleNameSelectionChanged
        )
        self.sampleNameSelection.setPlaceholderText("select sample name")

        self.sampleMaterialInfoLabel = QLabel()
        self.sampleMaterialInfoLabel.setText("Sample material:")

        self.sampleMaterialSelection = QComboBox()
        self.sampleMaterialSelection.setDuplicatesEnabled(False)
        self.sampleMaterialSelection.setEditable(True)
        self.sampleMaterialSelection.currentIndexChanged.connect(
            self.sampleMaterialSelectionChanged
        )
        self.sampleMaterialSelection.setPlaceholderText("select material")
        self.sampleMaterialSelection.addItems(sorted(list(self.sample_materials)))
        self.sampleMaterialSelection.setCurrentText("unknown")

        self.calibrationLayout = QHBoxLayout()
        self.calibrationLayout.addWidget(self.calibrateBtn)
        self.calibrationLayout.addWidget(self.clearCalibrationBtn)

        self.sampleNameLayout = QHBoxLayout()
        self.sampleNameLayout.addWidget(self.sampleNameInfoLabel, 25)
        self.sampleNameLayout.addWidget(self.sampleNameSelection, 75)

        self.sampleMaterialLayout = QHBoxLayout()
        self.sampleMaterialLayout.addWidget(self.sampleMaterialInfoLabel, 25)
        self.sampleMaterialLayout.addWidget(self.sampleMaterialSelection, 75)

        self.measureBoxLayout = QVBoxLayout()
        self.measureBoxLayout.addLayout(self.calibrationLayout)
        self.measureBoxLayout.addLayout(self.sampleNameLayout)
        self.measureBoxLayout.addLayout(self.sampleMaterialLayout)
        self.measureBoxLayout.addWidget(self.regularMeasurementBtn)

        self.measureBox = QGroupBox("measuring")
        self.measureBox.setLayout(self.measureBoxLayout)

    def _setupTwoDPlotUI(self):
        """sets up both the twoDPlotWidget, and its layout"""
        self.twoDPlotWidget = pg.PlotWidget(background=None)

        self.twoDPlotItem = self.twoDPlotWidget.getPlotItem()
        self.twoDPlotItem.hideButtons()
        self.twoDPlotItem.setMenuEnabled(False)
        self.twoDPlotItem.showGrid(x=True, y=True, alpha=0.5)
        self.twoDPlotItem.setMouseEnabled(x=False, y=True)

        self.pc = self.twoDPlotWidget.plot()
        self.pc.setSymbol("o")

        self.xPadding = min(self.wavelengths) * 0.1
        self.yPadding = 0.015
        self.yMin = 0
        self.yMax = 1.1
        self.twoDPlotItem.setLimits(
            xMin=min(self.wavelengths) - self.xPadding,
            xMax=max(self.wavelengths) + self.xPadding,
            yMin=0 - self.yPadding,
        )
        self.twoDPlotItem.setLabel("left", "NIR output", units="V", unitPrefix="m")
        self.twoDPlotItem.setLabel("bottom", "Wavelength (nm)")
        self.twoDPlotItem.getAxis("bottom").enableAutoSIPrefix(False)
        self.twoDPlotItem.setTitle("Reflectance")

        self.twoDPlotWidget.setXRange(
            self.wavelengths[0], self.wavelengths[-1], padding=0.1
        )
        self.twoDPlotWidget.setYRange(self.yMin, self.yMax, padding=self.yPadding)

        # Buttons for 2d plot
        # center, auto-restoreAxis and clear
        self.twoDAxisRestoreBtn = QPushButton("Restore axis")
        self.twoDAxisRestoreBtn.clicked.connect(self.twoDAxisRestoreBtnFunction)

        self.twoDAxisCenterBtn = QPushButton("Center axis")
        self.twoDAxisCenterBtn.clicked.connect(self.twoDAxisCenterBtnFunction)

        self.twoDClearPlotBtn = QPushButton("Clear graph")
        self.twoDClearPlotBtn.clicked.connect(self.clearGraph)

        self.twoDAutoBtnGroup = QButtonGroup()
        self.twoDAxisAutoRestoreChbx = QRadioButton("auto-restore axis")
        self.twoDAxisAutoRestoreChbx.clicked.connect(self.restoreAxisPlotChbxClick)
        self.twoDAutoBtnGroup.addButton(self.twoDAxisAutoRestoreChbx)
        self.twoDAxisAutoRangeChbx = QRadioButton("auto-center axis")
        self.twoDAxisAutoRangeChbx.clicked.connect(self.centerAxisPlotChbxClick)
        self.twoDAutoBtnGroup.addButton(self.twoDAxisAutoRangeChbx)

        self.twoDExportPlotBtn = QPushButton("Export graph")
        # self.exportPlotBtn.clicked.connect(self.exportGraph)

        self.twoDPlotControlLayout = QGridLayout()
        self.twoDPlotControlLayout.addWidget(self.twoDAxisRestoreBtn, 0, 0)
        self.twoDPlotControlLayout.addWidget(self.twoDAxisCenterBtn, 0, 1)
        self.twoDPlotControlLayout.addWidget(self.twoDClearPlotBtn, 0, 2)
        self.twoDPlotControlLayout.addWidget(self.twoDAxisAutoRestoreChbx, 1, 0)
        self.twoDPlotControlLayout.addWidget(self.twoDAxisAutoRangeChbx, 1, 1)
        self.twoDPlotControlLayout.addWidget(self.twoDExportPlotBtn, 1, 2)
        self.twoDPlotControlLayout.setSpacing(0)

        self.twoDPlotLayout = QVBoxLayout()
        self.twoDPlotLayout.addWidget(self.twoDPlotWidget, 80)
        self.twoDPlotLayout.addLayout(self.twoDPlotControlLayout, 20)

    def _setupThreeDPlotUI(self):
        self.threeDdata: Dict[Tuple[int], list[QScatterDataItem]] = dict()
        self.threeDdata_colors = []
        self.threeDgraph = Q3DScatter()
        self.threeDPlotWidget = QWidget.createWindowContainer(self.threeDgraph)

        self.threeDgraph.setOrthoProjection(True)
        self.threeDgraph.scene().activeCamera().setCameraPreset(
            Q3DCamera.CameraPresetIsometricLeft
        )
        self.threeDgraph.axisX().setTitle("1050 nm")
        self.threeDgraph.axisX().setTitleVisible(True)
        self.threeDgraph.axisX().setLabelFormat("%.4f")
        self.threeDgraph.axisY().setTitle("1450 nm")
        self.threeDgraph.axisY().setTitleVisible(True)
        self.threeDgraph.axisY().setLabelFormat("%.4f")
        self.threeDgraph.axisZ().setTitle("1650 nm")
        self.threeDgraph.axisZ().setTitleVisible(True)
        self.threeDgraph.axisZ().setLabelFormat("%.4f")

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
        fontsize = currentTheme.font().pointSizeF()
        font = currentTheme.font()
        font.setPointSizeF(4 * fontsize)
        currentTheme.setFont(font)

        # holds all of the scatterdataseries
        self.scatter_proxy = QScatterDataProxy()
        self.scatter_proxy2 = QScatterDataProxy()

        self.threeDClearPlotBtn = QPushButton("Clear graph")
        # self.threeDClearPlotBtn.clicked.connect()
        self.threeDExportPlotBtn = QPushButton("Export graph")
        # self.threeDExportPlotBtn.clicked.connect()

        self.threeDPlotControlLayout = QHBoxLayout()
        self.threeDPlotControlLayout.addWidget(self.threeDClearPlotBtn)
        self.threeDPlotControlLayout.addWidget(self.threeDExportPlotBtn)
        self.threeDPlotControlLayout.setSpacing(0)

        self.threeDPlotLayout = QVBoxLayout()
        self.threeDPlotLayout.addWidget(self.threeDPlotWidget, 80)
        self.threeDPlotLayout.addLayout(self.threeDPlotControlLayout, 20)

    def _setupHistogramUI(self):
        self.histogramPlotWidget = pg.PlotWidget(background=None)
        # self.histogramPlotItem = self.twoDPlotWidget.getPlotItem()
        self.histogramPlotWidget.hideButtons()
        self.histogramPlotWidget.setMenuEnabled(False)
        self.histogramPlotWidget.setMouseEnabled(x=False, y=False)
        self.histogramPlotWidget.setLimits(
            xMin=0,
            xMax=100,
            yMin=0,
        )
        self.histogramPlotWidget.setXRange(0, 100)

        # TODO replace this
        vertical_axis = {
            idx: name for idx, name in enumerate(self.sample_materials, start=1)
        }

        axis = self.histogramPlotWidget.getAxis("left")
        axis.setTicks([vertical_axis.items()])
        axis = self.histogramPlotWidget.getAxis("bottom")
        axis.setTicks([{x: str(x) for x in range(0, 120, 20)}.items()])
        fakedata = {
            name: value
            for name, value in zip(
                self.sample_materials,
                list(np.random.randint(0, 100, size=len(self.sample_materials))),
            )
        }
        self.plotHistogram(fakedata)

        self.histogramClearPlotBtn = QPushButton("Clear graph")
        # self.threeDClearPlotBtn.clicked.connect()
        self.histogramExportPlotBtn = QPushButton("Export graph")
        # self.threeDExportPlotBtn.clicked.connect()

        self.histogramPlotControlLayout = QHBoxLayout()
        self.histogramPlotControlLayout.addWidget(self.histogramClearPlotBtn)
        self.histogramPlotControlLayout.addWidget(self.histogramExportPlotBtn)
        self.histogramPlotControlLayout.setSpacing(0)

        self.histogramPlotLayout = QVBoxLayout()
        self.histogramPlotLayout.addWidget(self.histogramPlotWidget, 80)
        self.histogramPlotLayout.addLayout(self.histogramPlotControlLayout, 20)

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
        self.twoDPlotWidget.setFocus()
        if self.twoDAxisAutoRangeChbx.isChecked():
            # self.twoDAxisAutoRestoreChbx.setChecked(0)
            self.centerAxisPlot()

    def centerAxisPlot(self) -> None:
        # TODO make it so that this also corrects for baseline
        if len(self.old_data) > 0 or self.baseline is not None:
            # when coming from self.plot checking if it is checked is now done twice
            self.twoDPlotItem.getViewBox().autoRange()
            all_plotted_data = [x for y in self.old_data for x in y]
            if self.baseline is not None:
                all_plotted_data.extend(self.baseline)
            print(sorted(all_plotted_data))
            print(
                min(all_plotted_data) - self.yPadding,
            )
            print(
                max(all_plotted_data) - self.yPadding,
            )

            # self.twoDPlotWidgetItem.getViewBox().setYRange(
            self.twoDPlotWidget.setYRange(
                min(all_plotted_data),
                max(all_plotted_data),
                padding=self.yPadding,
            )
            # self.twoDPlotWidget.setYRange(self.yMin, self.yMax, padding=self.yPadding)

    def restoreAxisPlotChbxClick(self) -> None:
        self.twoDPlotWidget.setFocus()
        if self.twoDAxisAutoRestoreChbx.isChecked():
            # self.twoDAxisAutoRangeChbx.setChecked(0)
            self.restoreAxisPlot()

    def twoDAxisCenterBtnFunction(self):
        self.centerAxisPlot()
        self.twoDdisableAllChbx()

    def twoDAxisRestoreBtnFunction(self):
        self.restoreAxisPlotChbxClick()
        self.twoDdisableAllChbx()

    def twoDdisableAllChbx(self):
        # exclusive is used here because otherwise the currently selected chbx cannot be unchecked
        self.twoDAutoBtnGroup.setExclusive(False)
        for button in self.twoDAutoBtnGroup.buttons():
            button.setChecked(False)
        self.twoDAutoBtnGroup.setExclusive(True)

    def restoreAxisPlot(self) -> None:
        self.twoDPlotWidget.setXRange(
            self.wavelengths[0], self.wavelengths[-1], padding=0.1
        )
        self.twoDPlotWidget.setYRange(self.yMin, self.yMax, padding=self.yPadding)

    def clearGraph(self) -> None:
        self.old_data.clear()
        self.twoDPlotWidget.clear()
        self.axes.cla()

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() == Qt.Key.Key_Escape or e.key() == Qt.Key.Key_Q:
            self.close()

        elif (
            e.key() == Qt.Key.Key_Up
            or e.key() == Qt.Key.Key_W
            or e.key() == Qt.Key.Key_Plus
        ):
            self.twoDPlotItem.getViewBox().scaleBy((1, 0.9))

        elif (
            e.key() == Qt.Key.Key_Down
            or e.key() == Qt.Key.Key_S
            or e.key() == Qt.Key.Key_Minus
        ):
            self.twoDPlotItem.getViewBox().scaleBy((1, 1.1))

        elif e.key() == Qt.Key.Key_Left or e.key() == Qt.Key.Key_A:
            self.twoDPlotItem.getViewBox().translateBy((-10, 0))

        elif e.key() == Qt.Key.Key_Right or e.key() == Qt.Key.Key_D:
            self.twoDPlotItem.getViewBox().translateBy((+10, 0))

        elif e.key() == Qt.Key.Key_Home:
            self.twoDPlotWidget.setXRange(
                self.wavelengths[0], self.wavelengths[-1], padding=0.1
            )
            self.twoDPlotWidget.setYRange(self.yMin, self.yMax, padding=self.yPadding)

        elif e.key() == Qt.Key.Key_Space:
            self.takeRegularMeasurement()
        elif e.key() == Qt.Key.Key_F11:
            if not self.fullscreen:
                self.windowHandle().showFullScreen()
                self.fullscreen = True
            else:
                self.windowHandle().showNormal()
                self.fullscreen = False

    def takeRegularMeasurement(self):
        if (
            self.calibration_counter == 0
            and self.overwrite_no_callibration_warning == False
        ):
            button = QMessageBox.warning(
                self,
                "taking measurement",
                "No calibration is present are you sure you want to take a measurement?\n(if yes: PSPlot might crash)",
                QMessageBox.Yes,
                QMessageBox.No,
            )
            if button == QMessageBox.No:
                return
            else:
                self.overwrite_no_callibration_warning = True

        data = self.getMeasurement()
        self.addMeasurement(data)
        self.plotTwoD(data)
        self.threeD([data[1], data[4], data[6]])

    def addCalibrationMeasurement(self, data: List[float]) -> None:
        self.addToTable(data, calibrated_measurement=True)

    def addMeasurement(self, data: List[float]) -> None:
        name = self.sampleNameSelection.currentText()
        if name not in self.sample_labels:
            self.sample_labels.add(name)
            self.sampleNameSelection.addItem(name)

        material = self.sampleMaterialSelection.currentText()
        if material not in self.sample_materials:
            self.sample_materials.add(material)
            self.sampleMaterialSelection.addItem(material)

        # use calibration if possible
        if self.baseline is not None:
            dataCalibrated = [dat / base for dat, base in zip(data, self.baseline)]
            # data = dataCalibrated

        self.addToTable(data, name=name, material=material)

        self.old_data.append(data)

    def addToTable(
        self,
        data: List[float],
        name: str = "",
        material: str = "unknown",
        calibrated_measurement: bool = False,
    ) -> None:
        nRows = self.table.rowCount()
        # add a row
        self.table.setRowCount(nRows + 1)

        # add sample name as column 0
        self.table.setItem(nRows, 0, QTableWidgetItem(name))
        # add sample material as column 1
        self.table.setItem(nRows, 1, QTableWidgetItem(material))

        if calibrated_measurement:
            self.row_labels.append(f"c {self.calibration_counter}")
            self.table.setItem(nRows, 1, QTableWidgetItem("spectralon"))
        else:
            self.row_labels.append(str(nRows + 1 - self.calibration_counter))
        self.table.setVerticalHeaderLabels(self.row_labels)

        # add value for every column of new row
        dataStr = self.listToString(data)
        for col, val in enumerate(dataStr.split(), start=2):
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

        if button == QMessageBox.StandardButton.Yes:
            self.baseline = self.getMeasurement()
            self.calibration_counter += 1
            self.addCalibrationMeasurement(self.baseline)
            self.old_data.clear()

        self.plotTwoD()

    def clearCalibration(self) -> None:
        self.baseline = None
        self.plotTwoD(self.old_data[-1])

    def listToString(self, data: List[float]) -> str:
        return " ".join([f"{i:.7f}" for i in data])

    def tableChanged(self, item):
        # if it was a label that changed, add it to the list of labels
        if item.column() == 0:
            name = item.text()
            if name not in self.sample_labels:
                self.sample_labels.add(name)
                self.sampleNameSelection.addItem(name)

    def sampleNameSelectionChanged(self, name):
        if name not in self.sample_labels:
            self.sample_labels.add(name)

    def sampleMaterialSelectionChanged(self, name):
        if name not in self.sample_materials:
            self.sample_materials.add(name)

    def plotTwoD(self, data: Optional[List[float]] = None) -> None:
        # TODO remove this block:
        fakedata = {
            name: value
            for name, value in zip(
                self.sample_materials,
                list(np.random.randint(0, 100, size=len(self.sample_materials))),
            )
        }
        self.plotHistogram(fakedata)

        self.twoDPlotWidget.clear()
        self.baseline = np.array(self.baseline)

        # add the baseline of the last calibration
        if self.baseline is not None:
            normalizedbasline = self.baseline / self.baseline
            pc = self.twoDPlotWidget.plot(
                self.wavelengths, normalizedbasline, pen=(255, 0, 0)
            )

        for dat in self.old_data:
            dat = np.array(dat)
            normalizedolddat = dat / self.baseline
            pc = self.twoDPlotWidget.plot(
                self.wavelengths,
                normalizedolddat,
                pen=(0, 100, 0),
                symbolBrush=(0, 255, 0),
            )
            pc.setSymbol("x")

        lineC = tuple(
            self.twoDPlotWidget.palette()
            .color(QPalette.ColorRole.WindowText)
            .getRgb()[:-1]
        )
        markC = tuple(
            self.twoDPlotWidget.palette()
            .color(QPalette.ColorRole.Highlight)
            .getRgb()[:-1]
        )
        pen = pg.mkPen(color=lineC, symbolBrush=markC, symbolPen="o", width=2)
        if data is not None:
            data = np.array(data)
            normalizeddata = data / self.baseline
            pc = self.twoDPlotWidget.plot(self.wavelengths, normalizeddata, pen=pen)
            pc.setSymbol("o")

        if self.twoDAxisAutoRestoreChbx.isChecked():
            self.restoreAxisPlot()
        if self.twoDAxisAutoRangeChbx.isChecked():
            self.centerAxisPlot()

    def plotHistogram(self, data: Dict[str, int]) -> None:
        self.histogramPlotWidget.clear()
        yticks = list(range(1, len(data) + 1))
        widths = list(data.values())
        self.histogramPlotWidget.setYRange(0, len(data) + 0.5)
        self.bars = pg.BarGraphItem(
            x0=0,
            y=yticks,
            height=0.8,
            width=widths,
        )
        self.bars.setOpts(
            brushes=[
                QColor(self.palette().highlight().color()) for _ in range(len(data))
            ]
        )
        self.histogramPlotWidget.addItem(self.bars)
        # draw the text for each bar
        for x, y in zip(widths, yticks):
            if x >= 50:
                text = pg.TextItem(str(x), anchor=(1, 0.5))
                text.setPos(x, y)
            else:
                text = pg.TextItem(str(x), anchor=(0, 0.5))
                text.setPos(x, y)

            self.histogramPlotWidget.addItem(text)

    def loadDatasetOnline(self):
        QMessageBox.information(
            self, "loading dataset", f"Dataset is loaded from url:\n{self.dataset_url}"
        )
        self.loadDataset(self.dataset_url)

    def loadDatasetLocal(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Load dataset",
            "",
            "CSV (*.csv);;All Files (*)",
        )
        if not filename:
            QMessageBox.information(self, "loading dataset", "No file was selected")
        else:
            self.loadDataset(filename)

    def loadDataset(self, dataset_path: str):
        # the goal here is to load a dataset to visualize in the 3D scatterplot
        # import the dataframe
        df_raw = pd.read_csv(dataset_path)
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
            button = QMessageBox.warning(
                self,
                "showing dataset",
                "a dataset must first be loaded, woud you like to load the online dataset?",
                QMessageBox.Yes,
                QMessageBox.No,
            )
            if button == QMessageBox.Yes:
                self.loadDatasetOnline()
            else:
                return

        for sample in self.df_train.index:
            self.axes.scatter(
                self.df_train["nm1050"],
                self.df_train["nm1450"],
                self.df_train["nm1650"],
                c=self.df_train["PlasticNumber"],
            )

    def exportCsv(self) -> None:
        fname, _ = QFileDialog.getSaveFileName(
            self,
            "Save File",
            "",
            "CSV (*.csv);;All Files (*)",
        )
        if not fname:
            QMessageBox.information(self, "saving dataset", "No file was selected")
        else:
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

    def threeD(
        self,
        data: List[float],
        color: Tuple[int] = (125, 125, 125),
        name: str = "",
    ) -> None:
        """
        Plan of attack
        - per kleur is er één proxy nodig, een proxy houd series vast
        """
        if len(color) != 3 or len(data) != 3:
            raise ValueError("argument may only contain 3 items")

        self.ctr += 1
        # color = [(255, 0, 0), (0, 255, 0)][self.ctr % 2]
        # name = ["red", "green"][self.ctr % 2]
        name = list(self.sample_materials)[self.ctr % 7]
        color = list(self.sample_materials)[self.ctr % 7]
        color2 = self.color_tableau[np.random.randint(0, len(self.color_tableau))]

        if color not in self.threeDdata:
            self.threeDdata[color] = []
            # the list just exists to make sure that the colors maintain their order
            self.threeDdata_colors.append(color)
            # add a series and make it the correct color
            if self.ctr % 2:
                # series = QScatter3DSeries(self.scatter_proxy)
                series = QScatter3DSeries()
            else:
                # series = QScatter3DSeries(self.scatter_proxy2)
                series = QScatter3DSeries()
            series.setName(name)
            series.setItemLabelFormat("@xLabel | @yLabel | @zLabel | @seriesName")
            series.setMeshSmooth(True)
            series.setBaseColor(color2)
            self.threeDgraph.addSeries(series)

        self.threeDdata[color].append(QScatterDataItem(QVector3D(*data)))

        #  self.threeDdata[color].append(QScatterDataItem(QVector3D(*data)))

        for idx, currcolor in enumerate(self.threeDdata_colors):
            print(f"{idx}")
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

    app.setStyle("Fusion")
    window = PsPlot()
    window.show()
    app.exec()
