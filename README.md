# softlab-py-goodies

Small Python utility scripts with a shared static-analysis toolchain.

## Layout

Scripts are grouped by domain under `scripts/`:

```text
scripts/
`-- system/
    `-- cec_startkodi_on_poweron.py
```

## Scripts

### `system/cec_startkodi_on_poweron.py`

Listens for CEC messages on a Linux-based home media server and starts Kodi when the TV turns on.

Prerequisites:

* Some Linux distribution
* Python 3
* libCEC >= v6.0.2 with Python bindings
* Kodi configured to run under a window manager and exit when the TV turns off

Example libCEC setup:

```bash
apt-get update
apt-get install libcec-dev
pip3 install cec
```

Execute this script either when TV is on and Kodi is already running or when TV is off and Kodi stopped.
It must run with privileges sufficient to open COM ports and start Kodi.

Run it directly:

```bash
python scripts/system/cec_startkodi_on_poweron.py
```

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
