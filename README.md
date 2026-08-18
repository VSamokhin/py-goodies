# softlab-py-goodies

Small Python utility scripts with a shared static-analysis toolchain.

## Current Scripts

This script is intended for a Linux-based home media server to listen for CEC-messages and start a Kodi instance when TV goes on.
For more details look into the source code.

## Prerequisites

* some Linux distribution
* python3 (v3.10.12 works well)
* libCEC >= v6.0.2 with Python bindings
  * To install libCEC with Python bindings you need to execute something like the following set of commands, depending on your distribution:
    ```bash
    apt-get update
    apt-get install libcec-dev
    pip3 install cec
    ```
* Kodi is set up to run as it's expected:
  * a window manager is configured to start and host Kodi
  * you'd also need to configure Kodi to exit when TV goes off

The script shall run with privileges sufficient to open COM-ports and start Kodi.

Execute this script either when TV is on and Kodi is already running or when TV is off and Kodi stopped.

## Static Analysis

Set up the local commit hook:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip pre-commit
.venv/bin/pre-commit install
```

Run the complete local toolchain manually:

```bash
.venv/bin/pre-commit run --all-files
```
