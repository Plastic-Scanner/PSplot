#!/usr/bin/env python
import sys
import serial
from main import Spectraplot
from PyQt6.QtWidgets import QApplication

# Working on implementing this
# ./ps-spectraplot -b 115200 /dev/ttyACM0

if __name__ == "__main__":

    baudrate = 9600
    wavelengths = [610, 680, 730, 760, 810, 860]
    inputFile = "/dev/ttyACM0"
    
    try:
        ser = serial.Serial(inputFile, baudrate=baudrate, timeout=0.5)
        print(f"Opened serial port {ser.portstr}")
    except:
        print(f"Can't open serial port {inputFile}")
        sys.exit(1)


    app = QApplication(sys.argv)
    window = Spectraplot(ser)
    window.show()
    app.exec()