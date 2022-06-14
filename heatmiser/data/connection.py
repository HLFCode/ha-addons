"""This module is effectively a singleton for serial comms"""
import serial
import time
import logging
from heatmiser import HeatmiserThermostat

logging.basicConfig(level=logging.ERROR)
_LOGGER = logging.getLogger(__name__)

class HeatmiserUH1(object):
    """
    Represents the UH1 interface that holds the serial
    connection, and can have multiple thermostats
    """

    def __init__(self, device_or_ipaddress, name: str):
        # device_or_ipaddress in the form
        #  127.0.0.1:1024
        # or
        #  /dev/ttyUSB0
        self._device_or_ipaddress = device_or_ipaddress
        self._name = name
        self.thermostats = {}
        self._serport = None
        self._init_serial()
        self._busy = False
    
    def _init_serial(self):
        """
        Initialises the serial port and tries to open it
        Returns True if successful
        """
        try:
            if self._serport is not None:
                serport_response = self._serport.close()
                self._serport = None
            
            if self._device_or_ipaddress.startswith("/"):
                # assume direct serial
                self._serport = serial.Serial(self._device_or_ipaddress)
            else:
                # assume serial over IP via socket
                self._serport = serial.serial_for_url(f"socket://{self._device_or_ipaddress}")
            # Ensures that the serial port has not
            # been left hanging around by a previous process.
            self._serport.close()
            self._serport.baudrate = 4800
            self._serport.bytesize = serial.EIGHTBITS
            self._serport.parity = serial.PARITY_NONE
            self._serport.stopbits = serial.STOPBITS_ONE
            self._serport.timeout = 3
            self._serport.open()
            _LOGGER.info(f"Serial device {self._device_or_ipaddress} opened")
            return True

        except serial.SerialException as se:
            _LOGGER.error(f"Unable to initialise serial port on {self._device_or_ipaddress}, error {se}")
            self._serport = None
            return False

    def send_msg(self, message : list):
        """
        Sends a message to the thermostat and returns the data as a list of bytes
        Attempts to reopen the serial port if it is not open
        If there are any errors or no reply an empty list is returned
        Returns the response as a List, empty list if no response or False if error
        """
        datalist = []
        if self._serport is None:
            if not self._init_serial():
                return False
        
        if self._serport is not None:
            # port successfully opened
            if self._serport.is_open:
                # All should be good to communicate via the serial port
                try:
                    sleep_count = 0
                    while self._busy:
                        _LOGGER.debug(f"Sleeping {sleep_count}...")
                        time.sleep(0.5)
                        sleep_count +=1
                    _LOGGER.debug(f"Sending {message}")
                    serial_message = bytes(message)
                    self._busy = True
                    self._serport.write(serial_message)  # Write a string

                except serial.SerialException as se:
                    _LOGGER.error(f"Error writing to {self._device_or_ipaddress}: {se}")
                    self._serport.close()
                    self._serport = None
                    self._busy = False
                    return datalist

                except serial.SerialTimeoutException:
                    _LOGGER.error(f"Timeout writing to {self._device_or_ipaddress}")
                    self._busy = False
                    return datalist
                
                # write went well so
                # now wait for reply
                try:
                    # NB max return is 75 in 5/2 mode or 159 in 7day mode
                    _LOGGER.debug(f"Reading serial port {self._device_or_ipaddress}")
                    byteread = self._serport.read(159)
                    datalist = list(byteread)

                except serial.SerialException as se:
                    _LOGGER.error(f"Unable to read serial port {self._device_or_ipaddress}: {se}")
                    self._serport.close()
                    self._serport = None
                self._busy = False
            else:
                _LOGGER.debug(f"Serial port {self._device_or_ipaddress} has been created but is not open, resetting...")
                self._serport = None

        if len(datalist) < 1:
            _LOGGER.debug(f"No response from {self._device_or_ipaddress}")
        else:
            _LOGGER.debug(f"Received from {self._device_or_ipaddress}: {datalist}")
        return datalist

    def name(self) -> str:
        return self._name

    def disconnect(self):
        if self._serport is not None:
            self._serport.close()
            self._serport = None
            _LOGGER.info(f"Closed serial port {self._device_or_ipaddress}")

    def __del__(self):
        self.disconnect()
        
    def registerThermostat(self, thermostat):
        """
        Registers a thermostat with the UH1
        Raises an Exception if there is a problem
        """
        try:
            type(thermostat) == HeatmiserThermostat
            if thermostat.address in self.thermostats.keys():
                raise Exception(f"Unable to register thermostat as address {thermostat.address} as it already exists")
            else:
                self.thermostats[thermostat.address] = thermostat

        except Exception as e:
            raise Exception(f"Unable to register thermostat as is it not a Heatmiser Object: {e}")

    def listThermostats(self):
        return self.thermostats
