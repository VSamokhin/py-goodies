# BSD 3-Clause License
#
# Copyright (c) 2019-2026, Viktor Samokhin (wowyupiyo@gmail.com)
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
################################################################################
#
# v2.0.6
# This script is intended specifically for photo mirroing/backup of one directory to another.\n
# In my particular case the photos are organized in directories like follows:\n
# - root
#   - yyyy-MM-dd
#       - drone
#       - camera
#  - yyyy-MM-dd
# The whole structure below the source root (aka left side) directory is mirroed to the destination root (aka right side) directory.

import argparse
import asyncio
import concurrent.futures
import itertools
import logging
import logging.handlers
import os
import shutil
import threading
import time
from enum import Enum
from pathlib import Path

_LOGGER_COUNTER = itertools.count()


class CopyQueue:
    """Multithread queue implementation to copy files and dirs"""

    def __init__(self, *, threads=2, job_done_callback=None):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=threads)
        self.jobdone = job_done_callback
        self.futures = []
        self.count = 0
        self.lock = threading.Lock()

    def registercallback(self, future):
        if self.jobdone:
            future.add_done_callback(self.jobdone)

    def copyfile(self, src, dst):
        f = self.executor.submit(shutil.copy2, str(src), str(dst), follow_symlinks=False)
        self.registercallback(f)
        with self.lock:
            self.futures.append(f)
            self.count += 1

    def copydir(self, src, dst):
        # To be able to count all copied files
        def int_copy(*args):
            with self.lock:
                self.count += 1
            return shutil.copy2(*args)

        f = self.executor.submit(shutil.copytree, str(src), str(dst), copy_function=int_copy)
        self.registercallback(f)
        with self.lock:
            self.futures.append(f)

    def wait(self):
        self.executor.shutdown(wait=True)
        for future in self.futures:
            future.result()

    def getfilecount(self):
        with self.lock:
            return self.count


class RemoveMode(Enum):
    """Control the removal of files and directories while mirroing"""

    MARK = "MARK"
    """Only rename those deleted, but keep them"""
    PURGE_ALL = "PURGE_ALL"
    """Remove all deleted"""
    PURGE_LEVEL2 = "PURGE_LEVEL2"
    """Remove only those deleted, starting from the second level down the root directory.\n
    This mode allows to keep directories right under the root untouched.
    """

    def __str__(self):
        return self.value


class CopyPhotos:
    def __init__(
        self, *, ignores=None, read_only=True, remove_mode=None, verbose=False, log2file=True
    ):
        self.ignores = ignores
        self.readonly = read_only
        self.removedmode = remove_mode
        self.removedprefix = "_REMOVED_"
        self.logger = logging.getLogger(f"CopyPhotos.{next(_LOGGER_COUNTER)}")
        self.logger.propagate = False
        if verbose:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)

        self.logger.addHandler(logging.StreamHandler())

        self.dst = None

        if log2file:
            # Configure logging file handler
            fh = logging.handlers.RotatingFileHandler(
                "copyphotos2.log", maxBytes=(1048576), encoding="utf-8"
            )
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)

        # Init copy queue giving it a logging callback
        def copydonecallback(future):
            if future.exception():
                self.logger.error('Copy failed: "%s"', future.exception())
            else:
                self.logger.info('Copied: "%s"', str(future.result()))

        self.copyqueue = CopyQueue(threads=4, job_done_callback=copydonecallback)

    def getlogger(self):
        """Expose internal logger."""
        return self.logger

    def saferename(self, path, newname):
        newpath = path.with_name(newname)
        if not self.readonly:
            path.replace(newpath)

        return newpath

    def ismarked(self, path):
        return path.name.startswith(self.removedprefix)

    def markremoved(self, paths):
        """Take list of unmatched files or dirs in the destination directory
        and mark as removed those of them which are not yet marked.
        """
        for path in paths:
            if self.ismarked(path):
                self.logger.debug('Already marked as removed: "%s"', str(path))
            else:
                self.logger.debug('Mark as removed: "%s"', str(path))
                self.saferename(path, self.removedprefix + path.name)

    def rmdir(self, dir):
        self.logger.debug('Purge removed dir: "%s"', str(dir))
        if not self.readonly:
            shutil.rmtree(dir)

    def rmfile(self, file):
        self.logger.debug('Purge removed file: "%s"', str(file))
        if not self.readonly:
            os.remove(file)

    def purge(self, paths, rm_func):
        """Remove all entries given on the list."""
        for path in paths:
            rm_func(path)

    def purgelevel2(self, paths, rm_func):
        """Remove entries given on the list starting from level two down from the root."""
        assert self.dst is not None
        dstlen = len(self.dst.parts)
        for path in paths:
            if len(path.parts) - dstlen >= 2:
                rm_func(path)

    def remove(self, paths, rm_func):
        if self.removedmode == RemoveMode.MARK:
            self.markremoved(paths)
        elif self.removedmode == RemoveMode.PURGE_ALL:
            self.purge(paths, rm_func)
        elif self.removedmode == RemoveMode.PURGE_LEVEL2:
            self.purgelevel2(paths, rm_func)

    async def collectff(self, root, folders, files, check_dir_exclusion=False):
        """Collect files and dirs under the given root. Reciever dictionaries must be initialized!"""
        for i in root.iterdir():
            if check_dir_exclusion and self.isignore(i):
                self.logger.debug('Skip as exclusion: "%s"', str(i))
            else:
                if i.is_dir():
                    folders[i.name] = i
                elif i.is_file():
                    files[i.name] = i

    def isignore(self, path):
        """Check if a given file or directory name is on the exceptions list."""
        return any(i.lower() in path.name.lower() for i in [i for i in (self.ignores or [])])

    def checkfilesequal(self, leftentry, rightentry):
        """Check if given files are equal (size OR last modification date is enough for my case)."""
        lstat = os.stat(leftentry)
        rstat = os.stat(rightentry)
        return lstat.st_size == rstat.st_size or lstat.st_mtime == rstat.st_mtime

    async def copyremovedirs(self, leftdirs, rightdirs, dst):
        """Copy new dirs to the destination and mark or remove those which don't exist in the source anymore,
        return list of matched on both sides dirs.
        """
        matcheddirs = []
        for leftname, leftdir in leftdirs.items():
            rightdir = rightdirs.pop(leftname, None)
            if rightdir:
                matcheddirs.append((leftdir, rightdir))
            else:
                rightdir = dst.joinpath(leftdir.name)
                self.logger.debug("Copy directory %s -> %s", str(leftdir), str(rightdir))
                if not self.readonly:
                    self.copyqueue.copydir(leftdir, rightdir)

        self.remove(rightdirs.values(), self.rmdir)

        return matcheddirs

    async def copyremovefiles(self, leftfiles, rightfiles, dst):
        """Copy newer files to the destination directory and mark or remove those which don't exist in the source anymore.
        - rightfiles can be modified!
        """
        matchedfiles = []
        for leftname, leftfile in leftfiles.items():
            rightfile = rightfiles.pop(leftname, None)
            if rightfile and self.checkfilesequal(leftfile, rightfile):
                matchedfiles.append((leftfile, rightfile))
            else:
                rightfile = dst.joinpath(leftfile.name)
                self.logger.debug(
                    "Copy file %s -> %s %s",
                    str(leftfile),
                    str(rightfile),
                    ("[date, size]" if rightfile.exists() else "[new]"),
                )
                if not self.readonly:
                    self.copyqueue.copyfile(leftfile, rightfile)

        self.remove(rightfiles.values(), self.rmfile)

        return matchedfiles

    async def dowork(self, src, dst):
        """Do the copy routine recursively and return number of files copied.
        Source and destination dirs must be set and exist!
        """
        if not src or not src.exists():
            raise ValueError(f'Source directory is not correct: "{src}"')

        if not dst or not dst.exists():
            raise ValueError(f'Destination directory is not correct: "{dst}"')

        self.dst = dst

        dirs = [(src, dst)]
        while dirs:
            pair = dirs.pop()
            leftdir = pair[0]
            rightdir = pair[1]

            self.logger.debug('*** Compare "%s" and "%s"', str(leftdir), str(rightdir))

            leftdirs = dict()
            leftfiles = dict()
            leftTask = asyncio.create_task(self.collectff(leftdir, leftdirs, leftfiles, True))

            rightdirs = dict()
            rightfiles = dict()
            rightTask = asyncio.create_task(self.collectff(rightdir, rightdirs, rightfiles))

            await leftTask
            await rightTask

            # Process files of current directory
            filesTask = asyncio.create_task(self.copyremovefiles(leftfiles, rightfiles, rightdir))

            # Process sub-dirs of current directory
            dirsTask = asyncio.create_task(self.copyremovedirs(leftdirs, rightdirs, rightdir))

            await filesTask
            await dirsTask

            dirs.extend(dirsTask.result())

        self.copyqueue.wait()

        return self.copyqueue.getfilecount()


def gettime(sec):
    if sec < 0:
        return "0 sec."
    elif sec < 1:
        return f"{round(sec * 1000.0)} ms."
    elif sec < 60:
        return f"{round(sec)} sec."
    else:
        return f"{round(sec / 60.0)} min. {round(sec % 60.0)} sec."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i", "--ignore", action="append", help="list of source directory names to ignore"
    )
    parser.add_argument("-r", "--read-only", action="store_true", help="enable read-only mode")
    parser.add_argument(
        "-m",
        "--remove-mode",
        type=RemoveMode,
        choices=list(RemoveMode),
        help="mark only, purge all or purge starting with level 2 those entries in the destination directory which were removed",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="enable verbose logging")
    parser.add_argument("source_directory", help="directory to copy files from")
    parser.add_argument("dest_directory", help="directory to copy files to")
    args = parser.parse_args()

    cp = CopyPhotos(
        ignores=args.ignore,
        read_only=args.read_only,
        remove_mode=args.remove_mode,
        verbose=args.verbose,
    )
    cp.getlogger().info('Start looking for new entries in "%s"...', args.source_directory)
    if args.read_only:
        cp.getlogger().info("The read-only mode is ON!")

    try:
        start = time.time()
        count = asyncio.run(cp.dowork(Path(args.source_directory), Path(args.dest_directory)))
        end = time.time()

        cp.logger.info(f'{count} files copied into "{args.dest_directory}"')
        cp.logger.info("Job finished in: %s", gettime(end - start))
    except Exception as err:
        cp.logger.exception("Unrecoverable error occured:\n%s", err)
        raise SystemExit(1) from err


if __name__ == "__main__":
    main()
