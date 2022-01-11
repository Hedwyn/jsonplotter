"""****************************************************************************
Copyright (C) 2021 LCIS Laboratory - Baptiste Pestourie

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, in version 3.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.
You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
This program is part of the SecureLoc Project @https://github.com/Hedwyn/JsonPlotter
 ****************************************************************************

@file plotter.py
@author Baptiste Pestourie
@date 2021 May 1st
@brief Application module - contain the Model/View representation of the JsonPlotter application
@see https://github.com/Hedwyn/JsonPlotter
"""
# PyQt5 
from PySide2 import QtCore, QtWidgets, QtGui
from PySide2.QtWidgets import QDial, QTabWidget, QSpacerItem, QStyleFactory, QApplication, QLineEdit, QColorDialog, QToolButton, QTreeView, QFileSystemModel, QCheckBox, QBoxLayout, QComboBox, QLabel, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox, QMainWindow,QMenuBar, QMenu,QDockWidget
from PySide2.QtCore import QDir, QFile, QTextStream, QTimer
from PySide2.QtGui import QIcon


# matplotlib 
import matplotlib
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
matplotlib.use('Qt5Agg')

# other python dependencies
import time
import numpy as np
import sys
import json 
from datetime import datetime
import math

# project modules
from JsonParser import JsonParser
from serialInterface import SerialInterface
from mqttInterface import MqttInterface
from parameters import *
from BreezeStyleSheets import breeze_resources
from enum import Enum
from filters import Filter, MovingMedian

## Matplotlib configuration
plt.style.use(DEFAULT_MPL_TEMPLATE)

class LabeledEntry(QWidget):
    def __init__(self, name = ''):
        super().__init__()
        self.layout = QHBoxLayout()
        self.entry = QLineEdit()
        self.layout.addWidget(QLabel(name))
        self.layout.addWidget(self.entry)
        self.setLayout(self.layout)

class DeletableComboBox(QWidget):
    """A Qt Combo Box that can be deleted with an adjacent delete button"""
    def __init__(self, addParamBtn = False):
        super().__init__()
        self.alive = True
        self.layout = QHBoxLayout()
        self.cbox = QComboBox()
        self.deleteBtn = QPushButton("Delete")
        self.deleteBtn.clicked.connect(self.delete)
        self.layout.addWidget(self.cbox)
        self.layout.addWidget(self.deleteBtn)
        self.setLayout(self.layout)
        if addParamBtn:
            self.paramBtn = QToolButton()
            self.paramBtn.setIcon(QIcon(PARAM_DEFAULT_ICON))
            self.paramPopup = ParametersPopup()
            self.paramBtn.clicked.connect(self.paramPopup.show)
            self.layout.addWidget(self.paramBtn)
            
        else:
            self.paramBtn = None
    
    def delete(self):
        """Destroys the widget and calls the destroy function of the parent if any"""
        self.deleteLater()
        self.alive = False

class ParametersPopup(QMainWindow):
    """A popup template for parameter settings, contaning an arbitrary number of labeled entries"""
    def __init__(self):
        super().__init__()
        self._filterRef = None
        self.setWindowTitle("Parameters")
        self.body = QWidget()
        self.layout = QVBoxLayout()
        self.setCentralWidget(self.body)
        self.body.setLayout(self.layout)
        self.entries = {}
    
    @property
    def filterRef(self):
        return(self._filterRef)

    @filterRef.setter
    def filterRef(self, ref):
        self._filterRef = ref
        self.updateParams()
    
    def updateParams(self):
        """Parses the list of parameters given in reference and creates a labelled entry for each. Deletes entries which are not part of the param list"""
        # deleting unused params
        for param in list(self.entries):
            if not(param in self.filterRef.userParams):
                self.entries[param].deleteLater()
                del self.entries[param]
        # adding new params
        for param in self.filterRef.userParams:
            if not(param in self.entries):
                newEntry = LabeledEntry(param)
                self.entries[param] = newEntry
                newEntry.entry.editingFinished.connect(lambda p = param, t = self.filterRef.userParams[param]: self.setParam(p, t))
                self.layout.addWidget(newEntry)
    
    def deleteParam(self, param):
        """Deletes the parameters passed as argument from both the labeled entries and the parameters list"""
        self.entries.pop(param, None)
        if param in self.filterRef.userParams:
            del self.filterRef.userParams.userParams[param]
    
    def setParam(self, param, outputType):
        """Sets the value given by the user"""
        if param in self.entries:
            valStr = self.entries[param].entry.text()
            if valStr != '':

                try:
                    val = outputType(valStr)
                    setattr(self.filterRef, param, val)

                except:
                    AppModel.alert("The following parameter is given in not correctly typed: " + param + "; expected: " + str(outputType))
                
class DeletableFilterBox(DeletableComboBox):
    """A Filter Combo Box that can be deleted with an adjacent delete button"""
    def __init__(self, parent = None):
        super().__init__(addParamBtn = True)
        self.parent = parent
        self.filter = None
        self.cbox.currentIndexChanged.connect(self.setFilter)
        # getting the names of all the filters available
        for f in Filter.getAvailableFilters():
            self.cbox.addItem(f.name())
    
    def delete(self):
        super().delete()
        try:
            self.parent.deleteFilter(self)
        except AttributeError:
            pass

    def setFilter(self):
        selectedFilter = self.cbox.currentText()
        for f in Filter.getAvailableFilters():
            if selectedFilter == f.name():
                # calling choosen filter __init__
                self.filter = f()
                self.paramPopup.filterRef = self.filter


class PlotSource(Enum):
    """Simple enumeration type for the main types of inputs that can that be processed by the plotting engine"""
    FILE = 0
    SERIAL = 1
    MQTT = 2

class PlotMode(Enum):
    """Enumeration type for the different types of matplotlib plots available to the user: histogram, XY, etc."""
    NORMAL = "Normal"
    XY = "XY"
    HIST = "Histogram"
    XY_HIST = "2D Histogram"

class LinearPlot(Enum):
    """Different types of single-data plots"""
    BY_INDEX ="By index"
    CHRONOLOGICAL = "Chronological"

class HistPlot(Enum):
    """Different types of 1D Hist plots"""
    RAW = "Raw"
    NORMALIZED = "Normalized"

class MplCanvas(FigureCanvas):
    """Contains a Matplotlib figure with a single axis"""
    def __init__(self, parentApp=None, controlDock = None, width=10, height= 7, dpi=100):
        self.parentApp = parentApp
        self.controlDock = controlDock
        self._width = width
        self._height = height
        self._dpi = dpi
        self.fig = None
        self._dataSource = PlotSource.FILE
        self.currentPlot = None
        self.colorbarRef = None

        ## plot parameters
        self.currentStyle = DEFAULT_MPL_TEMPLATE
        self.xLowLim = None
        self.xHighLim = None
        self.yLowLim = None
        self.yHighLim = None
        self.sampleWidth = None
        self.initFigure()
        super(MplCanvas, self).__init__(self.fig)

    @property
    def dataSource(self):
        return self._dataSource
    
    @dataSource.setter
    def dataSource(self, source):
        # clearing axes when a new source is selected
        self.setPlotSource(source)
    
    @property
    def plotMode(self):
        mode = self.parentApp.currentTab.modeSelection.currentText()
        for m in PlotMode:
            if m.value == mode:
                return(m)
        else:
            # defaulting to normal
            return(PlotMode.NORMAL)
    
    @property
    def linearPlotType(self):
        if self.plotMode == PlotMode.NORMAL:
            plotType = self.parentApp.currentTab.xAxisSelection.currentText()
            for t in LinearPlot:
                if t.value == plotType:
                    return(t)
            else:
            # default mode
                return(LinearPlot.BY_INDEX)
                
    def initFigure(self):
        plt.style.use(self.currentStyle)
        self.fig = Figure(figsize=(self._width, self._height), dpi= self._dpi)
        self.axes = self.fig.add_subplot(111)
        
    def resetFigure(self):
        self.axes.clear()
        self.initFigure()
        ## assigning Mpl figure to the new figure
        self.figure = self.fig

    def setPlotSource(self, source):
        """Sets the input of the MPL canvas to the given source, either a json file, a MQTT stream or a serial stream"""
        if isinstance(source, PlotSource):
            self._dataSource = source
        self.controlDock.freezeOn = False


class PlotSettings(QMainWindow):
    def __init__(self, parent):
        super().__init__()
        ## internal parameters
        self.parent = parent
        self._qtColor = None
        self.gridOn = True
        self.legendOn = False
        self.color = DEFAULT_PLOT_COLOR
        self.style = DEFAULT_MPL_TEMPLATE

        ## widgets
        self.body = QWidget()
        self.gridChk = QCheckBox('Grid')
        self.gridChk.stateChanged.connect(self.onGridChecked)
        self.gridChk.setChecked(self.gridOn)

        self.legendChk = QCheckBox('Legend')
        self.legendChk.stateChanged.connect(self.onLegendChecked)
        self.legendChk.setChecked(self.legendOn)
        self.colorBtn = QPushButton('Color')
        self.colorBtn.clicked.connect(self.openColorDialog)

        ## matplotlib style selector
        self.styleCbox = QComboBox()
        for style in plt.style.available:
            self.styleCbox.addItem(style)
        self.styleCbox.currentIndexChanged.connect(self.onStyleSelected)

        # validation button
        self.validateBtn = QPushButton("OK")
        self.validateBtn.clicked.connect(self.onValidate)

    def onValidate(self):
        self.parent.plotJson()
        self.destroy()

    def openColorDialog(self):
        """Opens a color map for plot color selection"""
        colorDialog = QColorDialog()
        self._qtColor = colorDialog.getColor()
        r = self._qtColor.red()
        g = self._qtColor.green()
        b = self._qtColor.blue()
        self.color = self.convertToHmtl(r, g, b)
        
    def onGridChecked(self, state):
        """Triggered when the grid checkbox is checked. Saves the grid settings as a boolean"""
        if state > 0:
            self.gridOn = True
        else:
            self.gridOn = False

    def onLegendChecked(self, state):
        """Triggered when the legend checkbox is checked. Saves the legend settings as a boolean"""
        if state > 0:
            self.legendOn = True
        else:
            self.legendOn = False


    def onStyleSelected(self):
        """Trigerred when a style is selected in the style combo box. Sets the current matplotlib style to the new style chosen"""
        self.style = self.styleCbox.currentText()

    
    @staticmethod
    def convertToHmtl(r, g, b):
        """converts the color given as R, G, B to an HTML color code
        params
        r: int - red component as an integer between 0 and 255
        g: int - green component as an integer between 0 and 255 
        b: int - blue component as an integer between 0 and 255
        """
        return ('#%02x%02x%02x' % (r, g, b))


class PlotSettingsWindow(PlotSettings):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Advanced plot settings")
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.gridChk)
        self.layout.addWidget(self.legendChk)
        self.layout.addWidget(self.colorBtn)
        self.layout.addWidget(self.styleCbox)
        self.layout.addWidget(self.validateBtn)
        self.setCentralWidget(self.body)
        self.resize(600, 400)
        self.body.setLayout(self.layout)

class FiltersModel(QMainWindow):
    def __init__(self, view, parent):
        super().__init__()
        self.view = view
        self.parent = parent
        self.filtersChain = []
        self.body = QWidget()
        self.addFilterBtn = QPushButton("Add filter")
        self.addFilterBtn.clicked.connect(self.onAddFilter)
        self.filters = []
    
    def onAddFilter(self):
        """Adds a new filter entry as deletable combo box in the filter chain"""
        newFilter = DeletableFilterBox(self)
        self.filters.append(newFilter)
        self.view.addFilter(newFilter)
        # self.newFilter.currentIndexChanged.connect(lambda: self.)

    def currentFilters(self):
        """Returns a generator of references to the current filter instances enabled by the user"""
        for f in self.filters:
            yield f.filter 

    def deleteFilter(self, f):
        """Removes a filter from the list of filters when its delete button is pressed"""
        self.filters.remove(f)

    
    def apply(self, inputData):
        """Applies the filter chain to the input data and returs the results"""
        outputData = inputData
        for f in self.currentFilters():
            f.input = outputData
            outputData = f.apply()
        return(outputData)


class FiltersWindow(FiltersModel):
    def __init__(self, parent):
        super().__init__(self, parent)
        self.setWindowTitle("Filter chain")
        self.resize(600, 400)
        self.setCentralWidget(self.body)
        self.mainLayout = QVBoxLayout()
        self.body.setLayout(self.mainLayout)
        self.mainLayout.addWidget(self.addFilterBtn)

        
    def addFilter(self, newFilter):
        """Displays the newly created filter deletable combo box"""
        self.mainLayout.addWidget(newFilter)
        
    def toggle(self):
        """Switch function that shows/hides the filtering chain"""
        if self.isVisible():
            self.hide()
        else:
            self.show()


class MplDock(QDockWidget):
    """Right pane, contains the real-time controls for the matplotlib plot"""
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.setWindowTitle("Plot controls") 
        self.mplPane = QWidget()
        self.setWidget(self.mplPane)

        ## control buttons
        self.resetBtn = QPushButton("Reset settings")
        self.resetBtn.clicked.connect(self.onReset)
        self.clearBtn = QPushButton("Clear")
        self.clearBtn.clicked.connect(self.parent.clearData)
        self.freezeBtn = QPushButton("Freeze")
        self.freezeBtn.clicked.connect(self.onFreeze)
        self._freezeOn = False

        
        ## graph boundaries
        self.xLowLimEntry = QLineEdit(parent = self.mplPane)
        self.xHighLimEntry = QLineEdit(parent = self.mplPane)
        self.yLowLimEntry = QLineEdit(parent = self.mplPane)
        self.yHighLimEntry = QLineEdit(parent = self.mplPane)
        self.widthEntry = QLineEdit(parent = self.mplPane)
        self.xLowLimEntry.editingFinished.connect(self.onXLowLimSet)
        self.xHighLimEntry.editingFinished.connect(self.onXHighLimSet)
        self.yLowLimEntry.editingFinished.connect(self.onYLowLimSet)
        self.yHighLimEntry.editingFinished.connect(self.onYHighLimSet)
        self.widthEntry.editingFinished.connect(self.onWidthSet)

        ## filtering controls
        self.filters = FiltersWindow(parent = self)
        self.filtersBtn = QPushButton("Open filters")
        self.filtersBtn.clicked.connect(self.filters.toggle)

        ## parameters
        self.paramBtn = QToolButton()
        self.paramBtn.setIcon(QIcon(PARAM_DEFAULT_ICON))
        self.paramBtn.clicked.connect(self.openParams)

    def openParams(self):
        self.params = ParametersPopup()
        self.params.show()


    @property
    def freezeOn(self):
        return(self._freezeOn)
    
    @freezeOn.setter
    def freezeOn(self, state):
        if state == False and self.freezeOn == True:
            self.parent.plotTimer.start()
            self.freezeBtn.setText("Freeze")
            self._freezeOn = False        
        elif state == True and self.freezeOn == False:
            self.parent.plotTimer.stop()
            self.freezeBtn.setText("Unfreeze")
            self._freezeOn = True            

    def onReset(self):
        """Reset the plot parameters"""
        self.xLowLimEntry.clear()
        self.parent.canvas.xLowLim = None

        self.xHighLimEntry.clear()
        self.parent.canvas.xHighLim = None

        self.yLowLimEntry.clear()
        self.parent.canvas.yLowLim = None

        self.yHighLimEntry.clear()
        self.parent.canvas.yHighLim = None

        self.widthEntry.clear()
        self.parent.canvas.sampleWidth = None

        self.parent.plotJson()

    def onFreeze(self):
        """Toggles on and off plot freeze"""
        self.freezeOn = not(self.freezeOn)

    def onXLowLimSet(self):
        if self.xLowLimEntry.text() == '':
            self.parent.canvas.xLowLim = None
        else:
            try:
                self.parent.canvas.xLowLim = float(self.xLowLimEntry.text())
            except:
                self.parent.alert("Please provide valid float values")
                self.xLowLimEntry.clear()

    def onXHighLimSet(self):
        if self.xHighLimEntry.text() == '':
            self.parent.canvas.xHighLim = None
        else:
            try:
                self.parent.canvas.xHighLim = float(self.xHighLimEntry.text())
            except:
                self.parent.alert("Please provide valid float values")
                self.xHighLimEntry.clear()

    def onYLowLimSet(self):
        if self.yLowLimEntry.text() == '':
            self.parent.canvas.yLowLim = None
        else:
            try:
                self.parent.canvas.yLowLim = float(self.yLowLimEntry.text())
            except:
                self.parent.alert("Please provide a valid float value")
                self.yLowLimEntry.clear()
    
    def onYHighLimSet(self):
        if self.yHighLimEntry.text() == '':
            self.parent.canvas.yHighLim = None
        else:
            try:
                self.parent.canvas.yHighLim = float(self.yHighLimEntry.text())
            except:
                self.parent.alert("Please provide a valid float value")
                self.yHighLimEntry.clear()

    def onWidthSet(self):
        try:
            self.parent.canvas.sampleWidth = int(self.widthEntry.text())
        except:
            self.parent.alert("Please provide a valid integer value")
            self.widthEntry.clear()

class MqttDock(QDockWidget):
    """Mqtt pane for all MQTT-related operations: network parameters, conenction settings, etc."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("MQTT")
        self.parent = parent
        self.interface = MqttInterface(self)
        self.mqttPane = QWidget()
        self.setWidget(self.mqttPane)

        # connection settings
        self.ipSelection = QLineEdit(parent = self.mqttPane)
        self.ipSelection.setText(DEFAULT_HOST)
        self.ipSelection.editingFinished.connect(self.checkIp)
        self.portSelection = QLineEdit(parent = self.mqttPane)
        self.portSelection.setText(str(DEFAULT_PORT))
        self.portSelection.editingFinished.connect(self.checkPort)
        self.connectBtn = QPushButton("Connect")
        self.connectBtn.clicked.connect(self.connect)
        self.scanBtn = QPushButton("Start Scanning")
        self.scanBtn.clicked.connect(self.scan)
        self.scanBtn.setEnabled(False)
        self.displayBtn = QPushButton("Plot MQTT")
        # self.parent.setPlotSource(PlotSource.MQTT)
        self.displayBtn.clicked.connect(lambda: self.parent.canvas.setPlotSource(PlotSource.MQTT) )
        self.displayBtn.clicked.connect(self.parent.plotTimer.start)
        self._isScanOn = False

        # topics management
        self.topicsCbox = QComboBox()
        self.topicsCbox.currentIndexChanged.connect(self.onTopicSelected)
        self.topicRefreshTimer = QTimer()
        self.topicRefreshTimer.setInterval(TOPIC_REFRESH_TIME)
        self.topicRefreshTimer.timeout.connect(self.getTopics)

    def checkIp(self):
        """Checks that the current ip address provided by the user is correctly formatted"""
        address = self.ipSelection.text()
        isIpCorrect = False
        fields = address.split('.')
        if len(fields) == 4:
            for field in fields:
                if field.isdigit(): # checks that the field represents a positive integer
                    byte = int(field)
                    if byte < 256:
                        isIpCorrect = True
                        continue
                isIpCorrect = False
                break 
        if (isIpCorrect):
            self.interface.host = address
        else:
            self.interface.host = None
            self.parent.alert("The provided IP address is uncorrectly formatted")

        return(isIpCorrect)
    
    def checkPort(self):
        """Checks that the provided port is correctly formatted and autorized"""
        port = self.portSelection.text()
        if port.isdigit() and int(port) in AUTHORIZED_MQTT_PORTS:
            self.interface.port = int(port)
            return(True)
        else:
            self.interface.port = None
            self.parent.alert("The provided port is not valid. Please choose among " + str(AUTHORIZED_MQTT_PORTS))
            return(False)

    def connect(self):
        """Tries to connect to the MQTT broker if the settings provided by the user are correct"""
        if (self.checkPort() and self.checkIp()):
            if (self.interface.createClient()):
                # activating scan button
                self.scanBtn.setEnabled(True)
                # enabling topic scan refresh
                self.topicRefreshTimer.start()

    
    def scan(self):
        """Switch function that starts/stops scanning for MQTT topics"""
        if self._isScanOn:
            self._isScanOn = False
            self.interface.stopScan()
            self.scanBtn.setText("Start scanning")
        else:
            self._isScanOn = True
            self.interface.startScan()
            self.scanBtn.setText("Stop scanning")

    def onTopicSelected(self):
        self.interface.currentTopic = self.topicsCbox.currentText()
        self.interface.subscribe(self.interface.currentTopic)

   
    def getTopics(self):
        """Scans the received MQTT topics and add the new ones to the topics combo box"""
        for topic in self.interface.topics:
            if self.topicsCbox.findText(topic) == -1:
                self.topicsCbox.addItem(topic)

    def closeEvent(self, event):
        """Calls parent class closeEvent and stops all timers"""
        # stopping timers
        self.topicRefreshTimer.stop()
        super().closeEvent(event)

class PlotTab(QWidget):
    """An instance of a tab containing all the plot controls. Each tab is assigned to a single plot and canvas"""
    def __init__(self, name, parent):
        super().__init__()
        self.name = name
        if not(isinstance(parent, AppModel)):
            raise AttributeError("The parent of a PlotTab should be an AppModel instance")
        self.parent = parent

        # ## timer
        # self.plotTimer = QTimer()

        ## IO & log files
        self.currentFileLog = None
        self.selectedFile = None

        # # timer for live plot refresh
        # self.plotTimer.setInterval(PLOT_REFRESH_TIME)
        # self.plotTimer.timeout.connect(self.parent.plotJson)

        ## plot-related UI
        # buttons
        self.plotBtn = QPushButton('Plot JSON Log')
        self.plotBtn.clicked.connect(lambda:self.parent.canvas.setPlotSource(PlotSource.FILE))
        self.plotBtn.clicked.connect(self.parent.plotJson)

        self.livePlotBtn = QPushButton('Plot serial')
        self.livePlotBtn.clicked.connect(lambda: self.parent.canvas.setPlotSource(PlotSource.SERIAL))
        self.livePlotBtn.clicked.connect(self.parent.plotTimer.start)
        self.livePlotBtn.clicked.connect(self.updateXAxisSelection)

        # Drop-down menus for x and y axis selection       
        self.yAxisSelection = QComboBox()
        self.xAxisSelection = QComboBox()  
        self.modeSelection = QComboBox()

        # Adding the available plot modes to the mode selection combo box
        for mode in [e.value for e in PlotMode]:
            self.modeSelection.addItem(mode)
        self.modeSelection.currentIndexChanged.connect(self.changePlotMode)

        ## file explorer for the selection of the log file to plot - opens in a different window      
        self.browserBtn = QPushButton('Browse files')
        self.browserBtn.clicked.connect(self.parent.openFileExplorer)

        self.split = QCheckBox('Split')
        # serial port 
        self.serialCbox = QComboBox()
        self.serialCbox.currentIndexChanged.connect(self.setCurrentPort)
        self.parent.serialInterface.scanPorts()
        self.serialConnBtn = QPushButton("Connect to port")
        self.serialConnBtn.clicked.connect(self.parent.startSerialConnection)
        self.serialDeconnBtn = QPushButton("Disconnect port")
        self.serialDeconnBtn.clicked.connect(self.parent.stopSerialConnection)

        for port in self.parent.serialInterface.detectedPorts:
            self.serialCbox.addItem(port)
        
        # assigning current port
        if self.parent.serialInterface.detectedPorts:
            self.currentPort = self.parent.serialInterface.detectedPorts[0]
        else:
            self.currentPort = None
        

        ## optional parameters
        self.extraParams = []
        self.tickTime = DEFAULT_TICK_TIME
        self.tickTimeEntry = LabeledEntry("Time unit")
        self.tickTimeEntry.entry.editingFinished.connect(self.setTickTime)
        ## Pop-up menus
        # file browser
        self.fileExplorer = QWidget()
        self.fileSystem = None
        self.fileTree = None
        self.fileSelectBtn = None


    # @property
    # def currentPort(self):
    #     return(self.serialCbox.currentText())

    def setCurrentPort(self):
        selectedPort = self.serialCbox.currentText()
        if selectedPort in self.parent.serialInterface.connectedPorts:
            self.currentPort = selectedPort
    
    def updateXAxisSelection(self, mode):
        """Updates the content of the x axis combo box based on the plot mode selected by the user"""
        # removing all items
        self.xAxisSelection.clear()
        self.extraParams.clear()
        if mode == PlotMode.NORMAL:
            for plotType in [t.value for t in LinearPlot]:
                self.xAxisSelection.addItem(plotType)
                self.extraParams.append(self.tickTimeEntry)
                self.parent.addOptionalParam(self.tickTimeEntry)
        
        elif mode == PlotMode.XY or mode == PlotMode.XY_HIST:
            # copying items from the x values list
            for item in [self.yAxisSelection.itemText(i) for i in range(self.yAxisSelection.count())]:
                self.xAxisSelection.addItem(item)
        
        if mode == PlotMode.HIST:
            for plotType in [t.value for t in HistPlot]:
                self.xAxisSelection.addItem(plotType)

    def changePlotMode(self):
        """Called when the user selects a new plot mode in the plot mode selection combo box."""
        self.parent.canvas.currentPlot = None
        self.parent.canvas.plotRef = None
        self.parent.canvas.axes.clear()
        mode = self.parent.canvas.plotMode
        self.updateXAxisSelection(mode)   



    def setTickTime(self):
        try:
            self.tickTime = float(self.tickTimeEntry.entry.text())
        except:
            self.parent.alert("Please provide a float value (s)")       
             
class AppModel(QMainWindow):
    """Contains all the Qt elements embedded in the Application and defines their interactions."""
    def __init__(self, *args, **kwargs):
        """Declares all the useful widgets and their mutual interactions"""
        super().__init__(*args, **kwargs)
        ## IO & log files
        self.currentFileLog = None
        self.selectedFile = None

        ##♦ Timer for plot refresh
        self.plotTimer = QTimer()
        self.plotTimer.setInterval(PLOT_REFRESH_TIME)
        self.plotTimer.timeout.connect(lambda: self.plotJson(refreshOnly = False))

        # plot speed dial button
        self.speedDial = QDial()
        # disabling dial tracking; it will only emit the vlaue changed signal when released
        self.speedDial.setTracking(False)
        self.speedDial.setNotchesVisible(True)
        self.speedDial.valueChanged.connect(self.changePlotSpeed)
        self.speedDial.setRange(MINIMUM_REFRESH_TIME, MAXIMUM_REFRESH_TIME)

        # plot data
        self.meanLabel = QLabel()
        self.stdLabel = QLabel()
        self.medianLabel = QLabel()
        self.lengthLabel = QLabel()
        self.commentEntry = LabeledEntry('Comment')


        ## Creating the main window 
        self.body = QWidget()
        
        ## left Dock - MQTT panel
        self.mqttDock = MqttDock(self)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, self.mqttDock)

        ## Right dock - Live plot control
        self.mplDock = MplDock(self)
 
        ## Creating the integrated Mpl figure
        self.canvas = MplCanvas(parentApp = self, controlDock = self.mplDock)

        ## top menu
        self.topBar = QMenuBar()
        self.viewMenu = QMenu()
        self.viewMenu.addAction("Display Mpl Pane")
        # self.topBar.addMenu(self.viewMenu)
        self.topBar.addAction("View")
        self.plotSettingsBtn = QPushButton('Advanced Settings')
        self.plotSettingsBtn.clicked.connect(self.onPlotSettings)
        self.plotSettings = PlotSettingsWindow(self)
        
        ## tabs for the plot-related UI
        self.tabBar = QTabWidget()
        self.tabs = {}

        ## MPL toolbar
        self.toolbar = NavigationToolbar(self.canvas, self)

        ## Serial Interface
        self.serialInterface = SerialInterface(self)

        for port in self.serialInterface.detectedPorts:
            self.serialCbox.addItem(port)
        
        ## Pop-up menus
        # file browser
        self.fileExplorer = QWidget()
        self.fileSystem = None
        self.fileTree = None
        self.fileSelectBtn = None

        # creating the 'add Tab' button
        self.tabBar.addTab(QWidget(), QIcon(PARAM_DEFAULT_ICON), 'New')
        
        # creating the first tab and setting the view on it
        self.addTab()
        self.tabBar.setCurrentIndex(0)
        self.tabBar.currentChanged.connect(self.onTabChanged)

    def getLogForSource(self, source):
        log = None
        if source == PlotSource.FILE:
            log = self.currentFileLog 
        elif source == PlotSource.SERIAL:
            log = self.serialInterface.jsonLogs[self.currentTab.currentPort]    
        elif source == PlotSource.MQTT:
            log = self.mqttDock.interface
        return(log)     

    @property
    def sourceLog(self):
        return(self.getLogForSource(self.canvas.dataSource))
        # source = None
        # if self.canvas.dataSource == PlotSource.FILE:
        #     source = self.currentFileLog 
        # elif self.canvas.dataSource == PlotSource.SERIAL:
        #     source = self.serialInterface.jsonLogs[self.currentPort]    
        #     print(self.currentPort)
        #     print(self.serialInterface.jsonLogs.keys())   
        # elif self.canvas.dataSource == PlotSource.MQTT:
        #     source = self.mqttDock.interface
        # return(source)

    @property
    def currentTopic(self):
        topic = None
        if self.canvas.dataSource == PlotSource.FILE:
            topic = self.currentTab.yAxisSelection.currentText()
            
        elif self.canvas.dataSource == PlotSource.SERIAL:
            topic = self.currentTab.yAxisSelection.currentText()
            
        elif self.canvas.dataSource == PlotSource.MQTT:
            topic = self.mqttDock.interface.currentTopic
        return(topic)

    @property
    def currentTab(self):
        """Reference to the current tab widget"""
        return(self.tabBar.currentWidget())
    
    @currentTab.setter
    def currentTab(self, val):
        """Prevents from overwriting the reference to the current tab"""
        pass

    def addTab(self, name = None):
        """Adds a new tab in the plot menu. Each tab handles a single plot."""
        count = len(self.tabs)
        if name is None:
            name = 'Plot ' + str(count + 1)

        newTab =  PlotTab(name, self)
        self.tabBar.insertTab(len(self.tabs), newTab, name)
        # registering the new tab
        self.tabs[name] = newTab
        self.tabBar.setCurrentIndex(count)
        return(newTab)

    def onTabChanged(self, index):
        """Triggered when a new tab is selected"""
        if index == self.tabBar.count() - 1:
            # the last tab is clicked when the user wants to create a new tab
            self.addTab()

        # destroying current plot reference which is linked to the previous tab
        self.canvas.currentPlot = None
        self.canvas.axes.clear()

    def changePlotSpeed(self, newTimeout):
        """Modifies the timeout value of the plot timer. Controlled from the plot speed dial"""
        self.plotTimer.setInterval(newTimeout)

    def clearData(self):
        """Erases all the data accumulated for the current source"""
        if isinstance(self.sourceLog, JsonParser):
            self.sourceLog.clear_all()
        self.canvas.axes.clear()
        self.canvas.currentPlot = None


    def startSerialConnection(self):
        # starting a serial connection with the port selected by the user
        self.serialInterface.startSerialConnection(self.currentTab.serialCbox.currentText())

        # putting a timer to regularly scan json topics
        self.topicTimer = QTimer()
        self.topicTimer.setInterval(2000)
        self.topicTimer.timeout.connect(lambda:self.updateJsonTopics(source = PlotSource.SERIAL) )
        self.topicTimer.start()

    def stopSerialConnection(self):
        """Stops the current serial connection"""
        # starting a serial connection with the port selected by the user
        self.serialInterface.stopSerialConnection(self.currentTab.serialCbox.currentText())

        # stopping the timer
        self.topicTimer.stop()      

    def plotJson(self, refreshOnly = False):
        """Plots the topic selected by the user for a given json file"""
        # checking that a file has been selected
        # source = self.canvas.dataSource
        # if (source == PlotSource.FILE) and not(self.selectedFile):
        #     self.alert("You must select a file in the File Explorer first !")
        #     return
        
        # if source == PlotSource.FILE:
        #     self.sourceLog = self.currentFileLog 
        #     self.currentTopic = self.currentTab.yAxisSelection.currentText()
            
        # elif source == PlotSource.SERIAL:
        #     self.sourceLog = self.serialInterface.jsonLogs
        #     self.currentTopic = self.currentTab.yAxisSelection.currentText()
            
        # elif source == PlotSource.MQTT:
        #     self.sourceLog = self.mqttDock.interface
        #     self.currentTopic = self.mqttDock.interface.currentTopic

        # setting the style as chosen by the user
        if self.canvas.currentStyle != self.plotSettings.style:
            self.canvas.currentStyle = self.plotSettings.style
            self.canvas.resetFigure()

        ## setting y data
        self.ydata = self.sourceLog.get_topic_values(self.currentTopic, True)
        ydata = self.mplDock.filters.apply(self.ydata)
        if not(ydata):
            return

        ## Setting x data
        mode = self.canvas.plotMode
        if mode == PlotMode.NORMAL:
            plotType = self.canvas.linearPlotType 
            if plotType == LinearPlot.BY_INDEX:
                self.xdata = [i for i in range(len(ydata))]
                xLabel = "Index"
            if plotType == LinearPlot.CHRONOLOGICAL:
                self.xdata = [i * self.currentTab.tickTime for i in range(len(ydata))]
                xLabel = "Time"
        
        elif mode == PlotMode.XY or mode == PlotMode.XY_HIST:
            xTopic = self.currentTab.xAxisSelection.currentText()
            self.xdata = self.sourceLog.get_topic_values(xTopic, True)
            xLabel = xTopic

        if (self.canvas.dataSource == PlotSource.FILE):
            self.canvas.axes.clear()
            self.canvas.currentPlot = None

        ## setting label 
        label =  self.currentTab.currentPort if self.canvas.dataSource == PlotSource.SERIAL else self.selectedFile

        ## if no reference to the currentPlot, recreating a new plot
        if (self.canvas.currentPlot is None) or mode == PlotMode.HIST or mode == PlotMode.XY_HIST:
            if mode == PlotMode.NORMAL:
                self.canvas.currentPlot = self.canvas.axes.plot(self.xdata, ydata, color = self.plotSettings.color, label = label)[0]
                if self.plotSettings.legendOn:
                    self.canvas.axes.legend()
                else:
                    currentLegend = self.canvas.axes.get_legend()
                    if not(currentLegend is None):
                        currentLegend.remove()

            elif mode == PlotMode.XY:
                self.canvas.currentPlot = self.canvas.axes.scatter(self.xdata, ydata, marker = '.', c = self.plotSettings.color)[0]

            elif mode == PlotMode.HIST:
                self.canvas.currentPlot = self.canvas.axes.hist(ydata, bins = int(math.sqrt(len(ydata))), density = True, color = self.plotSettings.color)[0]

            elif mode == PlotMode.XY_HIST:
                # self.canvas.currentPlot, xedges, yedges, cmap = self.canvas.axes.hist2d(self.xdata, ydata, bins = int(math.sqrt(len(ydata))), density = True, cmap = matplotlib.cm.get_cmap(DEFAULT_CMAP))
                self.canvas.currentPlot, xedges, yedges, cmap = self.canvas.axes.hist2d(self.xdata, ydata, bins = int(math.sqrt(len(ydata))), density = True, cmap = matplotlib.cm.get_cmap('viridis'))
                
                if self.canvas.colorbarRef is None:
                    self.canvas.colorbarRef = self.canvas.figure.colorbar(cmap)
                else:
                    pass
                    # self.canvas.colorbarRef.set_cmap(cmap)
                

        else:
            self.canvas.currentPlot.set_xdata(self.xdata)
            self.canvas.currentPlot.set_ydata(ydata)

        if not(refreshOnly):    
            # settings axes labels            
            self.canvas.axes.set_ylabel(self.currentTab.yAxisSelection.currentText())
            if self.canvas.plotMode == PlotMode.NORMAL:
                self.canvas.axes.set_xlabel(xLabel, fontsize = DEFAULT_LABEL_FONT_SIZE)
                self.canvas.axes.set_ylabel(self.currentTab.yAxisSelection.currentText(), fontsize = DEFAULT_LABEL_FONT_SIZE)

            elif self.canvas.plotMode == PlotMode.XY or mode == PlotMode.XY_HIST:
                self.canvas.axes.set_xlabel(self.currentTab.xAxisSelection.currentText())
                self.canvas.axes.set_ylabel(self.currentTab.yAxisSelection.currentText())

            elif self.canvas.plotMode == PlotMode.HIST:
                self.canvas.axes.set_xlabel(self.currentTab.yAxisSelection.currentText())
                self.canvas.axes.set_ylabel("Density")


            ## setting plot boundaries
                # self.canvas.currentPlot = self.canvas.axes.plot(self.xdata, ydata, color = self.plotSettings.color)
            if self.canvas.plotMode == PlotMode.NORMAL:
                if self.canvas.sampleWidth:
                    highLim = max(self.xdata)
                    lowLim = highLim - self.canvas.sampleWidth
                    self.canvas.axes.set_xlim(lowLim, highLim)
                else:
                    highLim = self.canvas.xHighLim if self.canvas.xHighLim else max(self.xdata)
                    lowLim = self.canvas.xLowLim if self.canvas.xLowLim else min(self.xdata)
                    self.canvas.axes.set_xlim(lowLim, highLim)
                highLim = self.canvas.yHighLim if self.canvas.yHighLim else max(ydata)
                lowLim = self.canvas.yLowLim if self.canvas.yLowLim else min(ydata)
                self.canvas.axes.set_ylim(lowLim, highLim)
            self.canvas.axes.grid(b = self.plotSettings.gridOn)
        self.canvas.draw()

        ## computing mean, median and std
        try:
            if self.ydata:
                mean = np.mean(self.ydata)
                std = np.std(self.ydata)
                median = np.median(self.ydata)
                self.meanLabel.setText("Mean: " + str(mean)[:PLOT_DATA_MAX_DIGITS])
                self.medianLabel.setText("Median: " + str(median)[:PLOT_DATA_MAX_DIGITS])
                self.stdLabel.setText("Standard deviation: " + str(std)[:PLOT_DATA_MAX_DIGITS])
                self.lengthLabel.setText(str(len(self.ydata)) + " samples")
        except:
            pass



    def onPlotSettings(self):
        """Triggered when the presses the plot settings button. Open a plot settings menu in a separate window"""
        self.plotSettings.show()

    @staticmethod
    def alert(text):
        """Prints an alert message in a pop-up window"""
        alert = QMessageBox()
        alert.setText(text)
        alert.exec()

    def openFileExplorer(self):
        """Opens a file explorer in a separate window to let the user select a json file"""
        self.explorerLayout = QVBoxLayout()    
        self.fileSystem = QFileSystemModel()
        self.fileSystem.setRootPath(QDir.currentPath())
        self.fileSelectBtn = QPushButton("Select")
        self.fileSelectBtn.clicked.connect(self.onFileSelected)
        self.fileTree =  QTreeView()
        self.fileTree.setModel(self.fileSystem)
        self.fileTree.setRootIndex(self.fileSystem.index(QDir.currentPath()))
        self.explorerLayout.addWidget(self.fileTree)
        self.explorerLayout.addWidget(self.fileSelectBtn)
        self.fileExplorer.setLayout(self.explorerLayout)
        self.fileExplorer.show()       

    def onFileSelected(self):
        """Triggered when a json file is selected by the user in the pop-up file explorer. Updates the current log file targeted by the Application"""
        if self.fileTree.selectedIndexes():
            index = self.fileTree.selectedIndexes()[0]
            filename = self.fileSystem.filePath(index)
            self.selectedFile = filename
        self.currentFileLog = JsonParser(self.selectedFile)
        self.updateJsonTopics()
        self.currentTab.updateXAxisSelection(self.canvas.plotMode)
        self.fileExplorer.destroy()

    def updateJsonTopics(self, source = PlotSource.FILE):
        topics = self.getLogForSource(source).extract_topics()
        for item in [self.currentTab.yAxisSelection.itemText(i) for i in range(self.currentTab.yAxisSelection.count())]:
            if not(item in topics):
                self.currentTab.yAxisSelection.removeItem(self.currentTab.yAxisSelection.findText(item))
        
        # adding new topics
        for item in topics:
            if self.currentTab.yAxisSelection.findText(item) == -1:
                self.currentTab.yAxisSelection.addItem(item)
        # if (source == PlotSource.FILE):
        # #     topics = self.currentFileLog.extract_topics()
        #     for item in topics:
        #         if self.currentTab.yAxisSelection.findText(item) == -1:
        #             self.currentTab.yAxisSelection.addItem(item)

        # else:
        #     if self.currentTab.yAxisSelection.count() < len(self.serialInterface.jsonLogs.logs):
        #         topics = self.serialInterface.jsonLogs.extract_topics()
        #         # adding json topics to file
        #         for item in topics:
        #             if self.currentTab.yAxisSelection.findText(item) == -1:
                        # self.currentTab.yAxisSelection.addItem(item)

    def logSerialData(self):
        """Logs all the data collected on the serial interface"""
        if self.serialInterface:
            print("logging data")
            for port in self.serialInterface.jsonLogs:
                filename = ''
                ## formatting comment
                try:
                    comment = self.commentEntry.entry.text()
                    comment = "".join(x for x in comment if x.isalnum())
                    if comment != '':
                        filename += comment + '_'
                except:
                    print("Could not properly format the log name")
                # timestamp = datetime.now().strftime('%d_%m_%y_%H_%M_%S__')
                # filename += timestamp
                if self.ydata:
                    filename += '_n=' + str(len(self.ydata))
                filename += '_' + port
                filename += '.json'
                with open(LOG_DIR + '/' + filename, 'w+') as f:
                    for line in self.serialInterface.jsonLogs[self.currentTab.currentPort].logs:
                        f.write(json.dumps(line))
                        f.write('\n')
    
    def closeEvent(self, event):
        """Calls parent class closeEvent and stops all timers"""
        self.plotTimer.stop()
        super().closeEvent(event)
        if self.commentEntry.entry.text() != '':
            self.logSerialData()

        print("closing...")
        sys.exit(app.exec_)


class AppView(AppModel):
    """Manages the application rendering. 
    All the graphical-related operations are managed by AppView"""
    def __init__(self, *args, **kwargs):
        self.tabsLayout = []

        super().__init__(*args, **kwargs)
        # QtMainWindow consists of one central Widget surrounded by dock widgets.
        # defining the bnody as central widget
        self.setCentralWidget(self.body)
        self.setWindowTitle("Plotter v1.0")

        # window dimensions     
        self.setMinimumWidth(2100)
        self.setMinimumHeight(1280)
        self.setMaximumWidth(2100)
        self.setMaximumHeight(1280)

        # pop-ups dimensions
        self.fileExplorer.setMinimumWidth(800)
        self.fileExplorer.setMinimumHeight(600)
        self.fileExplorer.setMaximumWidth(800)
        self.fileExplorer.setMaximumHeight(600)

        self.mainLayout = QVBoxLayout()

        # top menu
        self.topToolbar = QHBoxLayout()
        self.topToolbar.addWidget(self.toolbar)
        self.topToolbar.addWidget(self.plotSettingsBtn)
        self.topToolbar.addWidget(QLabel("Refresh time"))
        self.topToolbar.addWidget(self.speedDial)

        ## Plot data row
        self.plotDataRow = QHBoxLayout()
        self.plotDataRow.addWidget(self.meanLabel)
        self.plotDataRow.addWidget(self.medianLabel)
        self.plotDataRow.addWidget(self.stdLabel)
        self.plotDataRow.addWidget(self.lengthLabel)

        

        self.mainLayout.addLayout(self.topToolbar)
        self.mainLayout.addLayout(self.plotDataRow)   
        self.mainLayout.addWidget(self.commentEntry)     
        self.mainLayout.addWidget(self.canvas)
    
        # self.mainLayout.addLayout(self.btnRow)
        # self.mainLayout.addLayout(self.serialRow)
        self.mainLayout.addWidget(self.tabBar)
        self.body.setLayout(self.mainLayout)

        ## MQTT left pane
        self.mqttLayout = QVBoxLayout()
        self.mqttLayout.addWidget(QLabel("MQTT broker IP address"))
        self.mqttLayout.addWidget(self.mqttDock.ipSelection)
        self.mqttLayout.addWidget(QLabel("Port Selection"))
        self.mqttLayout.addWidget(self.mqttDock.portSelection)
        self.mqttLayout.addWidget(self.mqttDock.connectBtn)
        self.mqttLayout.addWidget(self.mqttDock.scanBtn)
        self.mqttLayout.addWidget(self.mqttDock.topicsCbox)
        self.mqttLayout.addWidget(self.mqttDock.displayBtn)
        
        self.mqttDock.mqttPane.setLayout(self.mqttLayout)

        ## Live plot pane
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.mplDock)
        self.mplLayout = QVBoxLayout()

        # Controls row for x Axis limit
        self.xLimRow = QHBoxLayout()
        self.xLimRow.addWidget(QLabel("X min"))
        self.xLimRow.addWidget(self.mplDock.xLowLimEntry)
        self.xLimRow.addWidget(QLabel("X max"))
        self.xLimRow.addWidget(self.mplDock.xHighLimEntry)
        self.mplLayout.addLayout(self.xLimRow)

        # Controls row for y Axis limit
        self.yLimRow = QHBoxLayout()
        self.yLimRow.addWidget(QLabel("Y min"))
        self.yLimRow.addWidget(self.mplDock.yLowLimEntry)
        self.yLimRow.addWidget(QLabel("Y max"))
        self.yLimRow.addWidget(self.mplDock.yHighLimEntry)
        self.mplLayout.addLayout(self.yLimRow)

        # Control row for plot width
        self.widthRow = QHBoxLayout()
        self.widthRow.addWidget(QLabel("Window width"))
        self.widthRow.addWidget(self.mplDock.widthEntry)
        self.mplLayout.addLayout(self.widthRow)

        self.mplLayout.addWidget(self.mplDock.resetBtn)
        self.mplLayout.addWidget(self.mplDock.clearBtn)
        self.mplLayout.addWidget(self.mplDock.freezeBtn)
        self.mplLayout.addWidget(self.mplDock.filtersBtn)
        self.mplLayout.addWidget(self.mplDock.paramBtn)

        self.mplDock.mplPane.setLayout(self.mplLayout)
    
        # Menu bar
        self.setMenuBar(self.topBar)
        self.show()

    def formatTab(self, tab):
        """Manages the plot tabs layouts"""
        if not(isinstance(tab,  PlotTab)):
            return
        page = tab
        pageLayout = QVBoxLayout()
        page.setLayout(pageLayout)

        self.xAxisBox = QVBoxLayout()
        self.xAxisBox.addWidget(QLabel("X axis selection"))
        self.xAxisBox.addWidget(tab.xAxisSelection)

        self.yAxisBox = QVBoxLayout()
        self.yAxisBox.addWidget(QLabel("Y axis selection"))
        self.yAxisBox.addWidget(tab.yAxisSelection)
    

        self.plotModeLayout = QVBoxLayout()
        self.plotModeLayout.addWidget(QLabel("Plot Mode"))
        self.plotModeLayout.addWidget(tab.modeSelection)

        self.btnRow = QHBoxLayout()
        self.btnRow.addLayout(self.xAxisBox)
        self.btnRow.addLayout(self.yAxisBox)
        
        self.btnRow.addWidget(tab.browserBtn)
        self.btnRow.addWidget(tab.plotBtn)
        self.btnRow.addLayout(self.plotModeLayout)
        self.btnRow.addWidget(tab.split)

        self.serialRow = QHBoxLayout()
        self.serialRow.addWidget(tab.serialCbox)
        self.serialRow.addWidget(tab.serialConnBtn)
        self.serialRow.addWidget(tab.serialDeconnBtn)

        self.serialRow.addWidget(tab.livePlotBtn)

        self.extraParamRow = QHBoxLayout()
        self.extraParamRow.addSpacerItem(QSpacerItem(0, 65))


        pageLayout.addLayout(self.btnRow)
        pageLayout.addLayout(self.serialRow)
        pageLayout.addLayout(self.extraParamRow)

        self.tabsLayout.append(page)

    def addOptionalParam(self, widget):
        """Adds a context-dependant parameter to the current tab layout at the bottom"""
        self.extraParamRow.addWidget(widget)

    def addTab(self):
        newTab = super().addTab()
        self.formatTab(newTab)

        

app = QtWidgets.QApplication(sys.argv)

# set stylesheet
file = QFile(":/dark/stylesheet.qss")
file.open(QFile.ReadOnly | QFile.Text)
stream = QTextStream(file)
app.setStyleSheet(stream.readAll())
# app.setStyle(QStyleFactory.create("fusion"))
appView = AppView()


app.exec_()
sys.exit(app.exec_)
