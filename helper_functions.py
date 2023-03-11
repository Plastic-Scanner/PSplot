import numpy as np
from numpy.typing import ArrayLike
from typing import List, Union


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
