# pyright: reportMissingImports=false

import importlib
import subprocess
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

MODULE_NAME = "scripts.system.cec_startkodi_on_poweron"


class FakeDeviceTypes:
    def Add(self, device_type: int) -> None:
        self.device_type = device_type


class FakeConfig:
    def __init__(self) -> None:
        self.serverVersion = 1
        self.deviceTypes = FakeDeviceTypes()
        self.command_callback = None

    def SetCommandCallback(self, callback: object) -> None:
        self.command_callback = callback


@pytest.fixture
def cec_script(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[types.ModuleType, Mock]]:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))

    fake_lib = Mock()
    fake_lib.VersionToString.return_value = "1.0"
    fake_lib.GetLibInfo.return_value = "fake libCEC"

    fake_cec: Any = types.ModuleType("cec")
    fake_cec.CECDEVICE_TV = 0
    fake_cec.CEC_DEVICE_TYPE_RECORDING_DEVICE = 1
    fake_cec.CEC_POWER_STATUS_IN_TRANSITION_STANDBY_TO_ON = 2
    fake_cec.CEC_POWER_STATUS_ON = 3
    fake_cec.LIBCEC_VERSION_CURRENT = 4
    fake_cec.libcec_configuration = FakeConfig
    fake_cec.ICECAdapter = types.SimpleNamespace(Create=Mock(return_value=fake_lib))

    monkeypatch.setitem(sys.modules, "cec", fake_cec)
    sys.modules.pop(MODULE_NAME, None)

    module = importlib.import_module(MODULE_NAME)
    yield module, fake_lib

    sys.modules.pop(MODULE_NAME, None)


def test_commandcallback_sets_tvactive_for_tv_source_values(
    cec_script: tuple[types.ModuleType, Mock],
) -> None:
    module, _fake_lib = cec_script
    kodi = module.CecStartKodiOnPowerOn("systemctl start kodi-x11")

    assert kodi.commandcallback(["x", "x", "x", "0"]) == 0
    assert kodi.tvactive.is_set()

    kodi.tvactive.clear()

    assert kodi.commandcallback(["x", "x", "x", 0]) == 0
    assert kodi.tvactive.is_set()


def test_commandcallback_ignores_malformed_commands(
    cec_script: tuple[types.ModuleType, Mock],
) -> None:
    module, _fake_lib = cec_script
    kodi = module.CecStartKodiOnPowerOn("systemctl start kodi-x11")

    assert kodi.commandcallback(["too-short"]) == 0
    assert not kodi.tvactive.is_set()

    assert kodi.commandcallback(None) == 0
    assert not kodi.tvactive.is_set()


def test_attach2tv_closes_adapter_when_wait_raises(
    cec_script: tuple[types.ModuleType, Mock],
) -> None:
    module, fake_lib = cec_script
    adapter = types.SimpleNamespace(strComName="/dev/ttyACM0", adapterType=1)
    kodi = module.CecStartKodiOnPowerOn("systemctl start kodi-x11")
    kodi.detectadapter = Mock(return_value=adapter)
    kodi.wait4tvon = Mock(side_effect=RuntimeError("CEC read failed"))
    fake_lib.Open.return_value = True

    with pytest.raises(RuntimeError, match="CEC read failed"):
        kodi.attach2tv()

    fake_lib.Open.assert_called_once_with("/dev/ttyACM0", 500)
    fake_lib.Close.assert_called_once_with()


def test_wait4tvon_returns_true_when_power_status_is_on(
    cec_script: tuple[types.ModuleType, Mock],
) -> None:
    module, fake_lib = cec_script
    kodi = module.CecStartKodiOnPowerOn("systemctl start kodi-x11")
    fake_lib.GetDevicePowerStatus.return_value = module.cec.CEC_POWER_STATUS_ON

    assert kodi.wait4tvon() is True


def test_wait4tvon_uses_timed_event_wait_while_tv_is_off(
    cec_script: tuple[types.ModuleType, Mock],
) -> None:
    module, _fake_lib = cec_script
    kodi = module.CecStartKodiOnPowerOn("systemctl start kodi-x11")
    fake_event = types.SimpleNamespace(wait=Mock(), clear=Mock())
    kodi.go = Mock(side_effect=[True, False])
    kodi.ispoweron = Mock(return_value=False)
    kodi.tvactive = fake_event

    assert kodi.wait4tvon() is False
    fake_event.wait.assert_called_once_with(1)
    fake_event.clear.assert_called_once_with()


def test_runkodi_executes_split_command_without_shell(
    cec_script: tuple[types.ModuleType, Mock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _fake_lib = cec_script
    run = Mock(return_value=subprocess.CompletedProcess(args=[], returncode=0))
    sleep = Mock()
    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(module.time, "sleep", sleep)
    kodi = module.CecStartKodiOnPowerOn("systemctl start kodi-x11")

    kodi.runkodi()

    run.assert_called_once_with(["systemctl", "start", "kodi-x11"], check=False)
    sleep.assert_called_once_with(5)
    assert kodi.keepgoing is True


def test_runkodi_stops_on_nonzero_return_code(
    cec_script: tuple[types.ModuleType, Mock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _fake_lib = cec_script
    monkeypatch.setattr(
        module.subprocess,
        "run",
        Mock(return_value=subprocess.CompletedProcess(args=[], returncode=1)),
    )
    monkeypatch.setattr(module.time, "sleep", Mock())
    kodi = module.CecStartKodiOnPowerOn("systemctl start kodi-x11")

    kodi.runkodi()

    assert kodi.keepgoing is False
    module.time.sleep.assert_not_called()


def test_runkodi_stops_when_command_cannot_start(
    cec_script: tuple[types.ModuleType, Mock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, _fake_lib = cec_script
    monkeypatch.setattr(module.subprocess, "run", Mock(side_effect=FileNotFoundError("missing")))
    kodi = module.CecStartKodiOnPowerOn("missing-command")

    kodi.runkodi()

    assert kodi.keepgoing is False
