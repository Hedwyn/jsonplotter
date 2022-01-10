from serial import *
import serial.tools.list_ports
from parameters import *
import threading
from JsonParser import JsonParser
import sys
import platform
import json

LOG_DIR =  'SerialLogs'
OS = platform.system()
if OS.startswith('Linux'):
    SERIAL_ROOT = '/dev/'
    SERIAL_PREFIX = 'ttyACM0'
elif OS.startswith('Win') or OS.startwith('win'):
    SERIAL_ROOT = ''
    SERIAL_PREFIX = 'COM'

else:
    sys.exit()

class SerialInterface():
    def __init__(self, parent = None):
        self.parent = parent
        self.baudrate = DEFAULT_BAUDRATE
        self.detectedPorts = []
        self.connectedPorts = {}
        self._stop = False
        self.jsonLogs = {}

    def alert(self, msg):
        if self.parent:
            self.parent.alert(msg)

    def scanPorts(self):
        """Scans connected serial ports and store them"""
        self.detectedPorts = []
        ports = list(serial.tools.list_ports.comports())
        for entry in [port.device for port in ports]:
            if entry.startswith(SERIAL_ROOT + SERIAL_PREFIX):
                # appending to serial devives scrollbar
                self.detectedPorts.append(entry)        

    def startSerialConnection(self, port):
        """Calls a thread to start a new serial connection"""
        # checking that the port is not already connected
        if not (port in self.connectedPorts):
            t = threading.Thread(target = self.readSerial, args = (port,))
            self.connectedPorts[port] = t
            # terminating the thread when the program exits
            t.daemon = True
            t.start()
            self.jsonLogs[port] = JsonParser()
    
    def stopSerialConnection(self, port):
        """Stops the reading thread for the port passed as argument"""
        t = self.connectedPorts[port]
        # removing the port from the list of connected ports
        del self.connectedPorts[port]

    def readSerial(self, port, filename = 'serialLog'):
        filename = LOG_DIR + '/' + filename + '.txt'
        try:
            p =  Serial(port, baudrate = 115200)
        except:
            print("Cannot connect to" + port)      
            return
        while (port in self.connectedPorts):
            try:
                line = p.readline().decode('utf-8')
                self.jsonLogs[port].parse_line(line)
            except:
                pass
                    


    
        
if __name__ == "__main__":
    s = SerialInterface()
    s.readSerial('COM3')



        
    