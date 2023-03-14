#!/usr/bin/env python

from types import NoneType
from PyQt5.QtCore import Qt, pyqtSignal, QT_VERSION_STR
from PyQt5.QtGui import (
    QColor,
    QIcon,
    QKeyEvent,
)
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from datetime import datetime
from typing import List, Union
from plot_layouts import Histogram, ScatterPlot2D, ScatterPlot3D
from helper_functions import normalize, SNV_transform, list_to_string
import joblib
import os
import pandas as pd

# pyqtgraph should always be imported after importing pyqt
import pyqtgraph as pg
import random
import serial
import serial.tools.list_ports
import time


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
        self.setWindowIcon(QIcon("./resources/ps_logo.png"))

        # HARDCODED SETTINGS
        self.WAVELENGTHS = [
            940,
            1050,
            1200,
            1300,
            1450,
            1550,
            1650,
            1720,
        ]  # in nanometers
        self.BAUDRATE = 9600
        self.DATASET_URL = "https://raw.githubusercontent.com/Plastic-Scanner/data/main/data/20230117_DB2.1_second_dataset/measurement.csv"

        self.serial = None

        # the names of the columns of the table
        self.TABLE_HEADER = ["name", "material", "color"] + [str(x) for x in self.WAVELENGTHS]
        # the columns of the dataframe that are represented in the table
        self.TABLE_DATAFRAME_SUBSET_HEADERS = [f"nm{x}" for x in self.WAVELENGTHS]

        # the headers for the dataframe:
        # |  Reading                |   the how many'th measurement                   |
        # |  Name                   |   name or id of the piece                       |
        # |  PlasticType            |   type of the plastic                           |
        # |  Color                  |   physical color of the piece of plastic        |
        # |  MeasurementType        |   if the measurement was a calibration or not   | options: regular, calibration
        # |  nm<wavelengths>        |   measured signal per wavelength                |
        # |  nm<wavelengths>_norm   |   signal per wavelength after normalization     |
        self.DF_HEADER = (
            [
                "Name",
                "PlasticType",
                "Color",
                "MeasurementType",
                "DateTime",
            ]
            + [f"nm{x}" for x in self.WAVELENGTHS]
            + [f"nm{x}_snv" for x in self.WAVELENGTHS]
            + [f"nm{x}_norm" for x in self.WAVELENGTHS]
        )
        self.DF_HEADER_DTYPES = (
            {
                "Name": str,
                "PlasticType": str,
                "Color": str,
                "MeasurementType": str,
                "DateTime": str,
            }
            | {f"nm{x}": float for x in self.WAVELENGTHS}
            | {f"nm{x}_snv": float for x in self.WAVELENGTHS}
            | {f"nm{x}_norm": float for x in self.WAVELENGTHS}
        )
        # the columns of the dataframe that are used for the classifier model
        self.PREDICTION_HEADERS = [f"nm{x}" for x in self.WAVELENGTHS]

        self.SCATTER3D_AXIS_OPTIONS = (
            [f"nm{x}" for x in self.WAVELENGTHS]
            + [f"nm{x}_snv" for x in self.WAVELENGTHS]
            + [f"nm{x}_norm" for x in self.WAVELENGTHS]
        )

        self.SCATTER3D_AXIS_VAR_X_DEFAULT = "nm1050_norm"
        self.SCATTER3D_AXIS_VAR_Y_DEFAULT = "nm1450_norm"
        self.SCATTER3D_AXIS_VAR_Z_DEFAULT = "nm1650_norm"

        # colorblind friendly colors taken and adjusted from https://projects.susielu.com/viz-palette
        # ["#ffd700", "#ffb14e", "#fa8775", "#ea5f94",
        #  "#cd34b5", "#9d02d7", "#0000ff", "#2194F9"]
        self.COLOR_TABLEAU = (
            QColor(255, 215, 0),
            QColor(255, 177, 78),
            QColor(250, 135, 117),
            QColor(234, 95, 148),
            QColor(205, 52, 181),
            QColor(157, 2, 215),
            QColor(33, 148, 249),
            QColor(0, 0, 255),
        )
        self.SCATTER3D_ALLOWED_MATERIALS = [
            "PP",
            "PET",
            "PS",
            "HDPE",
            "LDPE",
            "PVC",
            "other",
            "unknown",
        ]
        self.SCATTER3D_COLOR_MAP = {
            x: y
            for x, y in zip(
                self.SCATTER3D_ALLOWED_MATERIALS,
                self.COLOR_TABLEAU,
            )
        }

        self.df = pd.DataFrame(columns=self.DF_HEADER)

        # classifier model used to predict type of plastic
        self.clf = joblib.load("./resources/model.joblib")

        # keeps track of all of the samples that have been measured
        self.DEFAULT_SAMPLE_MATERIALS = [
            "PP",
            "PET",
            "PS",
            "HDPE",
            "LDPE",
            "PVC",
            "spectralon",
            "unknown",
        ]
        self.sample_materials = self.DEFAULT_SAMPLE_MATERIALS.copy()

        # holds the calibration measurement
        self.baseline: Union[NoneType, List[float]] = None

        self.sample_colors = {""}
        self.sample_names = {""}

        self.fullscreen = False
        self.overwrite_no_callibration_warning = False
        # true when self.storeMeasurement is active
        self.currently_storing = False

        # all the values that were last plotted
        self.twoDPlottedList = []
        # to keep track of the amount of calibrations done in the current session
        self.current_calibration_counter = 0
        # the amount of calibrations done in the current session + the previous sessions
        self.total_calibration_counter = 0
        # holds labels for each row of the table, calibration rows are labeled differently
        self.tableRowLabels = []

        ## setting up the UI elements
        # input output (selecting serial and saving)
        self._setupInOutUI()
        # taking a measurement
        self._setupMeasureUI()
        # 2d Plot
        self.scatter2d = ScatterPlot2D(self)
        # 3d plot
        self.scatter3d = ScatterPlot3D(self)
        # histogram
        self.histogram = Histogram(self)

        # layout for graphs
        self.graphLayout = QHBoxLayout()
        self.graphLayout.setSpacing(20)
        self.graphLayout.addLayout(self.scatter2d, 50)
        self.graphLayout.addLayout(self.scatter3d, 50)
        self.graphLayout.addLayout(self.histogram, 50)

        ## Table to display output
        self.table = Table()
        self.table.setColumnCount(len(self.TABLE_HEADER))
        self.table.setHorizontalHeaderLabels(self.TABLE_HEADER)
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
        self.serial_scan()
        self.serialComboBox.setCurrentIndex(0)
        self.serial_connect()

        # TODO update this to include all new widgets
        self.scatter2d._plotWidget.setFocus()
        self.widget.setTabOrder(self.scatter2d.plotWidget, self.serialComboBox)

    def _setupInOutUI(self):
        # selecting serial
        self.serialComboBox = ComboBox()
        self.serialComboBox.onPopup.connect(self.serial_scan)
        self.serialComboBox.activated.connect(self.serial_connect)
        # make it take up the maximum possible space
        self.serialComboBox.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        # serial notification
        self.serialNotifLbl = QLabel()

        # loading and saving
        self.loadDatasetLocalBtn = QPushButton("Load dataset from file")
        self.loadDatasetLocalBtn.clicked.connect(self.load_dataset_local)

        self.loadDatasetOnlineBtn = QPushButton("Load dataset from github")
        self.loadDatasetOnlineBtn.clicked.connect(self.load_dataset_online)

        # export and calibrate
        self.exportDataBtn = QPushButton("Export dataset to file")
        self.exportDataBtn.clicked.connect(self.exportCsv)

        # serial horizontal layout
        self.horizontalSerialLayout = QHBoxLayout()
        self.horizontalSerialLayout.addWidget(self.serialComboBox)
        self.horizontalSerialLayout.addWidget(self.serialNotifLbl)

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
        self.regularMeasurementBtn = QPushButton("Take measurement\n(shortcut: spacebar)")
        self.regularMeasurementBtn.setToolTip("a calibration measurement needs to be taken first")
        self.regularMeasurementBtn.clicked.connect(self.takeRegularMeasurement)
        # comment out the next line in case you only want to allow measurements after a calibration
        # self.regularMeasurementBtn.setDisabled(True)

        # sample material
        self.sampleMaterialInfoLabel = QLabel()
        self.sampleMaterialInfoLabel.setText("Sample material:")

        self.sampleMaterialSelection = QComboBox()
        self.sampleMaterialSelection.setDuplicatesEnabled(False)
        self.sampleMaterialSelection.setEditable(True)
        # self.sampleMaterialSelection.currentIndexChanged.connect(
        #     self.sampleMaterialSelectionChanged
        # )
        self.sampleMaterialSelection.setPlaceholderText("select material")
        self.sampleMaterialSelection.addItems(sorted(self.sample_materials))
        self.sampleMaterialSelection.setCurrentText("unknown")

        # sample name
        self.sampleNameInfoLabel = QLabel()
        self.sampleNameInfoLabel.setText("Sample name:")

        self.sampleNameSelection = QComboBox()
        self.sampleNameSelection.setDuplicatesEnabled(False)
        self.sampleNameSelection.setEditable(True)
        self.sampleNameSelection.addItem("")
        # self.sampleNameSelection.currentIndexChanged.connect(
        #     self.sampleNameSelectionChanged
        # )
        self.sampleNameSelection.setPlaceholderText("select sample name")

        # sample color
        self.sampleColorInfoLabel = QLabel()
        self.sampleColorInfoLabel.setText("Sample color:")

        self.sampleColorSelection = QComboBox()
        self.sampleColorSelection.setDuplicatesEnabled(False)
        self.sampleColorSelection.setEditable(True)
        self.sampleColorSelection.addItem("")
        # self.sampleColorSelection.currentIndexChanged.connect(
        #     self.sampleColorSelectionChanged
        # )
        self.sampleColorSelection.setPlaceholderText("select sample name")

        self.calibrationLayout = QHBoxLayout()
        self.calibrationLayout.addWidget(self.calibrateBtn)
        self.calibrationLayout.addWidget(self.clearCalibrationBtn)

        self.sampleNameLayout = QHBoxLayout()
        self.sampleNameLayout.addWidget(self.sampleNameInfoLabel, 25)
        self.sampleNameLayout.addWidget(self.sampleNameSelection, 75)

        self.sampleMaterialLayout = QHBoxLayout()
        self.sampleMaterialLayout.addWidget(self.sampleMaterialInfoLabel, 25)
        self.sampleMaterialLayout.addWidget(self.sampleMaterialSelection, 75)

        self.sampleColorLayout = QHBoxLayout()
        self.sampleColorLayout.addWidget(self.sampleColorInfoLabel, 25)
        self.sampleColorLayout.addWidget(self.sampleColorSelection, 75)

        self.measureBoxLayout = QVBoxLayout()
        self.measureBoxLayout.addLayout(self.calibrationLayout)
        self.measureBoxLayout.addLayout(self.sampleNameLayout)
        self.measureBoxLayout.addLayout(self.sampleMaterialLayout)
        self.measureBoxLayout.addLayout(self.sampleColorLayout)
        self.measureBoxLayout.addWidget(self.regularMeasurementBtn)

        self.measureBox = QGroupBox("measuring")
        self.measureBox.setLayout(self.measureBoxLayout)

    def keyPressEvent(self, e: QKeyEvent):
        # if e.key() == Qt.Key.Key_Escape or e.key() == Qt.Key.Key_Q:
        if e.key() == Qt.Key.Key_Q:
            self.close()

        elif e.key() == Qt.Key.Key_Up or e.key() == Qt.Key.Key_W or e.key() == Qt.Key.Key_Plus:
            self.scatter2d._viewBox.scaleBy((1, 0.9))

        elif e.key() == Qt.Key.Key_Down or e.key() == Qt.Key.Key_S or e.key() == Qt.Key.Key_Minus:
            self.scatter2d._viewBox.scaleBy((1, 1.1))

        elif e.key() == Qt.Key.Key_Home:
            self.scatter2d._plotWidget.setXRange(
                self.WAVELENGTHS[0], self.WAVELENGTHS[-1], padding=0.1
            )
            self.scatter2d._plotWidget.setYRange(self.yMin, self.yMax, padding=self.yPadding)

        elif e.key() == Qt.Key.Key_Space:
            self.takeRegularMeasurement()
        elif e.key() == Qt.Key.Key_F11:
            if not self.fullscreen:
                self.windowHandle().showFullScreen()
                self.fullscreen = True
            else:
                self.windowHandle().showNormal()
                self.fullscreen = False

    def center(self):
        """centers the window to the center of the screen"""
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def serial_scan(self) -> None:
        """Scans for available serial devices and updates the list"""

        self.serialComboBox.clear()
        self.serialComboBox.insertItem(0, "None")
        for dev in list(serial.tools.list_ports.comports()):
            self.serialComboBox.insertItem(0, dev.device)

    def serial_connect(self) -> None:
        """Connects to the serial device (e.g. /dev/ttyACM0)"""

        if self.serial is not None:
            self.serial.close()  # Close previously opened port, if exist

        port = self.serialComboBox.currentText()

        try:
            self.serial = serial.Serial(port, baudrate=self.BAUDRATE, timeout=1)
            print(f"Opened serial port {self.serial.portstr}")
            self.serialNotifLbl.setText("Using real data")
            time.sleep(1)
            self.serial.readline()  # Consume the "Plastic scanner initialized" line
        except serial.serialutil.SerialException:
            print(f"Cannot open serial port '{port}', using dummy data")
            self.serial = None
            self.serialNotifLbl.setText("Using dummy data")
        except Exception:
            print(f"Can't open serial port '{port}', using dummy data")
            self.serial = None
            self.serialNotifLbl.setText("Using dummy data")

    def takeRegularMeasurement(self):
        if (
            self.current_calibration_counter == 0
            and self.overwrite_no_callibration_warning is False
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
        self.scatter2d.plot(SNV_transform(data))
        self.scatter3d.plot()
        self.histogram.plot()
        # self.plotThreeD([data[1], data[4], data[6]])

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

    def addMeasurement(self, data: List[float]) -> None:
        material = self.sampleMaterialSelection.currentText().rstrip()
        if material not in self.sample_materials:
            self.sample_materials.append(material)
            self.sampleMaterialSelection.addItem(material)

        name = self.sampleNameSelection.currentText().rstrip()
        if name not in self.sample_names:
            self.sample_names.add(name)
            self.sampleNameSelection.addItem(name)

        color = self.sampleColorSelection.currentText().rstrip()
        if color not in self.sample_colors:
            self.sample_colors.add(color)
            self.sampleColorSelection.addItem(color)

        self.storeMeasurement(data, name=name, material=material, color=color)

    def storeMeasurement(
        self,
        data: List[float],
        name: str = "",
        material: str = "unknown",
        color: str = "",
        calibrated_measurement: bool = False,
    ):
        """adds newest measurement to table and dataframe"""

        data_snv = SNV_transform(data)

        if calibrated_measurement:
            data_normalized = [1] * len(data)
        else:
            if self.baseline is not None:
                data_normalized = normalize(data, self.baseline)
            else:
                data_normalized = [None] * len(data)

        self.currently_storing = True
        self.addToDataframe(
            data,
            data_snv,
            data_normalized,
            name,
            material,
            color,
            calibrated_measurement,
        )
        self.addToTable(
            data,
            name,
            material,
            color,
            calibrated_measurement,
        )

        if not calibrated_measurement:
            if material not in self.scatter3d.unique_series:
                self.scatter3d.unique_series[material] = {}
            if name not in self.scatter3d.unique_series[material]:
                self.scatter3d.unique_series[material][name] = {"data": []}

            self.scatter3d.unique_series[material][name]["data"].append(
                data + data_snv + data_normalized
            )

        self.currently_storing = False

    def addToDataframe(
        self,
        data: List[float],
        data_snv: List[float],
        data_normalized: List[Union[float, None]],
        name: str = "",
        material: str = "unknown",
        color: str = "",
        calibrated_measurement: bool = False,
    ):
        if calibrated_measurement:
            measurement_type = "calibration"
        else:
            measurement_type = "regular"

        self.df.loc[len(self.df)] = [
            name,
            material,
            color,
            measurement_type,
            datetime.now(),
            *data,
            *data_snv,
            *data_normalized,
        ]

    def addToTable(
        self,
        data: List[float],
        name: str = "",
        material: str = "unknown",
        color: str = "",
        calibrated_measurement: bool = False,
    ) -> None:
        nRows = self.table.rowCount()
        # add a row
        self.table.setRowCount(nRows + 1)

        # add sample name as column 0
        self.table.setItem(nRows, 0, QTableWidgetItem(name))
        # add sample material as column 1
        self.table.setItem(nRows, 1, QTableWidgetItem(material))
        # add sample color as column 2
        self.table.setItem(nRows, 2, QTableWidgetItem(color))

        if calibrated_measurement:
            self.tableRowLabels.append(f"c {self.total_calibration_counter}")
            self.table.setItem(nRows, 1, QTableWidgetItem("spectralon"))
        else:
            self.tableRowLabels.append(str(nRows + 1 - self.total_calibration_counter))
        self.table.setVerticalHeaderLabels(self.tableRowLabels)

        # add value for every column of new row
        dataStr = list_to_string(data)
        for col, val in enumerate(dataStr.split(), start=3):
            cell = QTableWidgetItem(val)
            cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)  # disable editing of cells

            # use a different color if the measurement was taken for calibration
            self.table.setItem(nRows, col, cell)

        if calibrated_measurement:
            for column in range(self.table.columnCount()):
                self.table.item(nRows, column).setBackground(self.palette().alternateBase().color())

        self.table.scrollToBottom()

    def calibrate(self) -> None:
        button = QMessageBox.question(
            self, "Calibration", "Is the spectralon sample on the sensor?"
        )

        if button == QMessageBox.StandardButton.Yes:
            # if this is the first calibration, enable certain buttons
            if self.current_calibration_counter == 0:
                self.clearCalibrationBtn.setEnabled(True)
                self.regularMeasurementBtn.setEnabled(True)
                self.regularMeasurementBtn.setToolTip("")

            self.baseline = self.getMeasurement()
            self.current_calibration_counter += 1
            self.total_calibration_counter += 1
            self.storeMeasurement(self.baseline, calibrated_measurement=True)

            # after a calibration calibration the plot is cleared
            self.scatter2d.plot()

    def clearCalibration(self) -> None:
        self.baseline = None
        # after a calibration calibration the plot is cleared
        self.twoDPlottedList.clear()
        self.scatter2d.clear()

    def tableChanged(self, item):
        # if it was a label that changed, add it to the list of labels
        if item.column() == 0:
            name = item.text()
            if name not in self.sample_names:
                self.sample_names.add(name)
                self.sampleNameSelection.addItem(name)
        # if it was a material that changed, add it to the list of materials
        elif item.column() == 1:
            name = item.text()
            if name not in self.sample_materials:
                self.sample_materials.append(name)
                self.sampleMaterialSelection.addItem(name)

        # also update the change in the dataframe
        if not self.currently_storing:
            column = item.column()
            # the header of the dataframe contains the `DateTime` header which is not
            # present in the table, and has to be compensated for
            if column >= 4:
                column -= 1
            self.df.loc[item.row(), self.DF_HEADER[column]] = item.text()

    def load_dataset_online(self):
        QMessageBox.information(
            self, "loading dataset", f"Dataset is loaded from url:\n{self.DATASET_URL}"
        )
        self.loadDataset(self.DATASET_URL)

    def load_dataset_local(self):
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

    def _loadDatasetWarning(self) -> bool:
        """returns true if user is sure"""
        button = QMessageBox.warning(
            self,
            "Load dataset",
            "You are about to overwrite the data that is displayed by the table.\nAre you sure you want to overwrite?",
            QMessageBox.Yes,
            QMessageBox.No,
        )
        return button == QMessageBox.Yes

    def _loadDatasetWarningReally(self) -> bool:
        button = QMessageBox.warning(
            self,
            "Load dataset",
            "Are you really sure?",
            QMessageBox.Yes,
            QMessageBox.No,
        )
        return button == QMessageBox.Yes

    def loadDataset(self, dataset_path: str):
        """load a dataset to continue where that dataset last left off"""
        # give warnings that there is data and it will get overwritten
        if len(self.df) > 0:
            if not (self._loadDatasetWarning() and self._loadDatasetWarningReally()):
                return

        new_df = pd.read_csv(dataset_path, index_col="Reading", dtype=self.DF_HEADER_DTYPES)
        if list(new_df.columns) != self.DF_HEADER:
            QMessageBox.critical(
                self,
                "Load dataset",
                "Dataset could not be loaded because of unexpected columns\n\n"
                + f"columns of new dataset:\n {new_df.columns}\n\n"
                + f"expected columns for a dataset:\n {self.DF_HEADER}\n\n"
                + "COULD NOT LOAD NEW DATASET!\n\n"
                + "For help, please contact the PlasticScanner Team",
            )
            return

        self.df = new_df

        ## clear plots
        # clear 3d plot
        self.scatter3d.clear()
        # build the datastructure needed for 3dplot
        self.scatter3d.unique_series = {
            material: {} for material in self.df["PlasticType"].unique()
        }
        for _, row in self.df.iterrows():
            name = row["Name"]
            material = row["PlasticType"]
            if name not in self.scatter3d.unique_series[material]:
                self.scatter3d.unique_series[material][name] = {"data": []}

            self.scatter3d.unique_series[material][name]["data"].append(
                row[self.SCATTER3D_AXIS_OPTIONS]
            )

        # clear 2d plot and histogram
        self.scatter2d.clear()
        self.histogram.clear()

        ## reset variables
        # reset calibration counter
        self.sample_names = set(self.df["Name"])
        self.sample_colors = set(self.df["Color"])
        self.sample_materials = self.DEFAULT_SAMPLE_MATERIALS.copy()
        self.sample_materials.extend(list(set(self.df["PlasticType"]) - set(self.sample_materials)))
        self.current_calibration_counter = 0
        self.total_calibration_counter = 0
        self.clearCalibration()

        ## write dataframe to table
        # clear table an variable
        self.table.clearContents()
        self.table.setRowCount(0)
        self.tableRowLabels = []
        # build table
        for _idx, row in self.df.iterrows():
            name = row["Name"] if isinstance(row["Name"], str) else ""
            plasticType = row["PlasticType"] if isinstance(row["PlasticType"], str) else ""
            color = row["Color"] if isinstance(row["Color"], str) else ""
            if row["MeasurementType"] == "calibration":
                self.total_calibration_counter += 1
                self.addToTable(
                    row[self.TABLE_DATAFRAME_SUBSET_HEADERS],
                    name=name,
                    material=plasticType,
                    color=color,
                    calibrated_measurement=True,
                )
            else:
                self.addToTable(
                    row[self.TABLE_DATAFRAME_SUBSET_HEADERS],
                    name=name,
                    material=plasticType,
                    color=color,
                    calibrated_measurement=False,
                )

        self.scatter2d.plot()
        self.scatter3d.plot()

    def exportCsv(self) -> None:
        fname, _ = QFileDialog.getSaveFileName(
            self,
            "Save File",
            "",
            "CSV(*.csv);;All Files(*)",
        )
        if not fname:
            QMessageBox.information(self, "saving dataset", "No file was selected")
        else:
            if "." not in fname:
                fname = fname + ".csv"
            self.df.to_csv(fname, index_label="Reading")


if __name__ == "__main__":
    print(f"App is running on QT version {QT_VERSION_STR}")
    app = pg.mkQApp()

    # this should add some optimisations for high-DPI screens
    # https://pyqtgraph.readthedocs.io/en/latest/how_to_use.html#hidpi-displays
    QT_version = float("".join(QT_VERSION_STR.split(".")[:2]))
    if QT_version >= 5.14 and QT_version < 6:
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
        app.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    elif QT_version >= 5.14 and QT_version < 5.14:
        app.setAttribute(Qt.AA_EnableHighDpiScaling)
        app.setAttribute(Qt.AA_UseHighDpiPixmaps)
    pg.setConfigOptions(antialias=True)  # , crashWarning=True)

    app.setStyle("Fusion")
    window = PsPlot()
    window.show()
    app.exec()
