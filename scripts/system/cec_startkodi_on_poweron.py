#!/usr/bin/python3

# BSD 3-Clause License
#
# Copyright (c) 2023-2026, Viktor Samokhin (wowyupiyo@gmail.com)
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# v1.0.3

import logging
import logging.handlers
import shlex
import subprocess
import time
from threading import Event
from typing import Any, Protocol

import cec


class CecAdapter(Protocol):
    strComName: str
    adapterType: Any


"""This script is intended for an (Ubuntu) home media server to listen for CEC-messages
and start Kodi when TV goes on.
When Kodi is up and running, it exclusively grabs CEC-adapater's COM-port,
making it unavailable for others to open and the script is simply retrying to gain
access to the adapter in a loop. After Kodi exits, the script grabs CEC-adapter
and begins waiting for any broadcast command where TV specified as the source (0)
to start Kodi upon again. The routine is supposed to run forever, the only exit trigger
is a non-zero return value of the command to start Kodi.
For the routine to work properly, Kodi shall be configured to exit after TV has been switched off,
the corresponding setting resides under the "System -> Input -> Peripherals -> CEC Adpater" preferences of Kodi.
A command to start Kodi depends on the actual setup, in my case Kodi runs as the only app in an Openbox session.
Execute this script either when TV is on and Kodi is already running or when TV is off and Kodi stopped
"""


class CecStartKodiOnPowerOn:
    keepgoing = True

    def __init__(self, command: str, log2file: bool = False, verbose: bool = False) -> None:
        self.command = command

        # Configure logger
        self.logger = logging.getLogger(f"CecStartKodi.{id(self):x}")
        self.logger.propagate = False
        self.logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        logFormatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch = logging.StreamHandler()
        ch.setFormatter(logFormatter)
        self.logger.addHandler(ch)

        if log2file:
            # Configure logging file handler
            fh = logging.handlers.RotatingFileHandler(
                "execonpoweroncec.log", maxBytes=(1048576), encoding="utf-8"
            )
            fh.setFormatter(logFormatter)
            self.logger.addHandler(fh)

        self.cecconfig = cec.libcec_configuration()
        self.cecconfig.strDeviceName = "execonpower"
        self.cecconfig.bActivateSource = 0
        self.cecconfig.deviceTypes.Add(cec.CEC_DEVICE_TYPE_RECORDING_DEVICE)
        self.cecconfig.clientVersion = cec.LIBCEC_VERSION_CURRENT

        # Monitor TV's power status with an event
        self.tvactive = Event()

        # self.cecconfig.SetKeyPressCallback(self.keypresscallback)
        self.cecconfig.SetCommandCallback(self.commandcallback)

        self.lib = cec.ICECAdapter.Create(self.cecconfig)
        version = self.lib.VersionToString(self.cecconfig.serverVersion)
        libinfo = self.lib.GetLibInfo()
        self.logger.info(f"[libCEC {version}] {libinfo}")

    # def keypresscallback(self, key, duration):
    #    self.logger.debug(f'libCEC key: [{key}]')
    #    return 0

    def commandcallback(self, cmd: Any) -> int:
        self.logger.debug(f"libCEC command: [{cmd}]")
        try:
            command_source = cmd[3]
        except (IndexError, TypeError):
            self.logger.warning(f"Ignoring malformed libCEC command: [{cmd}]")
            return 0

        if str(command_source) == "0":
            self.tvactive.set()

        return 0

    def attach2tv(self) -> None:
        """Entry point of the script, it exits only if no CEC-adapter has been found"""
        adapter = self.detectadapter()
        if adapter:
            self.tvactive.clear()
            while self.go():
                if self.lib.Open(adapter.strComName, 500):
                    self.logger.info("Connected to the adapter")
                    try:
                        tvon = self.wait4tvon()
                    finally:
                        self.lib.Close()

                    if tvon:
                        self.runkodi()

                    return
                else:
                    self.logger.debug(f"Couldn't open [{adapter.strComName}] (busy?), retrying...")
                    # Don't load CPU much
                    time.sleep(2)
        else:
            self.logger.info("No CEC adapter found")

    def detectadapter(self) -> CecAdapter | None:
        """Loop until an adapter found, then return the first on the list"""
        # search for adapters
        while self.go():
            adapters = self.lib.DetectAdapters()
            adapter = adapters[0] if adapters else None
            if adapter:
                adaptertypestr = self.lib.AdapterTypeToString(adapter.adapterType)
                self.logger.info(f"Found an '{adaptertypestr}' adapter on [{adapter.strComName}]")
                return adapter
            else:
                self.logger.debug("No adapters found, retrying...")
                # No need for a hurry
                time.sleep(5)

        return None

    def wait4tvon(self) -> bool:
        while self.go():
            if self.ispoweron():
                self.logger.info("TV is ON")
                return True

            self.tvactive.wait(1)
            self.tvactive.clear()

        return False

    def ispoweron(self) -> bool:
        """Retrieve a power status of the attached TV"""
        pwrstatus = self.lib.GetDevicePowerStatus(cec.CECDEVICE_TV)
        return (
            pwrstatus == cec.CEC_POWER_STATUS_IN_TRANSITION_STANDBY_TO_ON
            or pwrstatus == cec.CEC_POWER_STATUS_ON
        )

    def runkodi(self) -> None:
        try:
            completed = subprocess.run(shlex.split(self.command), check=False)
            retval = completed.returncode
        except OSError as exc:
            self.logger.info(f"Failed to execute [{self.command}]: {exc}")
            self.keepgoing = False
            return

        self.logger.info(f"Executed [{self.command}], return value is {retval}")
        if retval == 0:
            # Allow Kodi to start and grab the CEC adapter
            time.sleep(5)
        else:
            self.logger.info("Seems the command failed, find the reason and restart this script")
            self.keepgoing = False

    def go(self) -> bool:
        """Here I could e.g. read a flag file and stop execution of the script"""
        return self.keepgoing


if __name__ == "__main__":
    # I've hardcoded the command for simplicity, you can opt to move it out from here
    # and pass as a command-line parameter instead
    ceckodi = CecStartKodiOnPowerOn(
        "systemctl start kodi-x11", False, False
    )  # Start an Openbox session with Kodi
    # Loop until a CEC-adapter found
    while ceckodi.go():
        ceckodi.attach2tv()
        time.sleep(5)
