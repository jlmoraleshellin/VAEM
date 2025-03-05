import logging

from vaem.VaemDriver import vaemDriver
from vaem.dataTypes import VaemConfig


if __name__ == "__main__":
    vaemConfig = VaemConfig("192.168.8.118", 502, 0)

    try:
        vaem = vaemDriver(vaemConfig, logger=logging)
    except Exception as e:
        print(e)

    def func():
        vaem._vaem_init()
        print(vaem.read_status())
        vaem.select_valve(3)
        print(vaem.read_status())
        vaem.deselect_valve(3)
        print(vaem.read_status())
        vaem.select_valve(7)
        print(vaem.read_status())
        vaem.deselect_valve(7)
        print(vaem.read_status())

    func()
