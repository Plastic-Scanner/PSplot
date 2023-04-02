#!/usr/bin/env python

from __future__ import annotations

import os
import random
import time
from datetime import datetime

import joblib
import pandas as pd

import serial
import serial.tools.list_ports
from PyQt5.QtCore import QT_VERSION_STR, Qt
from PyQt5.QtGui import (
    QIcon,
    QKeyEvent,
)
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# pyqtgraph should always be imported after importing pyqt
import pyqtgraph as pg

import settings
from helper_functions import normalize, snv_transform
from visualisation_components import Histogram, ScatterPlot2D, ScatterPlot3D, Table


class PsPlot(QMainWindow):
    """main class and main window of the PSPlot program:
    manages multiple things:
        - serial communication with measurement device
        - generating dummy data when real measurement device is not picked up
        - adding measurements to dataframe
        - loading dataframe from (online and offline sources)
        - exporting dataframe

    NOTE: I am aware that managing multiple things is bad cohesion.
    But it makes it easier to manage for now.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowIcon(QIcon(settings.GUI.WINDOW_LOGO))

        self._setup_variables()
        self._setup_ui()

        # Connect to the serial device (first, newest detected)
        self.serial_scan()
        self.serialComboBox.setCurrentIndex(0)
        self.serial_connect()

        # set focus to the 2d scatter plot
        # NOTE update this to include all new widgets
        self.scatter2d._plotWidget.setFocus()
        self.widget.setTabOrder(self.scatter2d.plotWidget, self.serialComboBox)

    def _setup_variables(self) -> None:
        self.serial = None

        self.df = pd.DataFrame(columns=settings.DATAFRAME.HEADER)

        # classifier model used to predict type of plastic
        self.clf = joblib.load("./resources/model.joblib")

        # keeps track of all of the samples that have been measured
        self.sample_materials = settings.USER_INPUT.DEFAULT_SAMPLE_MATERIALS.copy()

        # holds the calibration measurement
        self.baseline: list[float] | None = None

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

    def _setup_ui(self) -> None:
        # input output (selecting serial and saving)
        self._setup_in_out_ui()
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

        # Table to display output
        self.table = Table()
        # self.table.itemChanged.connect(lambda _: print("iets"))
        self.table.user_change.connect(self._update_df_after_table_change)

        # add all layouts to mainLayout
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

    def _setup_in_out_ui(self) -> None:
        # selecting serial
        self.serialComboBox = QComboBox()
        self.serialComboBox.activated.connect(self.serial_scan)
        self.serialComboBox.currentTextChanged.connect(self.serial_connect)
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
        self.exportDataBtn.clicked.connect(self.export_to_csv)

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

    def _setupMeasureUI(self) -> None:
        # calibration
        self.calibrateBtn = QPushButton("Calibrate with spectralon")
        self.calibrateBtn.clicked.connect(self.calibrate)

        self.clearCalibrationBtn = QPushButton("Clear Calibration")
        self.clearCalibrationBtn.clicked.connect(self.clear_calibration)
        self.clearCalibrationBtn.setDisabled(True)

        # the next two buttons will be enabled after a calibration has been performed
        self.regularMeasurementBtn = QPushButton("Take measurement\n(shortcut: spacebar)")
        self.regularMeasurementBtn.setToolTip("a calibration measurement needs to be taken first")
        self.regularMeasurementBtn.clicked.connect(self.regular_measurement)
        # enable the next line in case you only want to allow measurements after a calibration
        # self.regularMeasurementBtn.setDisabled(True)

        # sample material
        self.sampleMaterialInfoLabel = QLabel()
        self.sampleMaterialInfoLabel.setText("Sample material:")

        self.sampleMaterialSelection = QComboBox()
        self.sampleMaterialSelection.setDuplicatesEnabled(False)
        self.sampleMaterialSelection.setEditable(True)
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
        self.sampleNameSelection.setPlaceholderText("select sample name")

        # sample color
        self.sampleColorInfoLabel = QLabel()
        self.sampleColorInfoLabel.setText("Sample color:")

        self.sampleColorSelection = QComboBox()
        self.sampleColorSelection.setDuplicatesEnabled(False)
        self.sampleColorSelection.setEditable(True)
        self.sampleColorSelection.addItem("")
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

    def keyPressEvent(self, e: QKeyEvent) -> None:
        # if e.key() == Qt.Key.Key_Escape or e.key() == Qt.Key.Key_Q:
        if e.key() == Qt.Key.Key_Q:
            self.close()

        elif e.key() == Qt.Key.Key_Up or e.key() == Qt.Key.Key_W or e.key() == Qt.Key.Key_Plus:
            self.scatter2d._viewBox.scaleBy((1, 0.9))

        elif e.key() == Qt.Key.Key_Down or e.key() == Qt.Key.Key_S or e.key() == Qt.Key.Key_Minus:
            self.scatter2d._viewBox.scaleBy((1, 1.1))

        elif e.key() == Qt.Key.Key_Home:
            # TODO fix this
            self.scatter2d._plotWidget.setXRange(
                settings.HARDWARE.WAVELENGTHS[0],
                settings.HARDWARE.WAVELENGTHS[-1],
                padding=0.1,
            )
            self.scatter2d._plotWidget.setYRange(self.yMin, self.yMax, padding=self.yPadding)

        elif e.key() == Qt.Key.Key_Space:
            self.regular_measurement()

        elif e.key() == Qt.Key.Key_F11:
            if not self.fullscreen:
                self.windowHandle().showFullScreen()
                self.fullscreen = True
            else:
                self.windowHandle().showNormal()
                self.fullscreen = False

    def center(self) -> None:
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
            self.serial = serial.Serial(port, baudrate=settings.HARDWARE.BAUDRATE, timeout=1)
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

    def regular_measurement(self) -> None:
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

        data = self.get_measurement()
        self.add_measurement(data)
        self.scatter2d.plot(snv_transform(data))
        self.scatter3d.plot()
        self.histogram.plot()

    def get_measurement(self) -> list[float]:
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

    def add_measurement(self, data: list[float]) -> None:
        # get the material from the ComboBox
        material = self.sampleMaterialSelection.currentText().rstrip()
        if material not in self.sample_materials:
            self.sample_materials.append(material)
            self.sampleMaterialSelection.addItem(material)

        # get the name from the ComboBox
        name = self.sampleNameSelection.currentText().rstrip()
        if name not in self.sample_names:
            self.sample_names.add(name)
            self.sampleNameSelection.addItem(name)

        # get the color from the ComboBox
        color = self.sampleColorSelection.currentText().rstrip()
        if color not in self.sample_colors:
            self.sample_colors.add(color)
            self.sampleColorSelection.addItem(color)

        self.store_measurement(data, name=name, material=material, color=color)

    def store_measurement(
        self,
        data: list[float],
        name: str = "",
        material: str = "unknown",
        color: str = "",
        calibrated_measurement: bool = False,
    ) -> None:
        """adds newest measurement to table and dataframe"""

        data_snv = snv_transform(data)

        if calibrated_measurement:
            data_normalized = [1] * len(data)
        else:
            if self.baseline is not None:
                data_normalized = normalize(data, self.baseline)
            else:
                data_normalized = [None] * len(data)

        self.currently_storing = True
        self.store_to_dataframe(
            data,
            data_snv,
            data_normalized,
            name,
            material,
            color,
            calibrated_measurement,
        )
        self.table.append(
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

    def store_to_dataframe(
        self,
        data: list[float],
        data_snv: list[float],
        data_normalized: list[float | None],
        name: str = "",
        material: str = "unknown",
        color: str = "",
        calibrated_measurement: bool = False,
    ) -> None:
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

    def _update_df_after_table_change(self, column, row, value):
        self.df.loc[row, column] = value

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

            self.baseline = self.get_measurement()
            self.current_calibration_counter += 1
            self.total_calibration_counter += 1
            self.store_measurement(self.baseline, calibrated_measurement=True)

            # after a calibration calibration the plot is cleared
            self.scatter2d.plot()

    def clear_calibration(self) -> None:
        self.baseline = None
        # after a calibration calibration the plot is cleared
        self.twoDPlottedList.clear()
        self.scatter2d.clear()

    def load_dataset_online(self) -> None:
        QMessageBox.information(
            self,
            "loading dataset",
            f"Dataset is loaded from url:\n{settings.DATAFRAME.DATASET_URL}",
        )
        self.load_dataset(settings.DATAFRAME.DATASET_URL)

    def load_dataset_local(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Load dataset",
            "",
            "CSV (*.csv);;All Files (*)",
        )
        if not filename:
            QMessageBox.information(self, "loading dataset", "No file was selected")
        else:
            self.load_dataset(filename)

    def _load_dataset_warning(self) -> bool:
        """returns true if user is sure"""
        button = QMessageBox.warning(
            self,
            "Load dataset",
            "You are about to overwrite the data that is displayed by the table."
            + "\nAre you sure you want to overwrite?",
            QMessageBox.Yes,
            QMessageBox.No,
        )
        return button == QMessageBox.Yes

    def _load_dataset_warning_really(self) -> bool:
        button = QMessageBox.warning(
            self,
            "Load dataset",
            "Are you really sure?",
            QMessageBox.Yes,
            QMessageBox.No,
        )
        return button == QMessageBox.Yes

    def load_dataset(self, dataset_path: str) -> None:
        """load a dataset to continue where that dataset last left off"""
        # give warnings that there is data and it will get overwritten
        if len(self.df) > 0:
            if not (self._load_dataset_warning() and self._load_dataset_warning_really()):
                return

        new_df = pd.read_csv(dataset_path, index_col="Reading", dtype=settings.DATAFRAME.HEADER)
        if list(new_df.columns) != settings.DATAFRAME.HEADER:
            QMessageBox.critical(
                self,
                "Load dataset",
                "Dataset could not be loaded because of unexpected columns\n\n"
                + f"columns of new dataset:\n {new_df.columns}\n\n"
                + f"expected columns for a dataset:\n {settings.DATAFRAME.HEADER}\n\n"
                + "COULD NOT LOAD NEW DATASET!\n\n"
                + "For help, please contact the PlasticScanner Team",
            )
            return

        self.df = new_df

        # clear plots
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
                row[settings.SCATTER3D.AXIS_OPTIONS]
            )

        # clear 2d plot and histogram
        self.scatter2d.clear()
        self.histogram.clear()

        # reset variables
        # reset calibration counter
        self.sample_names = set(self.df["Name"])
        self.sample_colors = set(self.df["Color"])
        self.sample_materials = self.DEFAULT_SAMPLE_MATERIALS.copy()
        self.sample_materials.extend(list(set(self.df["PlasticType"]) - set(self.sample_materials)))
        self.current_calibration_counter = 0
        self.total_calibration_counter = 0
        self.clear_calibration()

        # clear table
        self.table.clear()
        # build table
        for _idx, row in self.df.iterrows():
            name = row["Name"] if isinstance(row["Name"], str) else ""
            plasticType = row["PlasticType"] if isinstance(row["PlasticType"], str) else ""
            color = row["Color"] if isinstance(row["Color"], str) else ""
            if row["MeasurementType"] == "calibration":
                self.total_calibration_counter += 1
                self.table.append(
                    row[settings.TABLE.DATAFRAME_SUBSET_HEADERS],
                    name=name,
                    material=plasticType,
                    color=color,
                    calibrated_measurement=True,
                )
            else:
                self.table.append(
                    row[settings.TABLE.DATAFRAME_SUBSET_HEADERS],
                    name=name,
                    material=plasticType,
                    color=color,
                    calibrated_measurement=False,
                )

        self.scatter2d.plot()
        self.scatter3d.plot()

    def export_to_csv(self) -> None:
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


def main():
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

    window = PsPlot()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
