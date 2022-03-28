from PyQt6.QtWidgets import QApplication
import pyqtgraph as pg

app = QApplication([])

wavelengths = [610, 680, 730, 760, 810, 860]
data = [239.23, 233.81, 187.27, 176.41, 172.35, 173.78]

pw = pg.plot(wavelengths, data, symbol="o")

pw.getPlotItem().getAxis('bottom').setTicks([[(wavelength, str(wavelength)) for wavelength in wavelengths]])

app.exec()