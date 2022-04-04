#!/usr/bin/env python
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QDockWidget,
    QListWidget,
    QHBoxLayout
)
import pyqtgraph as pg
import numpy as np
import serial

#variables
baudrate = 9600
inputFile = "COM5"
max = [0.492535, 0.508075, 0.477795, 0.481705, 0.509225, 0.491605, 0.485565, 0.520375]




class Spectraplot(QMainWindow):
    def __init__(self, serialobj):
        super().__init__()

        # EXPERIMENT
        self.wavelengths = [855, 940, 1050, 1200, 1300, 1450, 1550, 1650]    # in nanometers, 20nm FWHM

        self.serial = serialobj
        self.serial.readline()  # Consume the "Plastic scanner initialized line"

        # Widgets
        self.widget = QWidget()     # Container widget
        
        self.pw = pg.PlotWidget(background=None)
        self.pi = self.pw.getPlotItem()

        self.pc = self.pw.plot(self.wavelengths, np.zeros(8), symbol="o")
        self.pw.setXRange(self.wavelengths[0], self.wavelengths[-1], padding=0.1)

        self.pi.hideButtons()
        self.pi.setMenuEnabled(False)
        # self.pi.setLimits(
        #     xMin=min(self.wavelengths) - min(self.wavelengths)*0.1 , 
        #     xMax=max(self.wavelengths) + max(self.wavelengths)*0.1, 
        #     yMin=min(data) - min(data)*0.1,
        #     yMax=max(data) + max(data)*0.1,
        #     )
        self.pi.setLabel('bottom', "Wavelength [nm]")
        self.pi.setLabel('left', "NIR output", units='V')
        self.pi.setTitle('Reflectance')

        self.layout = QHBoxLayout()
        self.layout.addWidget(self.pw)
        self.layout.setContentsMargins(30, 60, 60, 30)
        self.widget.setLayout(self.layout)
        
        self.setWindowTitle("My plotter")
        self.resize(1000, 600)
        self.setMinimumSize(600, 350)
        self.center()
        self.setCentralWidget(self.widget)
        
    def center(self):
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def keyPressEvent(self, e):
        if (e.key() == Qt.Key.Key_Escape or
            e.key() == Qt.Key.Key_Q):
            self.close()

        elif (e.key() == Qt.Key.Key_Up or
              e.key() == Qt.Key.Key_W or
              e.key() == Qt.Key.Key_Plus):
            self.pi.getViewBox().scaleBy((0.9, 0.9))

        elif (e.key() == Qt.Key.Key_Down or
              e.key() == Qt.Key.Key_S or
              e.key() == Qt.Key.Key_Minus):
            self.pi.getViewBox().scaleBy((1.1, 1.1))

        elif (e.key() == Qt.Key.Key_Left or
              e.key() == Qt.Key.Key_A):
            self.pi.getViewBox().translateBy((-10, 0))

        elif (e.key() == Qt.Key.Key_Right or
              e.key() == Qt.Key.Key_D):
            self.pi.getViewBox().translateBy((+10, 0))

        elif (e.key() == Qt.Key.Key_Home):
            self.pi.getViewBox().autoRange(padding=0.1)
        
        elif (e.key() == Qt.Key.Key_Space):
            pre = self.getBackground()                                          #do a prescan
            data = self.getMeasurement()                                        #do a normal scan
            post = self.getBackground()                                         #do a postscan

            cleaned = [x-((pre+post)/2) for x in data]                          #subtract the average of pre and post scan from normal scan
            percentage = [0,0,0,0,0,0,0,0]
            for x in range(len(data)):
                percentage[x] = (data[x]/max[x])                                #scale the readings based on the max reading defined in top (scan with speclon)
            
            #calculate ratio's
            ratio = [0,0,0]
            ratio[0] = percentage[6]/percentage[7]
            ratio[1] = percentage[5]/percentage[6]
            ratio[2] = percentage[3]/percentage[4]
            if abs(pre-post) >= 0.00005:
                print("item moved?")                                            #feedback if it moved
            elif percentage[7] <= 0.2:
                print("not enough reflection")                                  #feedback if not enough light reflected
            else: 
                #print(percentage)
                #print(cleaned)
                print("%.6f, %.6f, %.6f" %(ratio[0], ratio[1], ratio[2]))       #print most interesting ratio's
            self.plot(data)

    def getMeasurement(self):
        # send serial command
        self.serial.write(b"scan\n")

        # read response
        line = self.serial.readline()
        line = line.decode()

        # parse data
        data = line.strip('> ').strip('\r\n').split('\t')
        data = [float(x) for x in data if x != '']
        return data

    def getBackground(self):
        # send serial command
        self.serial.write(b"adc\n")

        # read response
        line = self.serial.readline()
        line = line.decode()

        # parse data
        data = float(line.strip('> ').strip('\r\n'))
        return data

    def plot(self, data):
        self.pc.setData(self.wavelengths, data)


if __name__ == "__main__":


    
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
