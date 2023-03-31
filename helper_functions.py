#!/usr/bin/env python

from __future__ import annotations
import numpy as np
from numpy.typing import ArrayLike


def normalize(
    input_data: list[float],
    calibration_data: list[float] | ArrayLike,
) -> list[float]:
    """normalizes by dividing by `calibration_data` and also applies SNV_transform"""
    input_data = np.asarray(input_data)
    calibration_data = np.asarray(calibration_data)

    # scale by calibration measurement
    data_rescaled = input_data / calibration_data

    data_snv = snv_transform(data_rescaled)

    return list(data_snv)


def snv_transform(data: ArrayLike | list[float]) -> list[float]:
    # the following is an SNV transform
    # Subtract the mean and divide by the standarddiviation
    return list((np.asarray(data) - np.mean(data)) / np.std(data))


def list_to_string(data: list[float]) -> str:
    return " ".join([f"{i:.7f}" for i in data])
