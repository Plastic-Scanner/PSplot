#!/usr/bin/env python
"""settings, constants and computed constants that all other modules use"""

from __future__ import annotations
from PyQt5.QtGui import QColor


class HARDWARE:
    """Hardware constants of the plastic scanner."""

    # the HARDWARE.WAVELENGTHS of the LED's in nanometers
    WAVELENGTHS = [940, 1050, 1200, 1300, 1450, 1550, 1650, 1720]
    # the baud rate of the used microcontroller
    BAUDRATE = 9600


class USER_INPUT:
    DEFAULT_SAMPLE_MATERIALS = [
        "PP",
        "PET",
        "PS",
        "HDPE",
        "LDPE",
        "PVC",
        "spectralon",
        "unknown",
    ]


class DATAFRAME:
    """settings for working with and loading dataframes."""

    # for the dataframe
    DATASET_URL = "https://raw.githubusercontent.com/Plastic-Scanner/data/main/data/20230117_DB2.1_second_dataset/measurement.csv"
    # the headers for the dataframe:
    # |  Reading                |   the how many'th measurement                   |
    # |  Name                   |   name or id of the piece                       |
    # |  PlasticType            |   type of the plastic                           |
    # |  Color                  |   physical color of the piece of plastic        |
    # |  MeasurementType        |   if the measurement was a calibration or not   | options: regular, calibration
    # |  nm<wavelengths>        |   measured signal per wavelength                |
    # |  nm<wavelengths>_norm   |   signal per wavelength after normalization     |
    HEADER = (
        [
            "Name",
            "PlasticType",
            "Color",
            "MeasurementType",
            "DateTime",
        ]
        + [f"nm{x}" for x in HARDWARE.WAVELENGTHS]
        + [f"nm{x}_snv" for x in HARDWARE.WAVELENGTHS]
        + [f"nm{x}_norm" for x in HARDWARE.WAVELENGTHS]
    )
    HEADER_DTYPES = (
        {
            "Name": str,
            "PlasticType": str,
            "Color": str,
            "MeasurementType": str,
            "DateTime": str,
        }
        | {f"nm{x}": float for x in HARDWARE.WAVELENGTHS}
        | {f"nm{x}_snv": float for x in HARDWARE.WAVELENGTHS}
        | {f"nm{x}_norm": float for x in HARDWARE.WAVELENGTHS}
    )


class TABLE:
    """The table widget takes data from a pandas dataframe
    It takes the data from the columns in  DATAFRAME_SUBSET_HEADERS.
    The columns of the table are also labled, for this TABLE_HEADER is used.
    """

    # the names of the columns of the table
    HEADERS = ["name", "material", "color"] + [str(x) for x in HARDWARE.WAVELENGTHS]
    # the columns of the dataframe that are represented in the table
    DATAFRAME_SUBSET_HEADERS = [f"nm{x}" for x in HARDWARE.WAVELENGTHS]


class CLASSIFIER:
    """Settings for the classifier model"""

    # the columns of the dataframe that are used for the classifier model
    PREDICTION_HEADERS = [f"nm{x}" for x in HARDWARE.WAVELENGTHS]


class SCATTER3D:
    """Settings for the 3d scatter plot."""

    AXIS_OPTIONS = (
        [f"nm{x}" for x in HARDWARE.WAVELENGTHS]
        + [f"nm{x}_snv" for x in HARDWARE.WAVELENGTHS]
        + [f"nm{x}_norm" for x in HARDWARE.WAVELENGTHS]
    )

    AXIS_VAR_X_DEFAULT = "nm1050_norm"
    AXIS_VAR_Y_DEFAULT = "nm1450_norm"
    AXIS_VAR_Z_DEFAULT = "nm1650_norm"

    # colorblind friendly colors taken and adjusted from https://projects.susielu.com/viz-palette
    # ["#ffd700", "#ffb14e", "#fa8775", "#ea5f94",
    #  "#cd34b5", "#9d02d7", "#0000ff", "#2194F9"]
    COLOR_TABLEAU = (
        QColor(255, 215, 0),
        QColor(255, 177, 78),
        QColor(250, 135, 117),
        QColor(234, 95, 148),
        QColor(205, 52, 181),
        QColor(157, 2, 215),
        QColor(33, 148, 249),
        QColor(0, 0, 255),
    )
    ALLOWED_MATERIALS = [
        "PP",
        "PET",
        "PS",
        "HDPE",
        "LDPE",
        "PVC",
        "other",
        "unknown",
    ]
    COLOR_MAP = dict(
        zip(
            ALLOWED_MATERIALS,
            COLOR_TABLEAU,
        )
    )


class GUI:
    """settings used for the main window"""

    # path to the icon
    WINDOW_LOGO = "./resources/ps_logo.png"
