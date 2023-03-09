#!/usr/bin/env python

from PyQt5.QtCore import Qt, pyqtSignal, QT_VERSION_STR
from PyQt5.QtGui import (
    QColor,
    QIcon,
    QKeyEvent,
    QVector3D,
)
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtDataVisualization import (
    Q3DCamera,
    Q3DScatter,
    Q3DTheme,
    QAbstract3DGraph,
    QScatter3DSeries,
    QScatterDataItem,
    QScatterDataProxy,
)
from collections import deque
from datetime import datetime
from numpy.typing import ArrayLike
from typing import List, Optional, Tuple, Dict, Union
import joblib
import numpy as np
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


def normalize(
    input_data: List[float],
    calibration_data: Union[List[float], ArrayLike],
) -> List[float]:
    """normalizes by dividing by `calibration_data` and also applies SNV_transform"""
    input_data = np.asarray(input_data)
    calibration_data = np.asarray(calibration_data)

    # scale by calibration measurement
    data_rescaled = input_data / calibration_data

    data_snv = SNV_transform(data_rescaled)

    return list(data_snv)


def SNV_transform(data: Union[ArrayLike, List[float]]) -> List[float]:
    # the following is an SNV tranform
    # Subtract the mean and divide by the standarddiviation
    return list((np.asarray(data) - np.mean(data)) / np.std(data))


def list_to_string(data: List[float]) -> str:
    return " ".join([f"{i:.7f}" for i in data])


class PsPlot(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowIcon(QIcon("logo3-01.png"))

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
        ]  # in nanometers
        self.baudrate = 9600
        self.dataset_url = "https://raw.githubusercontent.com/Plastic-Scanner/data/main/data/20230117_DB2.1_second_dataset/measurement.csv"
        # labels used in the trainingset
        self.trained_labels = [
            "PP",
            "PET",
            "PS",
            "HDPE",
            "LDPE",
            "PVC",
        ]

        self.serial = None
        self.datasetloaded = None

        # the names of the columns of the table
        self.table_header = ["name", "material", "color"] + [
            str(x) for x in self.wavelengths
        ]
        # the measurement columns of the dataframe that are represented in the table
        self.table_used_dataframe_headers = [f"nm{x}" for x in self.wavelengths]

        # the headers for the dataframe:
        # |  Reading                |   the how many'th measurement                   |
        # |  Name                   |   name or id of the piece                       |
        # |  PlasticType            |   type of the plastic                           |
        # |  Color                  |   physical color of the piece of plastic        |
        # |  MeasurementType        |   if the measurement was a calibration or not   | options: regular, calibration
        # |  nm<wavelengths>        |   measured signal per wavelength                |
        # |  nm<wavelengths>_norm   |   signal per wavelength after normalization     |
        self.df_header = (
            [
                "Name",
                "PlasticType",
                "Color",
                "MeasurementType",
                "DateTime",
            ]
            + [f"nm{x}" for x in self.wavelengths]
            + [f"nm{x}_snv" for x in self.wavelengths]
            + [f"nm{x}_norm" for x in self.wavelengths]
        )
        self.df_header_dtypes = (
            {
                "Name": str,
                "PlasticType": str,
                "Color": str,
                "MeasurementType": str,
                "DateTime": str,
            }
            | {f"nm{x}": float for x in self.wavelengths}
            | {f"nm{x}_snv": float for x in self.wavelengths}
            | {f"nm{x}_norm": float for x in self.wavelengths}
        )
        self.df = pd.DataFrame(columns=self.df_header)

        self.prediction_options = [f"nm{x}" for x in self.wavelengths]
        self.clf = joblib.load("model.joblib")

        self.threeDAxisOptions = (
            [f"nm{x}" for x in self.wavelengths]
            + [f"nm{x}_snv" for x in self.wavelengths]
            + [f"nm{x}_norm" for x in self.wavelengths]
        )
        self.threeDAxisOptionsIndexMap = {
            name: index for index, name in enumerate(self.threeDAxisOptions)
        }
        self.threeDAxisVarXDefault = "nm1050_norm"
        self.threeDAxisVarYDefualt = "nm1450_norm"
        self.threeDAxisVarZDefault = "nm1650_norm"
        self.threeDAxisVarX = self.threeDAxisVarXDefault
        self.threeDAxisVarY = self.threeDAxisVarYDefualt
        self.threeDAxisVarZ = self.threeDAxisVarZDefault

        # keeps track of all of the samples that have been measured
        self.default_sample_materials = [
            "PP",
            "PET",
            "PS",
            "HDPE",
            "LDPE",
            "PVC",
            "spectralon",
            "unknown",
        ]
        self.sample_materials = self.default_sample_materials.copy()

        # holds the calibration measurement
        self.baseline = None

        self.sample_colors = {""}
        self.sample_names = {""}

        self.overwrite_no_callibration_warning = False
        self.fullscreen = False
        # true when self.storeMeasurement is active
        self.currently_storing = False
        # true when self.plotTwoD is active
        self.currently_plotting = False

        # used for also plotting previouse values
        self.twoDPlotHistoryDeque = deque(maxlen=3)
        # all the values that were last plotted
        self.twoDPlottedList = []
        # to keep track of the amount of calibrations done in the current session
        self.current_calibration_counter = 0
        # the amount of calibrations done in the current session + the previouse sessions
        self.total_calibration_counter = 0
        # holds labels for each row of the table, calibration rows are labeled differently
        self.tableRowLabels = []
        # colorblind friendly colors taken and adjusted from https://projects.susielu.com/viz-palette
        # ["#ffd700", "#ffb14e", "#fa8775", "#ea5f94", "#cd34b5", "#9d02d7", "#0000ff", "#2194F9"]
        self.color_tableau = (
            QColor(255, 215, 0),
            QColor(255, 177, 78),
            QColor(250, 135, 117),
            QColor(234, 95, 148),
            QColor(205, 52, 181),
            QColor(157, 2, 215),
            QColor(33, 148, 249),
            QColor(0, 0, 255),
        )
        self.threeDPlotAllowedMaterials = [
            "PP",
            "PET",
            "PS",
            "HDPE",
            "LDPE",
            "PVC",
            "other",
            "unknown",
        ]
        self.threeDPlotColormap = {
            x: y
            for x, y in zip(
                self.threeDPlotAllowedMaterials,
                self.color_tableau,
            )
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
        self.table = Table()
        self.table.setColumnCount(len(self.table_header))
        self.table.setHorizontalHeaderLabels(self.table_header)
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
        self.serialConnect()

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

    def _setupTwoDPlotUI(self):
        """sets up both the twoDPlotWidget, and its layout"""
        self.twoDPlotWidget = pg.PlotWidget(background=None)

        self.twoDPlotItem = self.twoDPlotWidget.getPlotItem()
        self.twoDPlotViewbox = self.twoDPlotItem.getViewBox()
        self.twoDPlotItem.hideButtons()
        self.twoDPlotItem.setMenuEnabled(True)
        self.twoDPlotItem.showGrid(x=True, y=True, alpha=0.5)
        self.twoDPlotItem.setMouseEnabled(x=False, y=True)

        self.pc = self.twoDPlotWidget.plot()
        self.pc.setSymbol("o")

        self.xPadding = min(self.wavelengths) * 0.1
        self.yPadding = 0
        self.yMin = 0
        self.yMax = 1.1
        self.twoDPlotItem.setLimits(
            xMin=min(self.wavelengths) - self.xPadding,
            xMax=max(self.wavelengths) + self.xPadding,
            # yMin=0 - self.yPadding,
        )
        # self.twoDPlotItem.setLabel("left", "NIR output", units="V", unitPrefix="m")
        self.twoDPlotItem.setLabel("left", "normalized NIR output")
        self.twoDPlotItem.setLabel("bottom", "Wavelength (nm)")
        self.twoDPlotItem.getAxis("bottom").enableAutoSIPrefix(False)
        self.twoDPlotItem.setTitle("Reflectance")

        self.twoDPlotWidget.setXRange(
            self.wavelengths[0], self.wavelengths[-1], padding=0.1
        )
        # self.twoDPlotWidget.setYRange(self.yMin, self.yMax, padding=self.yPadding)

        # Buttons for 2d plot
        self.twoDAxisAutoRangeChbx = QCheckBox("Auto range")
        self.twoDAxisAutoRangeChbx.clicked.connect(self.twoDPlotAutoRangeChbxClick)
        self.twoDAxisAutoRangeChbx.setChecked(True)
        self.twoDPlotViewbox.sigRangeChanged.connect(self.twoDPlotRangeChanged)

        self.twoDClearPlotBtn = QPushButton("Clear graph")
        self.twoDClearPlotBtn.clicked.connect(self.twoDPlotClear)

        self.twoDExportPlotBtn = QPushButton("Export graph")
        self.twoDExportPlotBtn.clicked.connect(self.twoDPlotExport)

        self.twoDPlotControlLayout = QHBoxLayout()
        self.twoDPlotControlLayout.addWidget(self.twoDAxisAutoRangeChbx)
        self.twoDPlotControlLayout.addWidget(self.twoDClearPlotBtn)
        self.twoDPlotControlLayout.addWidget(self.twoDExportPlotBtn)
        self.twoDPlotControlLayout.setSpacing(0)

        self.twoDPlotLayout = QVBoxLayout()
        self.twoDPlotLayout.addWidget(self.twoDPlotWidget, 80)
        self.twoDPlotLayout.addLayout(self.twoDPlotControlLayout, 20)

    def _setupThreeDPlotUI(self):
        # hierarchical datastructure that is used to speed up plotting
        # uses key material = other when material is known and not in threeDPlotAllowedLabels
        # uses key material = unknown when material field is ""
        # {
        #     material: {
        #         id/name: {
        #             "data": [data1, data2],
        #             "proxy": proxy,
        #             "series": series,
        #         }
        #     }
        # }
        self.threeDUniqueSeries = {
            material: {} for material in self.threeDPlotAllowedMaterials
        }

        self.threeDdata: Dict[Tuple[int], list[QScatterDataItem]] = dict()
        self.threeDdata_colors = []
        self.threeDgraph = Q3DScatter()
        self.threeDPlotWidget = QWidget.createWindowContainer(self.threeDgraph)

        self.threeDgraph.setOrthoProjection(True)
        self.threeDgraph.scene().activeCamera().setCameraPreset(
            Q3DCamera.CameraPresetIsometricLeft
        )
        self.threeDgraph.axisX().setTitle(self.threeDAxisVarXDefault)
        self.threeDgraph.axisX().setTitleVisible(True)
        self.threeDgraph.axisX().setLabelFormat("%.4f")
        self.threeDgraph.axisY().setTitle(self.threeDAxisVarYDefualt)
        self.threeDgraph.axisY().setTitleVisible(True)
        self.threeDgraph.axisY().setLabelFormat("%.4f")
        self.threeDgraph.axisZ().setTitle(self.threeDAxisVarZDefault)
        self.threeDgraph.axisZ().setTitleVisible(True)
        self.threeDgraph.axisZ().setLabelFormat("%.4f")

        # styling
        self.threeDgraph.setShadowQuality(QAbstract3DGraph.ShadowQuality(0))

        currentTheme = self.threeDgraph.activeTheme()
        currentTheme.setType(Q3DTheme.Theme(0))
        currentTheme.setBackgroundEnabled(False)
        currentTheme.setLabelBackgroundEnabled(False)
        currentTheme.setLabelTextColor(QColor(self.palette().text().color()))
        currentTheme.setAmbientLightStrength(1)
        currentTheme.setLightStrength(1)
        currentTheme.setHighlightLightStrength(1)
        currentTheme.setColorStyle(Q3DTheme.ColorStyleUniform)
        currentTheme.setGridEnabled(True)
        back = QColor(self.palette().window().color())
        currentTheme.setBackgroundColor(back)
        currentTheme.setWindowColor(back)
        fontsize = currentTheme.font().pointSizeF()
        font = currentTheme.font()
        font.setPointSizeF(4 * fontsize)
        currentTheme.setFont(font)

        ## legend
        self.threeDPlotLegendLayout = QHBoxLayout()
        back = self.palette().window().color().getRgb()
        self.threeDPlotLegendButtons = {}
        for name, color in self.threeDPlotColormap.items():
            label = QLabel()
            button = QPushButton(name)
            button.setCheckable(True)
            button.setChecked(True)
            button.clicked.connect(self.plotThreeD)
            rgb = color.getRgb()
            button.setStyleSheet(
                """
                QPushButton:checked{
                        color: black;
                        background-color:
                """
                + f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]});"
                + """
                        }

                QPushButton:pressed{
                        color: black;
                        background-color:
                """
                + f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]});"
                + """
                        }
                """
            )

            label.setText(name)
            label.setStyleSheet(
                "QLabel { background-color : "
                + f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]});"
                + " color : black; }"
            )
            # self.threeDPlotLegendLayout.addWidget(label)
            self.threeDPlotLegendLayout.addWidget(button)
            self.threeDPlotLegendButtons[name] = button

        ## buttons
        self.threeDAxXSelection = QComboBox()
        self.threeDAxXSelection.addItems(self.threeDAxisOptions)
        self.threeDAxXSelection.setCurrentText(self.threeDAxisVarXDefault)
        self.threeDAxXSelection.currentTextChanged.connect(self.threeDAxXChanged)
        self.threeDAxYSelection = QComboBox()
        self.threeDAxYSelection.addItems(self.threeDAxisOptions)
        self.threeDAxYSelection.setCurrentText(self.threeDAxisVarYDefualt)
        self.threeDAxYSelection.currentTextChanged.connect(self.threeDAxYChanged)
        self.threeDAxZSelection = QComboBox()
        self.threeDAxZSelection.addItems(self.threeDAxisOptions)
        self.threeDAxZSelection.setCurrentText(self.threeDAxisVarZDefault)
        self.threeDAxZSelection.currentTextChanged.connect(self.threeDAxZChanged)

        self.threeDDefaultAxesBtn = QPushButton("Default axes")
        self.threeDDefaultAxesBtn.clicked.connect(self.threeDDefaultAxes)
        self.threeDClearPlotBtn = QPushButton("Clear graph")
        self.threeDClearPlotBtn.clicked.connect(self.threeDPlotClear)
        self.threeDExportPlotBtn = QPushButton("Export graph")
        # self.threeDExportPlotBtn.clicked.connect()

        self.threeDPlotControlLayout = QGridLayout()
        self.threeDPlotControlLayout.addWidget(self.threeDAxXSelection, 0, 0)
        self.threeDPlotControlLayout.addWidget(self.threeDAxYSelection, 0, 1)
        self.threeDPlotControlLayout.addWidget(self.threeDAxZSelection, 0, 2)
        self.threeDPlotControlLayout.addWidget(self.threeDDefaultAxesBtn, 1, 0)
        self.threeDPlotControlLayout.addWidget(self.threeDClearPlotBtn, 1, 1)
        self.threeDPlotControlLayout.addWidget(self.threeDExportPlotBtn, 1, 2)
        self.threeDPlotControlLayout.setSpacing(0)

        self.threeDPlotLayout = QVBoxLayout()
        self.threeDPlotLayout.addWidget(self.threeDPlotWidget, 80)
        self.threeDPlotLayout.addLayout(self.threeDPlotLegendLayout, 2)
        self.threeDPlotLayout.addLayout(self.threeDPlotControlLayout, 20)
        self.threeDPlotLayout.setSpacing(0)

    def _setupHistogramUI(self):
        self.histogramPlotWidget = pg.PlotWidget(background=None)
        # self.histogramPlotItem = self.twoDPlotWidget.getPlotItem()
        self.histogramPlotWidget.hideButtons()
        self.histogramPlotWidget.setMenuEnabled(True)
        self.histogramPlotWidget.setMouseEnabled(x=False, y=False)
        self.histogramPlotWidget.setLimits(
            xMin=0,
            xMax=100,
            yMin=0,
        )
        self.histogramPlotWidget.setXRange(0, 100)

        # the labels for the vertical axis, they are flipped because
        # humans read from top to bottom
        vertical_axis = {
            idx: name for idx, name in enumerate(self.clf.classes_[::-1], start=1)
        }

        axis = self.histogramPlotWidget.getAxis("left")
        axis.setTicks([vertical_axis.items()])
        axis.setStyle(tickLength=0)

        axis = self.histogramPlotWidget.getAxis("bottom")
        axis.setTicks([{x: str(x) for x in range(0, 120, 20)}.items()])

        self.plotHistogram(initialize=True)

        self.histogramSortBtnGroup = QButtonGroup()
        self.histogramSortDefaultBtn = QRadioButton("sort default")
        self.histogramSortDefaultBtn.setChecked(True)
        self.histogramSortBtnGroup.addButton(self.histogramSortDefaultBtn)
        self.histogramSortCertaintyBtn = QRadioButton("sort score")
        self.histogramSortBtnGroup.addButton(self.histogramSortCertaintyBtn)

        self.histogramClearPlotBtn = QPushButton("Clear graph")
        # self.threeDClearPlotBtn.clicked.connect()
        self.histogramExportPlotBtn = QPushButton("Export graph")
        # self.threeDExportPlotBtn.clicked.connect()

        self.histogramPlotControlLayout = QGridLayout()
        self.histogramPlotControlLayout.addWidget(self.histogramSortDefaultBtn, 0, 0)
        self.histogramPlotControlLayout.addWidget(self.histogramSortCertaintyBtn, 0, 1)
        self.histogramPlotControlLayout.addWidget(self.histogramClearPlotBtn, 1, 0)
        self.histogramPlotControlLayout.addWidget(self.histogramExportPlotBtn, 1, 1)
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

    def serialConnect(self) -> None:
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
        except Exception:
            print(f"Can't open serial port '{port}', using dummy data")
            self.serial = None
            self.serialNotif.setText("Using dummy data")

    def center(self) -> None:
        """centers the application to the center of the screen"""
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def twoDPlotAutoRangeChbxClick(self) -> None:
        self.twoDPlotWidget.setFocus()
        self.twoDPlotViewbox.enableAutoRange(
            self.twoDPlotViewbox.YAxis,
            enable=self.twoDAxisAutoRangeChbx.isChecked(),
        )

    def twoDPlotRangeChanged(self):
        # if the user moves the range of the plot, then turn off the checkbox
        # if the range changed because of automatic rescaling that happened
        # during plotting then do nothing
        if not self.currently_plotting:
            self.twoDAxisAutoRangeChbx.setChecked(False)

    def twoDPlotClear(self) -> None:
        self.twoDPlotHistoryDeque.clear()
        self.twoDPlottedList.clear()
        self.twoDPlotWidget.clear()
        self.plotTwoD()
        # self.twoDAxisAutoRangeChbx.setChecked(True)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        # if e.key() == Qt.Key.Key_Escape or e.key() == Qt.Key.Key_Q:
        if e.key() == Qt.Key.Key_Q:
            self.close()

        elif (
            e.key() == Qt.Key.Key_Up
            or e.key() == Qt.Key.Key_W
            or e.key() == Qt.Key.Key_Plus
        ):
            self.twoDPlotViewbox.scaleBy((1, 0.9))

        elif (
            e.key() == Qt.Key.Key_Down
            or e.key() == Qt.Key.Key_S
            or e.key() == Qt.Key.Key_Minus
        ):
            self.twoDPlotViewbox.scaleBy((1, 1.1))

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
            self.current_calibration_counter == 0
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
        self.plotTwoD(SNV_transform(data))
        self.plotThreeD()
        self.plotHistogram()
        # self.plotThreeD([data[1], data[4], data[6]])

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
            if self.baseline != None:
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
            if material not in self.threeDUniqueSeries:
                self.threeDUniqueSeries[material] = {}
            if name not in self.threeDUniqueSeries[material]:
                self.threeDUniqueSeries[material][name] = {"data": []}

            self.threeDUniqueSeries[material][name]["data"].append(
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
            cell.setFlags(
                cell.flags() & ~Qt.ItemFlag.ItemIsEditable
            )  # disable editing of cells

            # use a different color if the measurement was taken for calibration
            self.table.setItem(nRows, col, cell)

        if calibrated_measurement:
            for column in range(self.table.columnCount()):
                self.table.item(nRows, column).setBackground(
                    self.palette().alternateBase().color()
                )

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
            self.twoDPlotHistoryDeque.clear()
            self.plotTwoD()

    def clearCalibration(self) -> None:
        self.baseline = None
        # after a calibration calibration the plot is cleared
        self.twoDPlotHistoryDeque.clear()
        self.twoDPlottedList.clear()
        self.twoDPlotWidget.clear()

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
                self.sampleMaterialLayoutSelection.addItem(name)

        # also update the change in the dataframe
        if not self.currently_storing:
            column = item.column()
            # the header of the dataframe contains the `DateTime` header which is not
            # present in the table, and has te be compensated for
            if column >= 4:
                column -= 1
            self.df.loc[item.row(), self.df_header[column]] = item.text()

    def plotTwoD(self, data: Optional[List[float]] = None) -> None:
        self.currently_plotting = True
        self.twoDPlotWidget.clear()

        # add the baseline of the last calibration
        if self.baseline is not None:
            normalized_baseline = [1] * len(self.baseline)
            pc = self.twoDPlotWidget.plot(
                self.wavelengths, normalized_baseline, pen=(255, 0, 0)
            )
            self.twoDPlottedList.append(normalized_baseline)

        for dat in self.twoDPlotHistoryDeque:
            if self.baseline is not None:
                dat = normalize(dat, self.baseline)
            self.twoDPlottedList.append(dat)
            pc = self.twoDPlotWidget.plot(
                self.wavelengths,
                dat,
                pen=(0, 100, 0),
                symbolBrush=(0, 255, 0),
            )
            pc.setSymbol("x")
        if data != None:
            self.twoDPlotHistoryDeque.append(data)

        # TODO make this shorter (look how I did this elsewhere)
        line_color = tuple(self.palette().text().color().getRgb())
        mark_color = tuple(self.palette().highlight().color().getRgb())

        pen = pg.mkPen(color=line_color, symbolBrush=mark_color, symbolPen="o", width=2)
        if data is not None:
            if self.baseline is not None:
                data = normalize(data, self.baseline)
            pc = self.twoDPlotWidget.plot(self.wavelengths, data, pen=pen)
            pc.setSymbol("o")

        self.currently_plotting = False

    def plotHistogram(self, initialize=False) -> None:
        if initialize:
            yticks = list(range(1, len(self.clf.classes_) + 1))
            widths = [0] * len(self.clf.classes_)
        else:
            data = self.df.loc[len(self.df) - 1, self.prediction_options]
            data = pd.DataFrame([data], columns=self.prediction_options)
            prediction = {
                plastic: self.clf.predict_proba(data)[0][idx] * 100
                for idx, plastic in enumerate(self.clf.classes_)
            }
            yticks = list(range(1, len(prediction) + 1))
            # the order of the predicted values is flipped here because the labels are also flipped
            widths = [int(x) for x in list(prediction.values())[::-1]]

            # if ever uncertain about the order of the predictions, use this:
            # for idx, material in enumerate(self.clf.classes_):
            #     print(f"{material}: {self.clf.predict_proba(data)[0][idx] * 100}%")

        self.histogramPlotWidget.clear()
        self.histogramPlotWidget.setYRange(0, len(self.clf.classes_) + 0.5)
        self.bars = pg.BarGraphItem(
            x0=0,
            y=yticks,
            height=0.8,
            width=widths,
        )
        self.bars.setOpts(brush=QColor(self.palette().highlight().color()))
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

        new_df = pd.read_csv(
            dataset_path, index_col="Reading", dtype=self.df_header_dtypes
        )
        if list(new_df.columns) != self.df_header:
            QMessageBox.critical(
                self,
                "Load dataset",
                "Dataset could not be loaded because of unexpected columns\n\n"
                + f"columns of new dataset:\n {new_df.columns}\n\n"
                + f"expected columns for a dataset:\n {self.df_header}\n\n"
                + f"COULD NOT LOAD NEW DATASET!\n\n"
                + "For help, please contact the PlasticScanner Team",
            )
            return

        self.df = new_df

        ## clear plots
        # clear 3d plot
        self.threeDPlotClear()
        # build the datastructure needed for 3dplot
        self.threeDUniqueSeries = {
            material: {} for material in self.df["PlasticType"].unique()
        }
        for _, row in self.df.iterrows():
            name = row["Name"]
            material = row["PlasticType"]
            if name not in self.threeDUniqueSeries[material]:
                self.threeDUniqueSeries[material][name] = {"data": []}
            self.threeDUniqueSeries[material][name]["data"].append(
                row[self.threeDAxisOptions]
            )

        # clear 2d plot and histogram
        self.twoDPlotClear()
        self.plotHistogram(initialize=True)

        ## reset variables
        # reset calibration counter
        self.sample_names = set(self.df["Name"])
        self.sample_colors = set(self.df["Color"])
        self.sample_materials = self.default_sample_materials.copy()
        self.sample_materials.extend(
            list(set(self.df["PlasticType"]) - set(self.sample_materials))
        )
        self.current_calibration_counter = 0
        self.total_calibration_counter = 0
        self.clearCalibration()

        ## write dataframe to table
        # clear table an variable
        self.table.clearContents()
        self.table.setRowCount(0)
        self.tableRowLabels = []
        # build table
        calibration_counter = 0
        for idx, row in self.df.iterrows():
            name = row["Name"] if isinstance(row["Name"], str) else ""
            plasticType = (
                row["PlasticType"] if isinstance(row["PlasticType"], str) else ""
            )
            color = row["Color"] if isinstance(row["Color"], str) else ""
            if row["MeasurementType"] == "calibration":
                self.total_calibration_counter += 1
                self.addToTable(
                    row[self.table_used_dataframe_headers],
                    name=name,
                    material=plasticType,
                    color=color,
                    calibrated_measurement=True,
                )
            else:
                self.addToTable(
                    row[self.table_used_dataframe_headers],
                    name=name,
                    material=plasticType,
                    color=color,
                    calibrated_measurement=False,
                )

        self.plotTwoD()
        self.plotThreeD()

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

    def twoDPlotExport(self):
        # TODO
        ...
        #     fname, _ = QFileDialog.getSaveFileName(
        #         self,
        #         "Save File",
        #         "",
        #         "CSV (*.csv);;All Files (*)",
        #     )
        #     if not fname:
        #         QMessageBox.information(self, "saving dataset", "No file was selected")
        #     else:
        #         self.twoDPlotWidget.export(fname)
        # print("hammer time")

    def plotThreeD(self, axis_changed: bool = False) -> None:
        """axis_changed: true if the variable of one of the axes was changed by the user"""
        indexX = self.threeDAxisOptionsIndexMap[self.threeDAxisVarX]
        indexY = self.threeDAxisOptionsIndexMap[self.threeDAxisVarY]
        indexZ = self.threeDAxisOptionsIndexMap[self.threeDAxisVarZ]
        for material in self.threeDUniqueSeries:
            if material not in self.threeDPlotAllowedMaterials:
                if material == "":
                    material_name = "unknown"
                else:
                    material_name = "other"
            else:
                material_name = material

            color = self.threeDPlotColormap[material_name]
            for id in self.threeDUniqueSeries[material]:
                if "proxy" not in self.threeDUniqueSeries[material][id]:
                    proxy = QScatterDataProxy()
                    series = QScatter3DSeries(proxy)

                    name = f"{id} | {material}"
                    series.setName(name)
                    # alternatively: "@xLabel | @yLabel | @zLabel | @seriesName"
                    series.setItemLabelFormat("@seriesName")
                    series.setMeshSmooth(True)
                    series.setBaseColor(color)
                    series.setColorStyle(Q3DTheme.ColorStyleUniform)

                    self.threeDUniqueSeries[material][id]["proxy"] = proxy
                    self.threeDUniqueSeries[material][id]["series"] = series
                    self.threeDgraph.addSeries(series)
                else:
                    proxy = self.threeDUniqueSeries[material][id]["proxy"]
                    series = self.threeDUniqueSeries[material][id]["series"]

                if self.threeDPlotLegendButtons[material_name].isChecked():
                    if (
                        len(self.threeDUniqueSeries[material][id]["data"])
                        > len(proxy.array())
                        or axis_changed
                    ):
                        # if none of the datapoints are None
                        if not any(
                            [
                                data[indexX] == None
                                or data[indexY] == None
                                or data[indexZ] == None
                                for data in self.threeDUniqueSeries[material][id][
                                    "data"
                                ]
                            ]
                        ):
                            dataArray = [
                                QScatterDataItem(
                                    QVector3D(
                                        data[indexX],
                                        data[indexY],
                                        data[indexZ],
                                    )
                                )
                                for data in self.threeDUniqueSeries[material][id][
                                    "data"
                                ]
                            ]

                            proxy.resetArray(dataArray)
                        else:
                            for data in self.threeDUniqueSeries[material][id]["data"]:
                                if (
                                    data[indexX] == None
                                    or data[indexY] == None
                                    or data[indexZ] == None
                                ):
                                    print(
                                        "WARNING: trying to plot point on normalized axis while non normalized data is present!"
                                    )
                                    print(
                                        "\tSWITCHING TO DISPLAYING NON NORMALIZED DATA..."
                                    )
                                    self.threeDAxisVarX = (
                                        self.threeDAxisVarX.rstrip("_norm") + "_snv"
                                    )
                                    self.threeDAxisVarY = (
                                        self.threeDAxisVarY.rstrip("_norm") + "_snv"
                                    )
                                    self.threeDAxisVarZ = (
                                        self.threeDAxisVarZ.rstrip("_norm") + "_snv"
                                    )
                                    self.threeDAxXSelection.setCurrentText(
                                        self.threeDAxisVarX
                                    )
                                    self.threeDAxYSelection.setCurrentText(
                                        self.threeDAxisVarY
                                    )
                                    self.threeDAxZSelection.setCurrentText(
                                        self.threeDAxisVarZ
                                    )
                            self.plotThreeD(axis_changed=True)
                            return

                        if series not in self.threeDgraph.seriesList():
                            self.threeDgraph.addSeries(series)
                else:
                    self.threeDgraph.removeSeries(series)

    def threeDDefaultAxes(self):
        self.threeDAxXSelection.setCurrentText(self.threeDAxisVarXDefault)
        self.threeDAxYSelection.setCurrentText(self.threeDAxisVarYDefualt)
        self.threeDAxZSelection.setCurrentText(self.threeDAxisVarZDefault)

    def threeDAxXChanged(self, name):
        self.threeDAxisVarX = name
        self.plotThreeD(axis_changed=True)

    def threeDAxYChanged(self, name):
        self.threeDAxisVarY = name
        self.plotThreeD(axis_changed=True)

    def threeDAxZChanged(self, name):
        self.threeDAxisVarZ = name
        self.plotThreeD(axis_changed=True)

    def threeDPlotClear(self):
        for material in self.threeDUniqueSeries:
            for id in self.threeDUniqueSeries[material]:
                series = self.threeDUniqueSeries[material][id]["series"]
                self.threeDgraph.removeSeries(series)

        self.threeDUniqueSeries = {
            material: {} for material in self.threeDPlotAllowedMaterials
        }


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
    pg.setConfigOptions(antialias=True)  # , crashWarning=True)

    app.setStyle("Fusion")
    window = PsPlot()
    window.show()
    app.exec()
