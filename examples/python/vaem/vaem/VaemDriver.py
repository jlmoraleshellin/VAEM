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

from pymodbus.client import ModbusTcpClient as TcpClient

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

error_codes = {
    0: "Ready for operation, no error",
    34: "Invalid index",
    35: "Invalid subindex",
    36: "Read request cannot be processed",
    37: "Write request cannot be processed",
    41: "Specified value falls below the minimum value",
    42: "The specified value exceeds the maximum value",
    43: "Incorrect transfer value",
    44: "Data type incorrect",
    93: "General syntax error",
    94: "Syntax error index (variable x)",
    95: "Syntax error subindex (variable y)",
    96: "Syntax error value",
    97: "Command execution aborted",
}


def handle_error_response(func):
    def wrapper(self: vaemDriver, *args, **kwargs):
        if self._init_done:
            result = func(self, *args, **kwargs)

            if result is None:
                return result

            error = result["errorRet"]
            if error != 0:
                self._log.error(f"{error_codes[error]}")
                self.clear_error()

            return result
        else:
            self._log.warning("No VAEM Connected")

    return wrapper

def _construct_registers(data: dict):
    register = []
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
        register.append((tmp[i] << 8) + tmp[i + 1])

    return register

def _deconstruct_registers(registers: list):
    data = {}
    if registers is not None:
        data["access"] = (registers[0] & 0xFF00) >> 8
        data["dataType"] = registers[0] & 0x00FF
        data["paramIndex"] = registers[1]
        data["paramSubIndex"] = (registers[2] & 0xFF00) >> 8
        data["errorRet"] = registers[2] & 0x00FF
        data["transferValue"] = 0
        for i in range(4):
            data["transferValue"] += registers[len(registers) - 1 - i] << (i * 16)

    return data


class vaemDriver:
    def __init__(self, vaemConfig: VaemConfig, logger=logging.getLogger("vaem")):
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
        if self._init_done:
            # set operating mode
            data["access"] = VaemAccess.Write.value
            data["dataType"] = VaemDataType.UINT8.value
            data["paramIndex"] = VaemIndex.OperatingMode.value
            data["paramSubIndex"] = 0
            data["errorRet"] = 0
            data["transferValue"] = VaemOperatingMode.OpMode1.value
            register = _construct_registers(data)
            self._transfer(register)

            # clear errors
            data["access"] = VaemAccess.Write.value
            data["dataType"] = VaemDataType.UINT16.value
            data["paramIndex"] = VaemIndex.ControlWord.value
            data["transferValue"] = VaemControlWords.ResetErrors.value
            register = _construct_registers(data)
            self._transfer(register)
        else:
            self._log.warning("No VAEM Connected!! CANNOT INITIALIZE")

    # read write oppeartion is constant and custom modbus is implemented on top
    def _transfer(self, writeData: list) -> list:
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
            return []

    @handle_error_response
    def save_settings(self) -> dict:
        data = {}
        register = []

        data["access"] = VaemAccess.Write.value
        data["dataType"] = VaemDataType.UINT32.value
        data["paramIndex"] = VaemIndex.SaveParameters.value
        data["paramSubIndex"] = 0
        data["errorRet"] = 0
        data["transferValue"] = 99999
        register = _construct_registers(data)
        resp = self._transfer(register)

        return _deconstruct_registers(resp)

    @handle_error_response
    def select_valve(self, valve_id: int):
        """Selects one valve in the VAEM.
        According to VAEM Logic all selected valves can be opened

        @param: valve_id - the id of the valve to select from 1 to 8

        raises:
            ValueError - raised if the valve id is not supported
        """
        data = {}
        if valve_id in range(1, 9):
            # get currently selected valves
            data = get_transfer_value(
                VaemIndex.SelectValve,
                vaemValveIndex[valve_id],
                VaemAccess.Read.value,
                **{},
            )
            register = _construct_registers(data)
            resp = self._transfer(register)
            # select new valve
            data = get_transfer_value(
                VaemIndex.SelectValve,
                vaemValveIndex[valve_id] | _deconstruct_registers(resp)["transferValue"],
                VaemAccess.Write.value,
                **{},
            )
            register = _construct_registers(data)
            resp = self._transfer(register)

            return _deconstruct_registers(resp)
        else:
            self._log.error("valve_id must be between 1-8")
            raise ValueError

    @handle_error_response
    def deselect_valve(self, valve_id: int) -> dict:
        """Deselects one valve in the VAEM.

        @param: valve_id - the id of the valve to select. valid numbers are from 1 to 8

        raises:
            ValueError - raised if the valve id is not supported
        """
        data = {}
        if valve_id in range(1, 9):
            # get currently selected valves
            data = get_transfer_value(
                VaemIndex.SelectValve,
                vaemValveIndex[valve_id],
                VaemAccess.Read.value,
                **{},
            )
            register = _construct_registers(data)
            resp = self._transfer(register)
            # deselect new valve
            data = get_transfer_value(
                VaemIndex.SelectValve,
                _deconstruct_registers(resp)["transferValue"]
                & (~(vaemValveIndex[valve_id])),
                VaemAccess.Write.value,
                **{},
            )
            register = _construct_registers(data)
            resp = self._transfer(register)

            return _deconstruct_registers(resp)
        else:
            self._log.error("valve_id must be between 1-8")
            raise ValueError

    @handle_error_response
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

        # Select valves by directly writing the binary pattern
        data = get_transfer_value(
            VaemIndex.SelectValve, decimal_code, VaemAccess.Write.value, **{}
        )
        register = _construct_registers(data)
        resp = self._transfer(register)

        return _deconstruct_registers(resp)

    # TODO refactor this method to handle errors individually
    def configure_valves(self, valve_id, settings: dict[VaemIndex, int]):
        """Configure settings for a specific valve. This method allows setting various
        parameters for a given valve.

        Args:
            valve_id: The identifier of the valve to configure
            settings (dict[VaemIndex, int]): Dictionary mapping valve parameters to their values.
                Keys are VaemIndex enum members and values are the parameter settings.

        Examples:
            >>> driver.configure_valves(1, {VaemIndex.ResponseTime: 100, VaemIndex.InrushCurrent: 50})
        """
        for param, value in settings.items():
            # Check if parameter is actually a setting
            if not hasattr(VaemRanges, param.name):
                raise ValueError(f"VaemIndex {param.name} is not a setting")

            # Check parameter and valve ranges
            if value in range(
                *getattr(VaemRanges, param.name).value
            ) and valve_id in range(1, 9):
                data = get_transfer_value(
                    param,
                    valve_id - 1,  # Valve id starts at 0 for settings
                    VaemAccess.Write.value,
                    **{param.name: int(value)},
                )
                register = _construct_registers(data)
                resp = self._transfer(register)
            else:
                valid_range = getattr(VaemRanges, param.name).value
                raise ValueError(
                    f"{param.name} must be in range {valid_range[0]} - {valid_range[1] - 1} and valve_id -> 1-8"
                )

    @handle_error_response
    def configure_valve_response_time(self, valve_id: int, opening_time: int):
        """Set a specific valve's response time (opening time)"""
        data = {}
        if (opening_time in range(0, (2**32))) and (valve_id in range(1, 9)):
            data = get_transfer_value(
                VaemIndex.ResponseTime,
                valve_id - 1,  # Valve id starts at 0 for settings
                VaemAccess.Write.value,
                **{"ResponseTime": int(opening_time)},
            )
            register = _construct_registers(data)
            resp = self._transfer(register)

            return _deconstruct_registers(resp)
        else:
            self._log.error("opening time must be in range 0-2000 and valve_id -> 1-8")
            raise ValueError

    @handle_error_response
    def configure_valve_inrush_current(self, valve_id: int, inrush_current: int):
        """Set a specific valve's inrush current"""
        data = {}
        if (inrush_current in range(20, 1000)) and (valve_id in range(1, 9)):
            data = get_transfer_value(
                VaemIndex.InrushCurrent,
                valve_id - 1,  # Valve id starts at 0 for settings
                VaemAccess.Write.value,
                **{"InrushCurrent": int(inrush_current)},
            )
            register = _construct_registers(data)
            resp = self._transfer(register)

            return _deconstruct_registers(resp)
        else:
            self._log.error(
                "inrush current must be in range 20-1000 and valve_id -> 1-8"
            )
            raise ValueError

    @handle_error_response
    def read_valve_configuration(self, valve_id, setting: VaemIndex):
        """Read settings for a specific valve. This method allows reading various
        parameters for a given valve.

        Args:
            valve_id: The identifier of the valve to configure
            settings (VaemIndex): VaemIndex settings to read.

        Examples:
            driver.read_valve_configuration(1, VaemIndex.ResponseTime)
        """
        # Check if parameter is actually a setting
        if not hasattr(VaemRanges, setting.name):
            raise ValueError(f"VaemIndex {setting.name} is not a setting")

        data = get_transfer_value(
            setting,
            valve_id - 1,  # Valve id starts at 0 for settings
            VaemAccess.Read.value,
            **{setting.name: 0},
        )
        register = _construct_registers(data)
        resp = self._transfer(register)

        return _deconstruct_registers(resp)

    @handle_error_response
    def start_valves(self):
        """
        Start all valves that are selected
        """
        data = {}
        data["access"] = VaemAccess.Write.value
        data["dataType"] = VaemDataType.UINT16.value
        data["paramIndex"] = VaemIndex.ControlWord.value
        data["paramSubIndex"] = 0
        data["errorRet"] = 0
        data["transferValue"] = VaemControlWords.StartValves.value
        register = _construct_registers(data)
        resp = self._transfer(register)

        return _deconstruct_registers(resp)

    @handle_error_response
    def reset_control_word(self):
        """ "Reset control word"""
        data = {}
        data["access"] = VaemAccess.Write.value
        data["dataType"] = VaemDataType.UINT16.value
        data["paramIndex"] = VaemIndex.ControlWord.value
        data["paramSubIndex"] = 0
        data["errorRet"] = 0
        data["transferValue"] = 0
        register = _construct_registers(data)
        resp = self._transfer(register)

        return _deconstruct_registers(resp)

    def open_valve(self):
        """
        Start all valves that are selected
        """
        self.open_valve()
        # TODO add a buffer
        self.reset_control_word()

    @handle_error_response
    def close_valve(self):
        data = {}
        # save settings
        data["access"] = VaemAccess.Write.value
        data["dataType"] = VaemDataType.UINT16.value
        data["paramIndex"] = VaemIndex.ControlWord.value
        data["paramSubIndex"] = 0
        data["errorRet"] = 0
        data["transferValue"] = VaemControlWords.StopValves.value

        register = _construct_registers(data)
        resp = self._transfer(register)

        return _deconstruct_registers(resp)

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
            register = _construct_registers(data)
            resp = self._transfer(register)

            # Get states from response
            decimal_code = _deconstruct_registers(resp)["transferValue"]

            # Convert to binary and ensure it's 8 bits (pad with leading zeros if needed)
            binary_string = format(decimal_code, "08b")
            # Convert to list of integers and reverse to match user-expected order
            states = [int(bit) for bit in binary_string]
            states.reverse()

            return states

        else:
            self._log.warning("No VAEM Connected!!")
            return None

    @handle_error_response
    def _read_status_word(self):
        """
        Read the statusword
        The status is return as a dictionary with the following keys:
        -> status: 1 if more than 1 valve is active
        -> error: 1 if error in valves is present
        """
        data = {}
        # save settings
        data["access"] = VaemAccess.Read.value
        data["dataType"] = VaemDataType.UINT16.value
        data["paramIndex"] = VaemIndex.StatusWord.value
        data["paramSubIndex"] = 0
        data["errorRet"] = 0
        data["transferValue"] = 0

        register = _construct_registers(data)
        resp = self._transfer(register)

        return _deconstruct_registers(resp)

    def get_status(self):
        """
        Get the status of the VAEM
        The status is return as a dictionary with the following keys:
        -> status: 1 if more than 1 valve is active
        -> error: 1 if error in valves is present
        """
        return get_status(self._read_status_word())

    def wait_for_readiness(self, timeout=10.0):
        """
        Wait for the device to be ready with a timeout.
        """
        start_time = time.time()

        while True:
            # Check if timeout has been exceeded
            if time.time() - start_time > timeout:
                self._log.warning(
                    f"Timeout waiting for device readiness after {timeout} seconds"
                )
                return False

            readiness = self.get_status()["Readiness"]
            if readiness == 0:
                time.sleep(0.1)
                print(readiness)
                pass
            else:
                return True

    @handle_error_response
    def clear_error(self):
        """
        If any error occurs in valve opening, must be cleared with this opperation.
        """
        data = {}
        data["access"] = VaemAccess.Write.value
        data["dataType"] = VaemDataType.UINT16.value
        data["paramIndex"] = VaemIndex.ControlWord.value
        data["paramSubIndex"] = 0
        data["errorRet"] = 0
        data["transferValue"] = VaemControlWords.ResetErrors.value
        register = _construct_registers(data)
        resp = self._transfer(register)

        return _deconstruct_registers(resp)
