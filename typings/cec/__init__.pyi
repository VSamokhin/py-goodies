from typing import Any

CECDEVICE_TV: Any
CEC_DEVICE_TYPE_RECORDING_DEVICE: Any
CEC_POWER_STATUS_IN_TRANSITION_STANDBY_TO_ON: Any
CEC_POWER_STATUS_ON: Any
LIBCEC_VERSION_CURRENT: Any

class libcec_configuration:
    strDeviceName: str
    bActivateSource: int
    deviceTypes: Any
    clientVersion: Any
    serverVersion: Any

    def SetCommandCallback(self, callback: Any) -> None: ...

class ICECAdapter:
    @staticmethod
    def Create(config: libcec_configuration) -> Any: ...
