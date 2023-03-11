from __future__ import annotations
from PyQt5.QtGui import (
    QColor,
    QVector3D,
)
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
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
from typing import List, Optional
from helper_functions import normalize
import pandas as pd

# pyqtgraph should always be imported after importing pyqt
import pyqtgraph as pg


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psplot import PsPlot


class WriteCoordinateError(Exception):
    pass


class ScatterPlot2D(QVBoxLayout):
    def __init__(self, parent: PsPlot):
        super().__init__()
        self._parent = parent
        self._changing_plot = False

        # used for also plotting previouse values
        self.plot_history = deque(maxlen=3)

        self._init_plot_widget()
        self._init_button_control()
        self.addWidget(self._plotWidget, 80)
        self.addLayout(self._controlLayout, 20)

    def _init_plot_widget(self):
        self._plotWidget = pg.PlotWidget(background=None)
        self._plotItem = self._plotWidget.getPlotItem()
        self._viewBox = self._plotWidget.getViewBox()

        self._plotWidget.hideButtons()
        self._plotWidget.setMenuEnabled(True)
        self._plotWidget.showGrid(x=True, y=True, alpha=0.5)
        self._plotWidget.setMouseEnabled(x=False, y=True)

        pc = self._plotWidget.plot()
        pc.setSymbol("o")

        xPadding = min(self._parent.WAVELENGHTS) * 0.1
        self._plotItem.setLimits(
            xMin=min(self._parent.WAVELENGHTS) - xPadding,
            xMax=max(self._parent.WAVELENGHTS) + xPadding,
        )

        # self.twoDPlotItem.setLabel("left", "NIR output", units="V", unitPrefix="m")
        self._plotItem.setLabel("left", "normalized NIR output")
        self._plotItem.setLabel("bottom", "Wavelength (nm)")
        self._plotItem.getAxis("bottom").enableAutoSIPrefix(False)
        self._plotItem.setTitle("Reflectance")

        self._plotWidget.setXRange(
            self._parent.WAVELENGHTS[0], self._parent.WAVELENGHTS[-1], padding=0.1
        )

    def _init_button_control(self):
        self._autoRangeChbx = QCheckBox("Auto range")
        self._autoRangeChbx.clicked.connect(self._autoRangeChbxClick)
        self._autoRangeChbx.setChecked(True)
        self._viewBox.sigRangeChanged.connect(self._rangeChanged)

        self._clearPlotBtn = QPushButton("Clear graph")
        self._clearPlotBtn.clicked.connect(self.clear)

        self._exportPlotBtn = QPushButton("Export graph")
        self._exportPlotBtn.clicked.connect(self.export)

        self._controlLayout = QHBoxLayout()
        self._controlLayout.addWidget(self._autoRangeChbx)
        self._controlLayout.addWidget(self._clearPlotBtn)
        self._controlLayout.addWidget(self._exportPlotBtn)
        self._controlLayout.setSpacing(0)

    def _autoRangeChbxClick(self) -> None:
        self._changing_plot = True
        self._plotWidget.setFocus()
        # enable or disable autorange
        self._viewBox.enableAutoRange(
            self._viewBox.YAxis,
            enable=self._autoRangeChbx.isChecked(),
        )
        # run autorange once if applicable
        if self._autoRangeChbx.isChecked():
            self._viewBox.autoRange()
        self._changing_plot = False

    def _rangeChanged(self):
        # if the user moves the range of the plot, then turn off the checkbox
        # if the range changed because of automatic rescaling that happened
        # during plotting then do nothing
        if not self._changing_plot:
            self._autoRangeChbx.setChecked(False)

    @property
    def plotWidget(self):
        return self._plotWidget

    @plotWidget.setter
    def plotWidget(self, value):
        raise WriteCoordinateError("plotWidget is read-only")

    def clear(self):
        self._changing_plot = True
        self.plot_history.clear()
        self._parent.twoDPlottedList.clear()
        self._plotWidget.clear()
        self.plot()
        self._changing_plot = False

    def plot(self, data: Optional[List[float]] = None):
        self._changing_plot = True
        self._plotWidget.clear()

        # add the baseline of the last calibration
        if self._parent.baseline is not None:
            normalized_baseline = [1] * len(self._parent.baseline)
            pc = self._plotWidget.plot(
                self._parent.WAVELENGHTS, normalized_baseline, pen=(255, 0, 0)
            )
            self._parent.twoDPlottedList.append(normalized_baseline)

        for dat in self.plot_history:
            if self._parent.baseline is not None:
                dat = normalize(dat, self._parent.baseline)
            self._parent.twoDPlottedList.append(dat)
            pc = self._plotWidget.plot(
                self._parent.WAVELENGHTS,
                dat,
                pen=(0, 100, 0),
                symbolBrush=(0, 255, 0),
            )
            pc.setSymbol("x")
        if data is not None:
            self.plot_history.append(data)

        # TODO make this shorter (look how I did this elsewhere)
        line_color = tuple(self._parent.palette().text().color().getRgb())
        mark_color = tuple(self._parent.palette().highlight().color().getRgb())

        pen = pg.mkPen(color=line_color, symbolBrush=mark_color, symbolPen="o", width=2)
        if data is not None:
            if self._parent.baseline is not None:
                data = normalize(data, self._parent.baseline)
            pc = self._plotWidget.plot(self._parent.WAVELENGHTS, data, pen=pen)
            pc.setSymbol("o")

        self._changing_plot = False

    def export(self):
        return NotImplemented


class ScatterPlot3D(QVBoxLayout):
    def __init__(self, parent: PsPlot):
        super().__init__(parent)
        self._parent = parent

        self._init_variables()
        self._init_plot_widget()
        self._init_button_control()

        self.addWidget(self._plotWidget, 80)
        self.addLayout(self._legendLayout, 2)
        self.addLayout(self._controlLayout, 20)
        self.setSpacing(0)

    def _init_variables(self):
        self._axis_options_index_map = {
            name: index
            for index, name in enumerate(self._parent.SCATTER3D_AXIS_OPTIONS)
        }
        self._axis_var_x = self._parent.SCATTER3D_AXIS_VAR_X_DEFAULT
        self._axis_var_z = self._parent.SCATTER3D_AXIS_VAR_Y_DEFAULT
        self._axis_var_y = self._parent.SCATTER3D_AXIS_VAR_Z_DEFAULT

        # hierarchical datastructure that is used to speed up plotting
        # has 2 special keys that are not materials but represent groups
        # material = "other" when material is known and not
        #   in parent.SCATTER3D_ALLOWED_MATERIALS
        # material = "unknown" when material field is ""
        # {
        #     material: {
        #         id/name: {
        #             "data": [data1, data2, ...],
        #             "proxy": proxy,
        #             "series": series,
        #         }
        #     }
        # }
        self.unique_series = {
            material: {} for material in self._parent.SCATTER3D_ALLOWED_MATERIALS
        }

    def _init_plot_widget(self):
        self._graph = Q3DScatter()
        self._plotWidget = QWidget.createWindowContainer(self._graph)

        self._graph.setOrthoProjection(True)
        self._graph.scene().activeCamera().setCameraPreset(
            Q3DCamera.CameraPresetIsometricLeft
        )
        self._graph.axisX().setTitle(self._parent.SCATTER3D_AXIS_VAR_X_DEFAULT)
        self._graph.axisX().setTitleVisible(True)
        self._graph.axisX().setLabelFormat("%.4f")
        self._graph.axisY().setTitle(self._parent.SCATTER3D_AXIS_VAR_Y_DEFAULT)
        self._graph.axisY().setTitleVisible(True)
        self._graph.axisY().setLabelFormat("%.4f")
        self._graph.axisZ().setTitle(self._parent.SCATTER3D_AXIS_VAR_Z_DEFAULT)
        self._graph.axisZ().setTitleVisible(True)
        self._graph.axisZ().setLabelFormat("%.4f")

        # styling
        self._graph.setShadowQuality(QAbstract3DGraph.ShadowQuality(0))

        currentTheme = self._graph.activeTheme()
        currentTheme.setType(Q3DTheme.Theme(0))
        currentTheme.setBackgroundEnabled(False)
        currentTheme.setLabelBackgroundEnabled(False)
        currentTheme.setLabelTextColor(QColor(self._parent.palette().text().color()))
        currentTheme.setAmbientLightStrength(1)
        currentTheme.setLightStrength(1)
        currentTheme.setHighlightLightStrength(1)
        currentTheme.setColorStyle(Q3DTheme.ColorStyleUniform)
        currentTheme.setGridEnabled(True)
        back = QColor(self._parent.palette().window().color())
        currentTheme.setBackgroundColor(back)
        currentTheme.setWindowColor(back)
        fontsize = currentTheme.font().pointSizeF()
        font = currentTheme.font()
        font.setPointSizeF(4 * fontsize)
        currentTheme.setFont(font)

    def _init_button_control(self):
        ## legend
        self._legendLayout = QHBoxLayout()
        self._legend_buttons = {}
        for name, color in self._parent.SCATTER3D_COLOR_MAP.items():
            label = QLabel()
            button = QPushButton(name)
            button.setCheckable(True)
            button.setChecked(True)
            button.clicked.connect(self.plot)
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
            self._legendLayout.addWidget(button)
            self._legend_buttons[name] = button

        ## buttons
        self._axXSelection = QComboBox()
        self._axXSelection.addItems(self._parent.SCATTER3D_AXIS_OPTIONS)
        self._axXSelection.setCurrentText(self._parent.SCATTER3D_AXIS_VAR_X_DEFAULT)
        self._axXSelection.currentTextChanged.connect(self._ax_x_changed)
        self._axYSelection = QComboBox()
        self._axYSelection.addItems(self._parent.SCATTER3D_AXIS_OPTIONS)
        self._axYSelection.setCurrentText(self._parent.SCATTER3D_AXIS_VAR_Y_DEFAULT)
        self._axYSelection.currentTextChanged.connect(self._ax_y_changed)
        self._axZSelection = QComboBox()
        self._axZSelection.addItems(self._parent.SCATTER3D_AXIS_OPTIONS)
        self._axZSelection.setCurrentText(self._parent.SCATTER3D_AXIS_VAR_Z_DEFAULT)
        self._axZSelection.currentTextChanged.connect(self._ax_z_changed)

        self._defaultAxesBtn = QPushButton("Default axes")
        self._defaultAxesBtn.clicked.connect(self._default_axes)
        self._clearPlotBtn = QPushButton("Clear graph")
        self._clearPlotBtn.clicked.connect(self.clear)
        self._exportPlotBtn = QPushButton("Export graph")
        self._exportPlotBtn.clicked.connect(self.export)

        self._controlLayout = QGridLayout()
        self._controlLayout.addWidget(self._axXSelection, 0, 0)
        self._controlLayout.addWidget(self._axYSelection, 0, 1)
        self._controlLayout.addWidget(self._axZSelection, 0, 2)
        self._controlLayout.addWidget(self._defaultAxesBtn, 1, 0)
        self._controlLayout.addWidget(self._clearPlotBtn, 1, 1)
        self._controlLayout.addWidget(self._exportPlotBtn, 1, 2)
        self._controlLayout.setSpacing(0)

    def _default_axes(self):
        self._axXSelection.setCurrentText(self._parent.SCATTER3D_AXIS_VAR_X_DEFAULT)
        self._axYSelection.setCurrentText(self._parent.SCATTER3D_AXIS_VAR_Y_DEFAULT)
        self._axZSelection.setCurrentText(self._parent.SCATTER3D_AXIS_VAR_Z_DEFAULT)

    def _ax_x_changed(self, name):
        self._axis_var_x = name
        self.plot(axis_changed=True)

    def _ax_y_changed(self, name):
        self._axis_var_y = name
        self.plot(axis_changed=True)

    def _ax_z_changed(self, name):
        self._axis_var_z = name
        self.plot(axis_changed=True)

    def clear(self):
        for material in self.unique_series:
            for id in self.unique_series[material]:
                series = self.unique_series[material][id]["series"]
                self._graph.removeSeries(series)

        self.unique_series = {
            material: {} for material in self._parent.SCATTER3D_ALLOWED_MATERIALS
        }

    def plot(self, axis_changed: bool = False):
        """axis_changed: true if the variable of
        one of the axes was changed by the user
        """
        index_x = self._axis_options_index_map[self._axis_var_x]
        index_y = self._axis_options_index_map[self._axis_var_y]
        index_z = self._axis_options_index_map[self._axis_var_z]
        for material in self.unique_series:
            if material not in self._parent.SCATTER3D_ALLOWED_MATERIALS:
                if material == "":
                    material_name = "unknown"
                else:
                    material_name = "other"
            else:
                material_name = material

            color = self._parent.SCATTER3D_COLOR_MAP[material_name]
            for id in self.unique_series[material]:
                if "proxy" not in self.unique_series[material][id]:
                    proxy = QScatterDataProxy()
                    series = QScatter3DSeries(proxy)

                    name = f"{id} | {material}"
                    series.setName(name)
                    # alternatively: "@xLabel | @yLabel | @zLabel | @seriesName"
                    series.setItemLabelFormat("@seriesName")
                    series.setMeshSmooth(True)
                    series.setBaseColor(color)
                    series.setColorStyle(Q3DTheme.ColorStyleUniform)

                    self.unique_series[material][id]["proxy"] = proxy
                    self.unique_series[material][id]["series"] = series
                    self._graph.addSeries(series)
                else:
                    proxy = self.unique_series[material][id]["proxy"]
                    series = self.unique_series[material][id]["series"]

                if self._legend_buttons[material_name].isChecked():
                    if (
                        len(self.unique_series[material][id]["data"])
                        > len(proxy.array())
                        or axis_changed
                    ):
                        # if none of the datapoints are None
                        if not any(
                            [
                                data[index_x] is None
                                or data[index_y] is None
                                or data[index_z] is None
                                for data in self.unique_series[material][id]["data"]
                            ]
                        ):
                            dataArray = [
                                QScatterDataItem(
                                    QVector3D(
                                        data[index_x],
                                        data[index_y],
                                        data[index_z],
                                    )
                                )
                                for data in self.unique_series[material][id]["data"]
                            ]

                            proxy.resetArray(dataArray)
                        else:
                            for data in self.unique_series[material][id]["data"]:
                                if (
                                    data[index_x] is None
                                    or data[index_y] is None
                                    or data[index_z] is None
                                ):
                                    print(
                                        "WARNING: trying to plot point on normalized axis while non normalized data is present!"
                                    )
                                    print(
                                        "\tSWITCHING TO DISPLAYING NON NORMALIZED DATA..."
                                    )
                                    self._axis_var_x = (
                                        self._axis_var_x.rstrip("_norm") + "_snv"
                                    )
                                    self._axis_var_y = (
                                        self._axis_var_y.rstrip("_norm") + "_snv"
                                    )
                                    self._axis_var_z = (
                                        self._axis_var_z.rstrip("_norm") + "_snv"
                                    )
                                    self._axXSelection.setCurrentText(self._axis_var_x)
                                    self._axYSelection.setCurrentText(self._axis_var_y)
                                    self._axZSelection.setCurrentText(self._axis_var_z)
                            self.plot(axis_changed=True)
                            return

                        if series not in self._graph.seriesList():
                            self._graph.addSeries(series)
                else:
                    self._graph.removeSeries(series)

    def export(self):
        return NotImplemented


class Histogram(QVBoxLayout):
    def __init__(self, parent: PsPlot):
        super().__init__()
        self._parent = parent

        self._init_plot_widget()
        self._init_button_control()

        self.addWidget(self._plotWidget, 80)
        self.addLayout(self._controlLayout, 20)

    def _init_plot_widget(self):
        self._plotWidget = pg.PlotWidget(background=None)

        self._plotWidget.hideButtons()
        self._plotWidget.setMenuEnabled(True)
        self._plotWidget.setMouseEnabled(x=False, y=False)
        self._plotWidget.setLimits(
            xMin=0,
            xMax=100,
            yMin=0,
        )
        self._plotWidget.setXRange(0, 100)
        self._plotWidget.setYRange(0, len(self._parent.clf.classes_) + 0.5)

        axis = self._plotWidget.getAxis("left")
        # the labels for the vertical axis, they are flipped because
        # humans read from top to bottom
        vertical_axis = {
            idx: name
            for idx, name in enumerate(
                self._parent.clf.classes_[::-1],
                start=1,
            )
        }
        axis.setTicks([vertical_axis.items()])
        axis.setStyle(tickLength=0)

        axis = self._plotWidget.getAxis("bottom")
        axis.setTicks([{x: str(x) for x in range(0, 120, 20)}.items()])

        yticks = list(range(1, len(self._parent.clf.classes_) + 1))
        widths = [0] * len(self._parent.clf.classes_)
        self._bars = pg.BarGraphItem(
            x0=0,
            y=yticks,
            height=0.8,
            width=widths,
            brush=QColor(self._parent.palette().highlight().color()),
        )
        self._plotWidget.addItem(self._bars)
        # draw the text for each bar
        self._texts = []
        for x, y in zip(widths, yticks):
            if x >= 50:
                text = pg.TextItem(text=str(x), anchor=(1, 0.5))
                text.setPos(x, y)
            else:
                text = pg.TextItem(text=str(x), anchor=(0, 0.5))
                text.setPos(x, y)

            self._texts.append(text)
            self._plotWidget.addItem(text)

    def _init_button_control(self):
        self._sortBtnGroup = QButtonGroup()
        self._sortDefaultBtn = QRadioButton("sort default")
        self._sortDefaultBtn.setChecked(True)
        self._sortBtnGroup.addButton(self._sortDefaultBtn)
        self._sortCertaintyBtn = QRadioButton("sort score")
        self._sortBtnGroup.addButton(self._sortCertaintyBtn)
        self._sortBtnGroup.buttonClicked.connect(self._sorting_selection_changed)

        self._clearBtn = QPushButton("Clear graph")
        self._clearBtn.clicked.connect(self.clear)

        self._exportBtn = QPushButton("Export graph")
        # self.threeDExportPlotBtn.clicked.connect()

        self._controlLayout = QGridLayout()
        self._controlLayout.addWidget(self._sortDefaultBtn, 0, 0)
        self._controlLayout.addWidget(self._sortCertaintyBtn, 0, 1)
        self._controlLayout.addWidget(self._clearBtn, 1, 0)
        self._controlLayout.addWidget(self._exportBtn, 1, 1)
        self._controlLayout.setSpacing(0)

    def _sorting_selection_changed(self):
        self.plot()

    def plot(self):
        data = self._parent.df.loc[
            len(self._parent.df) - 1, self._parent.PREDICTION_HEADERS
        ]
        data = pd.DataFrame([data], columns=self._parent.PREDICTION_HEADERS)
        prediction = {
            plastic: self._parent.clf.predict_proba(data)[0][idx] * 100
            for idx, plastic in enumerate(self._parent.clf.classes_)
        }
        yticks = list(range(1, len(prediction) + 1))
        # the order of the predicted values is flipped here because the
        # labels are also flipped
        widths = [int(x) for x in list(prediction.values())[::-1]]

        # if ever uncertain about the order of the predictions, use this:
        # for idx, material in enumerate(self.clf.classes_):
        #     print(f"{material}: {self.clf.predict_proba(data)[0][idx] * 100}%")

        axis = self._plotWidget.getAxis("left")
        if self._sortDefaultBtn.isChecked():
            # the labels for the vertical axis, they are flipped because
            # humans read from top to bottom
            vertical_axis = {
                idx: name
                for idx, name in enumerate(
                    self._parent.clf.classes_[::-1],
                    start=1,
                )
            }
        elif self._sortCertaintyBtn.isChecked():
            widths, names = map(
                list,
                zip(*sorted(zip(widths, self._parent.clf.classes_[::-1]))),
            )
            vertical_axis = {
                idx: name
                for idx, name in enumerate(
                    names,
                    start=1,
                )
            }

        axis.setTicks([vertical_axis.items()])

        self._bars.setOpts(y=yticks, width=widths)
        for x, y, text in zip(widths, yticks, self._texts):
            if x >= 50:
                text.setAnchor = (1, 0.5)
            else:
                text.setAnchor = (0, 0.5)
            text.setText(str(x))
            text.setPos(x, y)

    def clear(self):
        """set the position of all of the bars to 0"""
        yticks = list(range(1, len(self._parent.clf.classes_) + 1))
        widths = [0] * len(self._parent.clf.classes_)
        self._plotWidget.clear()
        self._bars = pg.BarGraphItem(
            x0=0,
            y=yticks,
            height=0.8,
            width=widths,
            brush=QColor(self._parent.palette().highlight().color()),
        )
        self._plotWidget.addItem(self._bars)

        # draw the text for each bar
        for x, y in zip(widths, yticks):
            if x >= 50:
                text = pg.TextItem(str(x), anchor=(1, 0.5))
                text.setPos(x, y)
            else:
                text = pg.TextItem(str(x), anchor=(0, 0.5))
                text.setPos(x, y)

            self._plotWidget.addItem(text)

    def export(self):
        return NotImplemented
