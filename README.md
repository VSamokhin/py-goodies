# softlab-py-goodies

Small Python utility scripts with a shared static-analysis toolchain.

## Layout

Scripts are grouped by domain under `scripts/`:

```text
scripts/
|-- photos/
|   `-- copyphotos2.py
`-- system/
    `-- cec_startkodi_on_poweron.py
```

## Scripts

### `photos/copyphotos2.py`

Mirrors a photo directory tree into a destination directory, optionally ignoring matching
names and marking or purging destination entries that no longer exist in the source.

Example wrapper for copying from an external drive to a mounted or mountable network share:

```bash
#!/usr/bin/env bash
set -euo pipefail

EXT_DRIVE="/Volumes/<external-drive>"
MOUNT_POINT="/Volumes/<network-share>"
FALLBACK_MOUNT_POINT="$HOME/<network-share>"
SMB_SHARE="//<user>@<server>/<share>"
SCRIPT_DIR="$HOME/Projects/softlab-py-goodies"

UNMOUNT_AFTER=false
UNMOUNT_WAIT_TIME=20

cleanup() {
    if [ "$UNMOUNT_AFTER" = true ]; then
        echo "Wait for $UNMOUNT_WAIT_TIME sec. before unmounting the share..."
        sleep $UNMOUNT_WAIT_TIME
        /sbin/umount -f "$MOUNT_POINT"
        rmdir "$MOUNT_POINT"
    fi
}

copy_photos() {
    python3 "$SCRIPT_DIR/scripts/photos/copyphotos2.py" "$@"
}

COMMON_IGNORE_ARGS=(
    --ignore ".DS_Store"
    --ignore "._"
)

trap cleanup EXIT

if [ ! -d "$EXT_DRIVE" ]; then
    echo "External drive $EXT_DRIVE is not found."
    exit 1
fi

if [ ! -d "$MOUNT_POINT" ]; then
    MOUNT_POINT="$FALLBACK_MOUNT_POINT"
    if [ -d "$MOUNT_POINT" ]; then
        echo "Mount point already exists: $MOUNT_POINT"
        exit 1
    fi

    mkdir "$MOUNT_POINT"
    echo "Mounting $SMB_SHARE at $MOUNT_POINT"
    /sbin/mount -t smbfs "$SMB_SHARE" "$MOUNT_POINT"
    UNMOUNT_AFTER=true
fi

copy_photos \
    "$EXT_DRIVE/DCIM" \
    "$MOUNT_POINT/Pictures/Camera" \
    --remove-mode PURGE_LEVEL2 \
    "${COMMON_IGNORE_ARGS[@]}"

copy_photos \
    "$EXT_DRIVE/Media" \
    "$MOUNT_POINT/Backup/Media" \
    --remove-mode PURGE_ALL \
    "${COMMON_IGNORE_ARGS[@]}"
```

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
