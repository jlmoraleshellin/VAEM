__author__ = "Kolev, Milen"
__copyright__ = "Copyright 2021, Festo Life Tech"
__credits__ = [""]
__license__ = "Apache"
__version__ = "0.0.2"
__maintainer__ = "Kolev, Milen"
__email__ = "milen.kolev@festo.com"
__status__ = "Development"

import logging
import struct
import time

from pymodbus.client.sync import ModbusTcpClient as TcpClient

from vaem.dataTypes import VaemConfig
from vaem.vaemHelper import *

readParam = {
    "address": 0,
    "length": 0x07,
}

writeParam = {
    "address": 0,
    "length": 0x07,
}


def _construct_frame(data):
    frame = []
    tmp = struct.pack(
        ">BBHBBQ",
        data["access"],
        data["dataType"],
        data["paramIndex"],
        data["paramSubIndex"],
        data["errorRet"],
        data["transferValue"],
    )

    for i in range(0, len(tmp) - 1, 2):
        frame.append((tmp[i] << 8) + tmp[i + 1])

    return frame


def _deconstruct_frame(frame):
    data = {}
    if frame is not None:
        data["access"] = (frame[0] & 0xFF00) >> 8
        data["dataType"] = frame[0] & 0x00FF
        data["paramIndex"] = frame[1]
        data["paramSubIndex"] = (frame[2] & 0xFF00) >> 8
        data["errorRet"] = frame[2] & 0x00FF
        data["transferValue"] = 0
        for i in range(4):
            data["transferValue"] += frame[len(frame) - 1 - i] << (i * 16)

    return data


class vaemDriver:
    def __init__(self, vaemConfig: VaemConfig, logger: logging = logging):
        self._config = vaemConfig
        self._log = logger
        self._init_done = False

        self.client = TcpClient(host=self._config.ip, port=self._config.port)

        for _ in range(2):
            if self.client.connect():
                break
            else:
                self._log.warning(f"Failed to connect VAEM. Reconnecting attempt: {_}")
            if _ == 1:
                self._log.error(f"Could not connect to VAEM: {self._config}")
                raise ConnectionError(f"Could not connect to VAEM: {self._config}")

        self._log.info(f"Connected to VAEM : {self._config}")
        self._init_done = True
        self._vaem_init()

    def _vaem_init(self):
        data = {}
        frame = []

        if self._init_done:
            # set operating mode
            data["access"] = VaemAccess.Write.value
            data["dataType"] = VaemDataType.UINT8.value
            data["paramIndex"] = VaemIndex.OperatingMode.value
            data["paramSubIndex"] = 0
            data["errorRet"] = 0
            data["transferValue"] = VaemOperatingMode.OpMode1.value
            frame = _construct_frame(data)
            self._transfer(frame)

            # clear errors
            data["access"] = VaemAccess.Write.value
            data["dataType"] = VaemDataType.UINT16.value
            data["paramIndex"] = VaemIndex.ControlWord.value
            data["transferValue"] = VaemControlWords.ResetErrors.value
            frame = _construct_frame(data)
            self._transfer(frame)
        else:
            self._log.warning("No VAEM Connected!! CANNOT INITIALIZE")

    def save_settings(self):
        data = {}
        frame = []
        if self._init_done:
            # save settings
            data["access"] = VaemAccess.Write.value
            data["dataType"] = VaemDataType.UINT32.value
            data["paramIndex"] = VaemIndex.SaveParameters.value
            data["paramSubIndex"] = 0
            data["errorRet"] = 0
            data["transferValue"] = 99999
            frame = _construct_frame(data)
            self._transfer(frame)
        else:
            self._log.warning("No VAEM Connected!!")

    # read write oppeartion is constant and custom modbus is implemented on top
    def _transfer(self, writeData):
        data = 0
        try:
            data = self.client.readwrite_registers(
                read_address=readParam["address"],
                read_count=readParam["length"],
                write_address=writeParam["address"],
                write_registers=writeData,
                unit=self._config.slave_id,
            )
            return data.registers
        except Exception as e:
            self._log.error(f"Something went wrong with read opperation VAEM : {e}")

    def select_valve(self, valve_id: int):
        """Selects one valve in the VAEM.
        According to VAEM Logic all selected valves can be opened,
        others cannot with open command

        @param: valve_id - the id of the valve to select

        raises:
            ValueError - raised if the valve id is not supported
        """
        data = {}
        if self._init_done:
            if valve_id in range(0, 8):
                # get currently selected valves
                data = get_transfer_value(
                    VaemIndex.SelectValve,
                    vaemValveIndex[valve_id + 1],
                    VaemAccess.Read.value,
                    **{},
                )
                frame = _construct_frame(data)
                resp = self._transfer(frame)
                # select new valve
                data = get_transfer_value(
                    VaemIndex.SelectValve,
                    vaemValveIndex[valve_id + 1]
                    | _deconstruct_frame(resp)["transferValue"],
                    VaemAccess.Write.value,
                    **{},
                )
                frame = _construct_frame(data)
                self._transfer(frame)
            else:
                self._log.error(
                    "opening time must be in range 0-2000 and valve_id -> 0-8"
                )
                raise ValueError
        else:
            self._log.warning("No VAEM Connected!!")

    def deselect_valve(self, valve_id: int):
        """Deselects one valve in the VAEM.
        According to VAEM Logic all selected valves can be opened,
        others cannot with open command

        @param: valve_id - the id of the valve to select. valid numbers are from 1 to 8

        raises:
            ValueError - raised if the valve id is not supported
        """
        pass
        data = {}
        if self._init_done:
            if valve_id in range(0, 8):
                # get currently selected valves
                data = get_transfer_value(
                    VaemIndex.SelectValve,
                    vaemValveIndex[valve_id + 1],
                    VaemAccess.Read.value,
                    **{},
                )
                frame = _construct_frame(data)
                resp = self._transfer(frame)
                # deselect new valve
                data = get_transfer_value(
                    VaemIndex.SelectValve,
                    _deconstruct_frame(resp)["transferValue"]
                    & (~(vaemValveIndex[valve_id + 1])),
                    VaemAccess.Write.value,
                    **{},
                )
                frame = _construct_frame(data)
                self._transfer(frame)
            else:
                self._log.error(
                    "opening time must be in range 0-2000 and valve_id -> 1-8"
                )
                raise ValueError
        else:
            self._log.warning("No VAEM Connected!!")

    def select_valves(self, states: list[int]):
        """Select multiple valves at once by specifying states for all valves. See documentation on how to open multiple valves.

        param: valve_states - list of 8 values (0 or 1) representing valve states
                         from left to right (valve 1 is first element, valve 8 is last)"""

        # Ensure there are 8 states
        if len(states) != 8:
            self._log.error("Must provide 8 valve states")
            return

        # Reverse the list to match controller's right-to-left bit ordering
        reversed_states = states.copy()
        reversed_states.reverse()
        # Convert the reversed list to a binary string, then to decimal
        binary_string = "".join(str(state) for state in reversed_states)
        decimal_code = int(binary_string, 2)

        data = {}
        if self._init_done:
            # Select valves by directly writing the binary pattern
            data = get_transfer_value(
                VaemIndex.SelectValve, decimal_code, VaemAccess.Write.value, **{}
            )
            frame = _construct_frame(data)
            self._transfer(frame)
        else:
            self._log.warning("No VAEM Connected!!")

    def configure_valves(self, valve_id: int, opening_time: int):
        """Configure the valves with pre selected parameters"""
        data = {}
        if self._init_done:
            if (opening_time in range(0, 4294967296)) and (valve_id in range(0, 8)):
                data = get_transfer_value(
                    VaemIndex.ResponseTime,
                    valve_id,
                    VaemAccess.Write.value,
                    **{"ResponseTime": int(opening_time)},
                )
                frame = _construct_frame(data)
                self._transfer(frame)
            else:
                self._log.error(
                    "opening time must be in range 0-2000 and valve_id -> 1-8"
                )
                raise ValueError
        else:
            self._log.warning("No VAEM Connected!!")

    def open_valve(self):
        """
        Start all valves that are selected
        """
        data = {}
        if self._init_done:
            # save settings
            data["access"] = VaemAccess.Write.value
            data["dataType"] = VaemDataType.UINT16.value
            data["paramIndex"] = VaemIndex.ControlWord.value
            data["paramSubIndex"] = 0
            data["errorRet"] = 0
            data["transferValue"] = VaemControlWords.StartValves.value
            frame = _construct_frame(data)
            self._transfer(frame)
            
            # reset the control word
            data["access"] = VaemAccess.Write.value
            data["dataType"] = VaemDataType.UINT16.value
            data["paramIndex"] = VaemIndex.ControlWord.value
            data["paramSubIndex"] = 0
            data["errorRet"] = 0
            data["transferValue"] = 0
            frame = _construct_frame(data)
            self._transfer(frame)
        else:
            self._log.warning("No VAEM Connected!!")

    def close_valve(self):
        data = {}
        if self._init_done:
            # save settings
            data["access"] = VaemAccess.Write.value
            data["dataType"] = VaemDataType.UINT16.value
            data["paramIndex"] = VaemIndex.ControlWord.value
            data["paramSubIndex"] = 0
            data["errorRet"] = 0
            data["transferValue"] = VaemControlWords.StopValves.value

            frame = _construct_frame(data)
            self._transfer(frame)
        else:
            self._log.warning("No VAEM Connected!!")

    def read_valves_state(self):
        data = {}
        if self._init_done:
            # get currently selected valves
            data = get_transfer_value(
                VaemIndex.SelectValve,
                0,
                VaemAccess.Read.value,
                **{},
            )
            frame = _construct_frame(data)
            resp = self._transfer(frame)

            # Get states from response
            decimal_code = _deconstruct_frame(resp)["transferValue"]

            # Convert to binary and ensure it's 8 bits (pad with leading zeros if needed)
            binary_string = format(decimal_code, '08b')
            # Convert to list of integers and reverse to match user-expected order
            states = [int(bit) for bit in binary_string]
            states.reverse()

            return states

        else:
            self._log.warning("No VAEM Connected!!")
            return None

    def read_status(self):
        """
        Read the status of the VAEM
        The status is return as a dictionary with the following keys:
        -> status: 1 if more than 1 valve is active
        -> error: 1 if error in valves is present
        """
        data = {}
        if self._init_done:
            # save settings
            data["access"] = VaemAccess.Read.value
            data["dataType"] = VaemDataType.UINT16.value
            data["paramIndex"] = VaemIndex.StatusWord.value
            data["paramSubIndex"] = 0
            data["errorRet"] = 0
            data["transferValue"] = 0

            frame = _construct_frame(data)
            resp = self._transfer(frame)
            #self._log.info(get_status(_deconstruct_frame(resp)["transferValue"]))

            return get_status(_deconstruct_frame(resp)["transferValue"])
        else:
            self._log.warning("No VAEM Connected!!")
            return ""
        
    def wait_for_readiness(self, timeout=10.0):
        """
        Wait for the device to be ready with a timeout.
        """
        start_time = time.time()
        
        while True:
            # Check if timeout has been exceeded
            if time.time() - start_time > timeout:
                self._log.warning(f"Timeout waiting for device readiness after {timeout} seconds")
                return False
                
            readiness = self.read_status()["Readiness"]
            if readiness == 0:
                time.sleep(0.1)
                print(readiness)
                pass
            else:
                return True

    def clear_error(self):
        """
        If any error occurs in valve opening, must be cleared with this opperation.
        """
        if self._init_done:
            data = {}
            data["access"] = VaemAccess.Write.value
            data["dataType"] = VaemDataType.UINT16.value
            data["paramIndex"] = VaemIndex.ControlWord.value
            data["paramSubIndex"] = 0
            data["errorRet"] = 0
            data["transferValue"] = VaemControlWords.ResetErrors.value
            frame = _construct_frame(data)
            self._transfer(frame)
        else:
            self._log.warning("No VAEM Connected!!")
