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
from typing import List
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


class Table(QTableWidget):
    """
    this class extends QTableWidget
    * supports copying multiple cell's text onto the clipboard
    * formatted specifically to work with multiple-cell paste into programs
      like google sheets, excel, or numbers
    Taken and modified from https://stackoverflow.com/a/68598423/5539470
    """

    def __init__(
        self,
        TABLE_HEADER: List[str],
        TABLE_DATAFRAME_SUBSET_HEADERS: List[str],
    ) -> None:
        super().__init__()

        self.setColumnCount(len(TABLE_HEADER))
        self.setHorizontalHeaderLabels(TABLE_HEADER)
        self.itemChanged.connect(self.tableChanged)
        # make the first 2 columns extra wide
        self.setColumnWidth(0, 200)
        self.setColumnWidth(1, 200)

        self.row_labels = []
        self.calibration_counter

    def append(
        self,
        data: List[float],
        name: str = "",
        material: str = "unknown",
        color: str = "",
        calibrated_measurement: bool = False,
    ) -> None:
        ...
        n_rows = self.rowCount()
        # add a row
        self.setRowCount(n_rows + 1)

        # add sample name as column 0
        self.setItem(n_rows, 0, QTableWidgetItem(name))
        # add sample material as column 1
        self.setItem(n_rows, 1, QTableWidgetItem(material))
        # add sample color as column 2
        self.setItem(n_rows, 2, QTableWidgetItem(color))

        if calibrated_measurement:
            self.calibration_counter += 1
            self.row_labels.append(f"c {self.calibration_counter}")
            self.setItem(n_rows, 1, QTableWidgetItem("spectralon"))
        else:
            self.row_labels.append(str(n_rows + 1 - self.calibration_counter))

        self.setVerticalHeaderLabels(self.row_labels)

        # add value for every column of new row
        dataStr = list_to_string(data)
        for col, val in enumerate(dataStr.split(), start=3):
            cell = QTableWidgetItem(val)
            # disable editing of cells
            cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)

            # use a different color if the measurement was taken for calibration
            self.setItem(n_rows, col, cell)

        # apply different background color for calibration measurement
        if calibrated_measurement:
            for column in range(self.columnCount()):
                self.item(n_rows, column).setBackground(self.palette().alternateBase().color())

        self.scrollToBottom()

    def clear(self) -> None:
        """clears the contents of the table"""
        self.clearContents()
        self.setRowCount(0)
        self.row_labels = []

    # TODO this should become an emitted signal
    def itemChanged(self, item) -> None:
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
