import logging
from writepropertydata import WritePropertyData
from utils import check_param
from crc16 import CRC16, BYTEMASK

HMV3_ID = 3
FUNC_READ = 0
FUNC_WRITE = 1
RW_LENGTH_ALL = 0xffff
RW_MASTER_ADDRESS = 0x81
DCB_OFFSET = 9
HEATMISER = 'heatmiser'


logging.basicConfig(level=logging.ERROR)
_LOGGER = logging.getLogger(__name__)


class HeatmiserThermostat(object):
    """
    Object to contain a Heatmiser thermostat
    Contains all known ro and rw properties
    Allows changing of writeable properties
    """

    WEEKDAYS = {1:"Mon", 2:"Tue", 3:"Wed", 4:"Thu", 5:"Fri", 6:"Sat", 7:"Sun"}
    PRT = "PRT"
    PRT_E = "PRT-E"
    DT = "DT"
    DT_E = "DT-E"
    PRTHW = "PRTHW"
    TM1 = "TM1"
    HC_EN = "HC-EN"
    MODELS = {0: DT, 1: DT_E, 2: PRT, 3: PRT_E, 4: PRTHW, 5: TM1, 7: HC_EN}
    read_properties = {}
    write_properties = {}


    def __init__(self, address: int, model: str, hub, name: str = ""):
        """
        Raises an Exception if the thermostat can't be registered
        """
        _LOGGER.info(f"Creating thermostat '{name}' ({model}) at address {address}...")
        self.address = address
        self.model = model
        self._hub = hub
        self.name = name

        self._dcb_frame = []
        hub.registerThermostat(self)
        # Creation and registration successful so read the thermostat's DCB
        self.read_properties["Model"] = model
        self.read_thermostat()
        if model in [self.PRT, self.PRT_E, self.DT, self.DT_E, self.PRTHW]:
            self.write_properties["frost_protect_temp"] = WritePropertyData("Frost Protect Temp", 17, 7, 17)
            self.write_properties["room_target_temp"] = WritePropertyData("Room Target Temp", 18, 5, 35)
            self.write_properties["floor_max_temp"] = WritePropertyData("Floor Max Temp", 19, 20, 45)
            self.write_properties["display_state"] = WritePropertyData("Display State", 21, options={"off": 0,"on": 1})
            self.write_properties["key"] = WritePropertyData("Key", 22, options={"unlocked": 0,"locked": 1})
            self.write_properties["run_mode"] = WritePropertyData("Run Mode", 23, options={"heating": 0, "frost protect": 1})
            # Holiday Hours max, 2385 is 99 (+4) hours. Thermostat seems to add 4 hours...
            self.write_properties["holiday_hours"] = WritePropertyData("Holiday Hours", dcb_offset=24, min=0, max=2385, twobyte=True)
            # Temp Hold Minutes max, 5970 is 99:30
            self.write_properties["temp_hold_minutes"] = WritePropertyData("Temp Hold Minutes", dcb_offset=26, min=0, max=5970, twobyte=True)
            # offset = self._dateTime_offset(model)
            # if offset is not None:
            #     self.write_properties["Current Day"] = WritePropertyData("Current Day", offset, options=self.WEEKDAYS)
            #     self.write_properties["Current Time"] = WritePropertyData("Current Time", offset + 1, isTime=True)

    # def _check_param(self, module :str , function : str, param_name : str, param_type : type, param):
    #     if type(param) != param_type:
    #         raise ValueError(f"{module}.{function} parameter error: {param_name} must be a {param_type}, {type(param)} supplied")

    @staticmethod
    def getThermostatType(hub, address: int) -> str:
        """Returns the thermostat type (PRT-N etc) by interrogating the network at address 'address'
        or False if there is no thermostat at the address"""
        msg = HeatmiserThermostat.assemble_message(address, FUNC_READ, 0, [0])
        packet = hub.send_msg(msg)
        if packet is False:
            return False
        if len(packet) < 1:
            _LOGGER.debug(f"Thermostat reply error: no reply")
            return False
        elif len(packet) < 7:
            _LOGGER.error(f"Thermostat reply error: message too short needed >=7 bytes, received {len(packet)} bytes")
            return False
        checksum = packet[len(packet) - 2:]
        rxmsg = packet[:len(packet) - 2]
        crc = CRC16()   # Initialises the CRC
        expectedchecksum = crc.run(rxmsg)
        if expectedchecksum != checksum:
            # This typically happens when the thermostat loses power while commected to the RS485 bus
            _LOGGER.error("Thermostat reply error: CRC is incorrect")
            return False

        # Response passes checksum so check the contents
        return HeatmiserThermostat._decode_byte(packet[4 + DCB_OFFSET], HeatmiserThermostat.MODELS)

    @staticmethod
    def assemble_message(address: int, function, start: int, payload : list) -> list:
        """Forms a message payload, including CRC. Returns a list"""
        check_param("payload", list, payload)

        start_low = (start & BYTEMASK)
        start_high = (start >> 8) & BYTEMASK
        if function == FUNC_READ:
            payload_length = 0
            length_low = (RW_LENGTH_ALL & BYTEMASK)
            length_high = (RW_LENGTH_ALL >> 8) & BYTEMASK
        else:
            payload_length = len(payload)
            length_low = (payload_length & BYTEMASK)
            length_high = (payload_length >> 8) & BYTEMASK
        msg = [
            address,
            10 + payload_length,
            RW_MASTER_ADDRESS,
            function,
            start_low,
            start_high,
            length_low,
            length_high
        ]
        if function == FUNC_WRITE:
            msg = msg + payload
#            type(msg) #What did this do?
        crc = CRC16()
        msg = msg + crc.run(msg)
        return msg

    def _send_message(self, dcb_address: int, command_data : list, read_thermostat: bool = True):
        """
        Composes a message for the thermostat, sends it via the hub, validates its response
        Returns the thermostat data as a list if the response is valid
        dcb_address: the offset into the dcb to which command_data relates
        command_data: list of bytes to send
        Returns True if successful
        Returns False if either no response was received or the response was invalid
        """
        check_param("command_data", list, command_data)
        # Read commands obtain all the available data from the thermostat
        # Write commands respond with a CRC only (7 bytes in total)
        read_write_command = FUNC_READ if read_thermostat else FUNC_WRITE

        if read_thermostat:
            self.read_properties = {}

        msg = HeatmiserThermostat.assemble_message(self.address, read_write_command, dcb_address, command_data)
        packet = self._hub.send_msg(msg)
        if packet is False:
            return False
        if len(packet) < 1:
            _LOGGER.error(f"Thermostat '{self.name}' at {self.address} no reply")
            return False
        elif len(packet) < 7:
            _LOGGER.error(f"Thermostat reply error: message too short needed >=7 bytes, received {len(packet)} bytes")
            return False
        
        checksum = packet[len(packet) - 2:]
        rxmsg = packet[:len(packet) - 2]
        crc = CRC16()   # Initialises the CRC
        expectedchecksum = crc.run(rxmsg)
        if expectedchecksum != checksum:
            # This typically happens when the thermostat loses power while commected to the RS485 bus
            _LOGGER.error("Thermostat reply error: CRC is incorrect, attempting to reinitialise serial comms")
            self._hub.disconnect()
            return False

        # Response passes checksum so check the contents
        dest_addr = packet[0]
        frame_len = (packet[2] << 8) | packet[1]
        source_addr = packet[3]
        func_code = packet[4]

        if dest_addr != RW_MASTER_ADDRESS:
            _LOGGER.error(f"Thermostat reply error: desitnation address ({dest_addr}) does not match thermostat address ({RW_MASTER_ADDRESS})")
            return False

        if source_addr != self.address:
            _LOGGER.error(f"Thermostat reply error: message source address ({source_addr}) does not match source ({self.address})")
            return False

        rw_opts = {FUNC_READ: "read", FUNC_WRITE: "write"}
        if func_code not in rw_opts.keys():# != FUNC_WRITE and func_code != FUNC_READ:
            _LOGGER.error(f"Thermostat reply error: reply function ({func_code}) must be either {FUNC_READ} (read), or {FUNC_WRITE} (write)")
            return False

        if func_code != read_write_command:
            req_func = rw_opts[read_write_command]
            resp_func = rw_opts[func_code]
            _LOGGER.error(f"Thermostat reply error: request was for {req_func}, response was for {resp_func} ")
            return False

        if func_code == FUNC_WRITE and frame_len != 7:
            # Reply to Write is always 7 long
            _LOGGER.error(f"Thermostat reply error: request was for a write but the response length was {frame_len} not 7")
            return False

        if len(packet) != frame_len:
            _LOGGER.error(f"Thermostat reply error: response indicated {frame_len} bytes but {len(packet)} were received")
            return False
        
        if func_code == FUNC_READ:
            reported_model = packet[13]
            if self.MODELS[reported_model] != self.model:
                _LOGGER.error(f"Thermostat registered as {self.model} but thermostat is {self.MODELS[reported_model]}")
                return False
        # All checks passed
        if read_thermostat:
            self._dcb_frame = packet
            self.read_properties["Vendor"] = HeatmiserThermostat._decode_byte(packet[2 + DCB_OFFSET], { 0: "Heatmiser", 1: "OEM"})
            self.read_properties["Version"] = packet[3 + DCB_OFFSET] & 0x7F
            self.read_properties["Floor limiting"] = HeatmiserThermostat._decode_byte(packet[3 + DCB_OFFSET] & 0x80, { 0: "Off", 0x80: "On"}) # bit 7
            self.read_properties["Type"] = HeatmiserThermostat._decode_byte(packet[4 + DCB_OFFSET], self.MODELS)
            # device specific from here on
            
            if self.model == self.TM1:
                # TODO
                pass
            else:
                self.read_properties["Units"] = HeatmiserThermostat._decode_byte(packet[5 + DCB_OFFSET], { 0: "°C", 1: "°F"})
                if self.model in [self.HC_EN]:
                    # TODO
                    pass
                else:
                    #DT DT-E PRT PRT-E PRTHW
                    self.read_properties["Differential"] = packet[6 + DCB_OFFSET]
                    self.read_properties["Frost Protection"] = HeatmiserThermostat._decode_byte(packet[7 + DCB_OFFSET], {0: "Not active", 1: "Active"})
                    self.read_properties["Calibration Offset"] = (packet[8 + DCB_OFFSET] << 8) | packet[9 + DCB_OFFSET]
                    self.read_properties["Bus Address"] = str(packet[11 + DCB_OFFSET])
                    sensors = {0: "Built in"}
                    if self.model != "PRTHW": #DT DT-E PRT PRT-E
                        sensors = sensors | {1: "Remote", 2: "Floor", 3: "Built in + Floor", 4: "Remote + Floor"}
                    self.read_properties["Sensor Type"] = HeatmiserThermostat._decode_byte(packet[13 + DCB_OFFSET], sensors)
                    self.read_properties["Optimum Start"] = packet[14 + DCB_OFFSET]
                    self.read_properties["Rate of Change"] = packet[15 + DCB_OFFSET]
                    self.read_properties["Timer Mode"] = HeatmiserThermostat._decode_byte(packet[16 + DCB_OFFSET], { 0: "wk-day/wk-end", 1: "7 day"})
                    self.read_properties["Frost Protect Temp"] = packet[17 + DCB_OFFSET]
                    self.read_properties["Room Target Temp"] = packet[18 + DCB_OFFSET]
                    self.read_properties["Floor Max Temp"] = packet[19 + DCB_OFFSET]
                    self.read_properties["Floor Max limit"] = HeatmiserThermostat._decode_byte(packet[20 + DCB_OFFSET], { 0: "disabled", 1: "enabled"})
                    self.read_properties["Display State"] = HeatmiserThermostat._decode_byte(packet[21 + DCB_OFFSET], { 0: "off", 1: "on"})
                    self.read_properties["Key"] = HeatmiserThermostat._decode_byte(packet[22 + DCB_OFFSET], { 0: "unlocked", 1: "locked"})
                    self.read_properties["Run Mode"] = HeatmiserThermostat._decode_byte(packet[23 + DCB_OFFSET], { 0: "heating", 1: "frost protect"})
                    self.read_properties["Holiday Hours"] = packet[25 + DCB_OFFSET] + (packet[24 + DCB_OFFSET] << 8)
                    self.read_properties["Temp Hold Minutes"] = packet[27 + DCB_OFFSET] + (packet[26 + DCB_OFFSET] << 8)
                    self.read_properties["Remote Sensor Temp"] = (str(packet[29 + DCB_OFFSET] / 10) if packet[29 + DCB_OFFSET] != 0xff else "not connected")
                    self.read_properties["Floor Sensor Temp"] = (str(packet[31 + DCB_OFFSET] / 10) if packet[31 + DCB_OFFSET] != 0xff else "not connected")
                    self.read_properties["Built-in Sensor Temp"] = (str(packet[33 + DCB_OFFSET] / 10) if packet[33 + DCB_OFFSET] != 0xff else "not connected")
                    self.read_properties["Error"] = HeatmiserThermostat._decode_byte(packet[34 + DCB_OFFSET], {0: "none", 0xE0: "built-in sensor", 0xE1: "floor sensor", 0xE2: "remote sensor"})
                    self.read_properties["Heating State"] = HeatmiserThermostat._decode_byte(packet[35 + DCB_OFFSET], {0: "no heat", 1: "heat"})
                    offset = self._dateTime_offset(self.model)
                    if offset is not None:
                        if packet[offset] in self.WEEKDAYS:
                            self.read_properties["Current Day"] = self.WEEKDAYS[packet[offset]]
                        else:
                            self.read_properties["Current Day"] = "unknown"
                        self.read_properties["Current Time"] = f"{packet[offset + 1]:02d}:{packet[offset + 2]:02d}:{packet[offset + 3]:02d}"
                    
                    weekdayWeekendOffset = self._weekdayWeekendOffset(self.model)
                    if weekdayWeekendOffset is not None:
                        self._addTimeTempProperties("Weekday", packet, weekdayWeekendOffset)
                        self._addTimeTempProperties("Weekend", packet, weekdayWeekendOffset + 12)
                    if self.model in [self.PRT, self.PRT_E] and self.read_properties["Timer Mode"] == "7 day":
                        offset = 64 + DCB_OFFSET
                        for dow in self.WEEKDAYS:
                            offset = self._addTimeTempProperties(self.WEEKDAYS[dow], packet, offset)
                    # TODO PRTHW & HC-EN
                
            _LOGGER.debug(self.read_properties)
        else:
            # decode response from a write command contains no data
            pass
        return True
    
    def _dateTime_offset(self, model):
        """Returns the byte offset within the dcb of the date and time data
        or None if the thermostat does not support date/time"""
        offsets = {self.PRT: 36, self.PRT_E: 36, self.PRTHW: 37, self.TM1:15}
        if model in offsets:
            return offsets[model] + DCB_OFFSET
        else:
            return None

    def _weekdayWeekendOffset(self, model : str):
        """Returns the byte offset within the dcb of the weekday/weekend data
        or None if the thermostat does not support weekday/weekend"""
        offsets = {self.PRT: 40, self.PRT_E: 40, self.PRTHW: 41, self.HC_EN: 45}#, self.TM1: 19}
        if model in offsets:
            return offsets[model] + DCB_OFFSET
        else:
            return None

    def _addTimeOnOffProperties(self, name : str, packet : list, offset : int):
        item = offset
        for time_slot in range(1, 4):
            self.read_properties[f"{name} Time{time_slot} On"] = f"{packet[item]:02d}:{packet[item + 1]:02d}"
            self.read_properties[f"{name} Time{time_slot} Off"] = f"{packet[item + 2]:02d}:{packet[item + 3]:02d}"
            item +=4

    def _addTimeTempProperties(self, name : str, packet : list, offset : int):
        item = offset
        periods = ["Wake", "Leave", "Return", "Sleep"]
        for period in periods:
            self.read_properties[f"{name} {period} Time"] = f"{packet[item]:02d}:{packet[item + 1]:02d}"
            self.read_properties[f"{name} {period} Temp"] = packet[item + 2]
            item +=3
        return item

    def connected(self) -> bool:
        """
        Returns True if the thermostat is online and connected (able to be read)
        """
        return len(self._dcb_frame) > 0

    @staticmethod
    def _decode_byte(byte, options):
        """Returns a string from a set of options depending on the value of byte
        e.g. _decode_byte(1, { 0: "Heatmiser", 1: "OEM"}) returns OEM"""
        if byte in options:
            return options[byte]
        else:
            return f"unknown ({byte})"

    def read_thermostat(self):
        """
        Reads the data from the thermostat
        Returns True if the read was successful
        """
        _LOGGER.debug(f"Reading thermostat '{self.name}' ({self.model}) at address {self.address}")
        try:
            return self._send_message(0, [0], True)
        except Exception as ex:
            _LOGGER.error(f"read_thermostat error: {ex}")

    def update_thermostat(self, property : WritePropertyData, value):
        """
        Updates the thermostat for the property defined in "property" with value "value"
        Returns True if the update was successful
        Returns False if "value" is invalid or the "property" does not exist
        """
        check_param("property", WritePropertyData, property)
        if (str(value)) == '':
            # discard without error
            return True
        data = None
        if property.options is not None:
            if value in property.options:
                data = [property.options[value]]
            else:
                _LOGGER.error(f"Error sending {value} to '{property.name}', value not in {property.options}")
        elif property.isTime:
            pass
        else:
            value = int(float(value)) # maybe float?
            if property.max is not None:
                if value > property.max:
                    _LOGGER.error(f"Error sending {value} to '{property.name}', Value must be >= {property.max}")
            if property.min is not None:
                if value < property.min:
                    _LOGGER.error(f"Error sending {value} to '{property.name}', Value must be <= {property.min}")
            
            if property.twobyte:
                data = [value & 0xFF, (value >> 8) & 0xFF]
            else:
                data = [value]
        if data is not None:
            model = self.read_property("Type")
            if self._send_message(property.dcb_offset, data, False):
                _LOGGER.info(f"Sent '{property.name}' ({value} as {data}) to thermostat '{self.name}' ({model}) at address {self.address}")
            else:
                _LOGGER.error(f"Error sending '{property.name}' ({value} as {data}) to thermostat '{self.name}' ({model}) at address {self.address}")
                return False
            return True
        else:
            return False

    def _dcb_item(self, index):
        """returns the value in the dcb at index 'index' or None if 'index' is out of range
        N.B the data is stored in _dcb_frame which includes all the headers before the dcb starts"""
        if len(self._dcb_frame) - DCB_OFFSET > index:
            return self._dcb_frame[index + DCB_OFFSET]
        else:
            return None
    
    def read_property(self, name : str):
        """
        Returns the value of a "read" property or None if unknown
        """
        if name in self.read_properties:
            return self.read_properties[name]
        else:
            return None

#     def _item_string(self, item_index, options):
#         value = self._dcb_item(item_index)
#         # if value is None:
#         #     return "Unknown"
#         if value in options:
#             return options[value]
#         else:
#             return None # UNKNOWN



# Write functions
    def set_thermostat_time(self, day_of_week, hour, minute, second):
        """
        NOT TESTED as it is unclear whether the day of week and time of day have to be sent separately or together
        TODO
        """
        if self.connected() is not True:
            _LOGGER.error(f"Unable to set thermostat {self.address} time to {day_of_week} {hour}:{minute}:{second} as the thermostat is not connected")
            return False
        version = self._dcb_item(3) & 0x7F
        if version <= 19:
            # This needs more data. All I know is that V19 does not support this
            _LOGGER.error(f"Unable to set thermostat {self.address} time to {day_of_week} {hour}:{minute}:{second} as the thermostat as the thermostat version {version} is too low")
            return False

        thermostat_type = self.read_property("Type")
        all_ok = True
        if thermostat_type in [self.DT, self.DT_E]:
            _LOGGER.error(f"Unable to set thermostat {self.address} time as {self.MODELS[thermostat_type]} ({thermostat_type}) does not support it")
            return False
        elif thermostat_type in [self.PRT, self.PRT_E]:
            dcb_offset = 36
        elif thermostat_type == self.PRTHW:
            dcb_offset = 37
        elif thermostat_type == self.TM1:
            dcb_offset = 15
        else:
            _LOGGER.error(f"Unable to set thermostat {self.address} time as the model number ({thermostat_type}) is not recognised")
            return False
        day_of_week = day_of_week[0:3].title()
        try:
            week_day_no = next(week_day_no for week_day_no, value in self.WEEKDAYS.items() if value == day_of_week)
        except Exception as ex:
            _LOGGER.error(f"Unable to set thermostat {self.address} time as day of week ({day_of_week}) is not recognised")
            return False

        hour = max(0, min(23, int(hour)))
        minute = max(0, min(59, int(minute)))
        second = max(0, min(59, int(second)))
        payload = [week_day_no, hour, minute, second]

        msg = f"et thermostat {self.address} time to {day_of_week} (day {week_day_no}) {hour:02d}:{minute:02d}:{second:02d} at dcb[{dcb_offset}]"
        if self._send_message(dcb_offset, payload, False):
        #msgToSend = HeatmiserThermostat.assemble_message(self.address, FUNC_WRITE, dcb_offset, payload)
        #if self._hub.send_msg(msgToSend):
            _LOGGER.debug("S" + msg)
        else:
            _LOGGER.error(f"Unable to s{msg} using {payload}")
        all_ok = False
        return all_ok

    # def _set_limited_int_value(self, dcb_index, value, min_value, max_value, name):
    #     """
    #     Helper to limit the (int) value to a range and update the thermostat with the value
    #     Returns True if successful
    #     N.B. this does not update the current dcb with the updated value
    #     This will happen after the next call to update_from_thermostat
    #     """
    #     if self.connected() is not True:
    #         _LOGGER.error(f"Unable to set thermostat {self.address} {name} to {value} as the thermostat is not connected")
    #         return False

    #     value = int(value)
    #     if max_value < value < min_value:
    #         limited_value = max(min_value, min(max_value, value))
    #         _LOGGER.warning(f"Limited the setting of {name} for thermostat {self.address} from {value} to {limited_value} as it is outside {min_value} to {max_value}")
    #         value = limited_value
    #     datal = self._send_message(dcb_index, value, False)
    #     ok = (len(datal) == 7)
    #     if ok:
    #         _LOGGER.info(f"Set thermostat {self.address} {name} to {value}")
    #     else:
    #         _LOGGER.error(f"Unable to set thermostat {self.address} {name} to {value}")
    #     return ok
