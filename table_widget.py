#!/usr/bin/env python

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QTableWidget,
    QTableWidgetItem,
)

import settings
from helper_functions import list_to_string


class Table(QTableWidget):
    """
    this class extends QTableWidget
    - supports copying multiple cell's text onto the clipboard
    - formatted specifically to work with multiple-cell paste into programs
      like google sheets, excel, or numbers
    - autocomplete functionality for certain columns
    Taken and modified from https://stackoverflow.com/a/68598423/5539470
    """

    def __init__(
        self,
    ) -> None:
        super().__init__()

        self.setColumnCount(len(settings.TABLE.HEADERS))
        self.setHorizontalHeaderLabels(settings.TABLE.HEADERS)

        # make the first 2 columns extra wide
        self.setColumnWidth(0, 200)
        self.setColumnWidth(1, 200)

        # the labels for the most left column
        self._row_labels = []
        # how many times a calibrated measurement has been appended
        self._calibration_counter = 0

    def append(
        self,
        data: list[float],
        name: str = "",
        material: str = "unknown",
        color: str = "",
        calibrated_measurement: bool = False,
    ) -> None:
        """Add a new row to the table.
        A row can take on one of two types: calibrated, or not calibrated.
        A calibrated row is highlighted with a different background color
        and given a different index in the left column.
        """
        n_rows = self.rowCount()
        # add a row
        self.setRowCount(n_rows + 1)

        # add sample name as column 0
        # self.setItem(n_rows, 0, QTableWidgetItem(name))
        self.setItem(n_rows, 0, QTableWidgetItem(name))

        # add sample material as column 1
        self.setItem(n_rows, 1, QTableWidgetItem(material))

        # add sample color as column 2
        self.setItem(n_rows, 2, QTableWidgetItem(color))

        if calibrated_measurement:
            self._calibration_counter += 1
            self._row_labels.append(f"c {self._calibration_counter}")
            self.setItem(n_rows, 1, QTableWidgetItem("spectralon"))
        else:
            self._row_labels.append(str(n_rows + 1 - self._calibration_counter))

        self.setVerticalHeaderLabels(self._row_labels)

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
        self._row_labels = []

    # TODO this should become an emitted signal so that the comboboxes can also be updated
    def itemChanged(self, item) -> None:
        super().itemChanged(item)

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
        """enables copying from the table using CTRL-C"""
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

    def built_from_dataframe(self) -> None:
        NotImplemented
