import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.photos import copyphotos2

SRC_PATH = Path("c:\\src")
DST_PATH = Path("c:\\dst")
LEFT_FILE = SRC_PATH.joinpath("left.jpg")
RIGHT_FILE = DST_PATH.joinpath("right.jpg")


class ModuleTest(unittest.TestCase):
    def test_get_time(self):
        self.assertEqual(copyphotos2.gettime(0.5), "500 ms.")
        self.assertEqual(copyphotos2.gettime(0), "0 ms.")
        self.assertEqual(copyphotos2.gettime(-1), "0 sec.")
        self.assertEqual(copyphotos2.gettime(59.5), "60 sec.")
        self.assertEqual(copyphotos2.gettime(1), "1 sec.")
        self.assertEqual(copyphotos2.gettime(1.1), "1 sec.")
        self.assertEqual(copyphotos2.gettime(123), "2 min. 3 sec.")
        self.assertEqual(copyphotos2.gettime(123.6), "2 min. 4 sec.")

    def test_copyqueue_copies_file_counts_job_and_invokes_callback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jpg"
            destination = root / "destination.jpg"
            source.write_text("photo")
            callback = mock.Mock()
            queue = copyphotos2.CopyQueue(threads=1, job_done_callback=callback)

            queue.copyfile(source, destination)
            queue.wait()

            self.assertEqual(destination.read_text(), "photo")
            self.assertEqual(queue.getfilecount(), 1)
            callback.assert_called_once()
            self.assertEqual(callback.call_args.args[0].result(), str(destination))

    def test_copyqueue_wait_propagates_copy_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_source = root / "missing.jpg"
            destination = root / "destination.jpg"
            queue = copyphotos2.CopyQueue(threads=1)

            queue.copyfile(missing_source, destination)

            with self.assertRaises(FileNotFoundError):
                queue.wait()


class CopyPhotosTestCase(unittest.TestCase):
    def setUp(self):
        self.cp = copyphotos2.CopyPhotos(ignores=["excl", "ign"], log2file=False)
        return super().setUp()

    @mock.patch("scripts.photos.copyphotos2.Path.exists")
    def test_dowork_fail(self, mock_exists):
        # SRC empty
        with self.assertRaises(ValueError):
            asyncio.run(self.cp.dowork(None, DST_PATH))
        mock_exists.assert_not_called()
        mock_exists.reset_mock()

        # DST empty
        mock_exists.return_value = True
        with self.assertRaises(ValueError):
            asyncio.run(self.cp.dowork(SRC_PATH, None))
        mock_exists.assert_called_once()
        mock_exists.reset_mock()

        # Both empty
        with self.assertRaises(ValueError):
            asyncio.run(self.cp.dowork(None, None))
        mock_exists.assert_not_called()
        mock_exists.reset_mock()

        # SRC doesn't exist
        mock_exists.return_value = False
        with self.assertRaises(ValueError):
            asyncio.run(self.cp.dowork(SRC_PATH, DST_PATH))
        mock_exists.assert_called_once()
        mock_exists.reset_mock()

        # DST doesn't exist
        mock_exists.side_effect = [True, False]
        with self.assertRaises(ValueError):
            asyncio.run(self.cp.dowork(SRC_PATH, DST_PATH))
        self.assertEqual(mock_exists.call_count, 2)
        mock_exists.side_effect = None
        mock_exists.reset_mock()

        # SRC wrong type
        with self.assertRaises(AttributeError):
            asyncio.run(self.cp.dowork("SRC_PATH", DST_PATH))

        # DST wrong type
        mock_exists.return_value = True
        with self.assertRaises(AttributeError):
            asyncio.run(self.cp.dowork(SRC_PATH, "DST_PATH"))
        mock_exists.assert_called_once()

        # Both wrong type
        with self.assertRaises(AttributeError):
            asyncio.run(self.cp.dowork("SRC_PATH", "DST_PATH"))

    @mock.patch("scripts.photos.copyphotos2.os.stat")
    def test_checkfilesequal_equal(self, mock_os_stat):
        lstat = mock.MagicMock()
        lstat.st_size = 666
        lstat.st_mtime = 0.666

        rstat = mock.MagicMock()
        rstat.st_size = 666
        rstat.st_mtime = 0.666

        mock_os_stat.side_effect = [lstat, rstat]

        self.assertTrue(self.cp.checkfilesequal(LEFT_FILE, RIGHT_FILE))
        self.assertEqual(mock_os_stat.call_count, 2)

    @mock.patch("scripts.photos.copyphotos2.os.stat")
    def test_checkfilesequal_not_equal(self, mock_os_stat):
        lstat = mock.MagicMock()
        lstat.st_size = 666
        lstat.st_mtime = 0.666

        rstat = mock.MagicMock()
        rstat.st_size = 777
        rstat.st_mtime = 0.777

        mock_os_stat.side_effect = [lstat, rstat]

        self.assertFalse(self.cp.checkfilesequal(LEFT_FILE, RIGHT_FILE))
        self.assertEqual(mock_os_stat.call_count, 2)

    @mock.patch("scripts.photos.copyphotos2.os.stat")
    def test_checkfilesequal_accepts_matching_size_or_mtime(self, mock_os_stat):
        left_same_size = mock.MagicMock()
        left_same_size.st_size = 666
        left_same_size.st_mtime = 0.666

        right_same_size = mock.MagicMock()
        right_same_size.st_size = 666
        right_same_size.st_mtime = 0.777

        left_same_mtime = mock.MagicMock()
        left_same_mtime.st_size = 666
        left_same_mtime.st_mtime = 0.666

        right_same_mtime = mock.MagicMock()
        right_same_mtime.st_size = 777
        right_same_mtime.st_mtime = 0.666

        mock_os_stat.side_effect = [
            left_same_size,
            right_same_size,
            left_same_mtime,
            right_same_mtime,
        ]

        self.assertTrue(self.cp.checkfilesequal(LEFT_FILE, RIGHT_FILE))
        self.assertTrue(self.cp.checkfilesequal(LEFT_FILE, RIGHT_FILE))

    def test_isignore(self):
        self.assertTrue(self.cp.isignore(SRC_PATH.joinpath("somedir/exclusion.jpg")))
        self.assertTrue(self.cp.isignore(SRC_PATH.joinpath("ignore.jpg")))

        self.assertFalse(self.cp.isignore(SRC_PATH.joinpath("excl/somefile.jpg")))
        self.assertFalse(self.cp.isignore(SRC_PATH.joinpath("somedir/somefile.jpg")))

    def test_instances_use_separate_loggers_without_duplicate_handlers(self):
        first = copyphotos2.CopyPhotos(log2file=False)
        second = copyphotos2.CopyPhotos(log2file=False)

        self.assertIsNot(first.getlogger(), second.getlogger())
        self.assertEqual(len(first.getlogger().handlers), 1)
        self.assertEqual(len(second.getlogger().handlers), 1)

    def test_collectff_populates_files_and_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dir1").mkdir()
            (root / "dir2").mkdir()
            (root / "file1.jpg").write_text("photo")
            (root / "file2.jpg").write_text("photo")

            folders = {}
            files = {}

            asyncio.run(self.cp.collectff(root, folders, files))

        self.assertEqual(folders, {"dir1": root / "dir1", "dir2": root / "dir2"})
        self.assertEqual(files, {"file1.jpg": root / "file1.jpg", "file2.jpg": root / "file2.jpg"})

    def test_collectff_populates_files_and_dirs_and_skips_ignored_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep").mkdir()
            (root / "excluded").mkdir()
            (root / "photo.jpg").write_text("photo")

            folders = {}
            files = {}

            asyncio.run(self.cp.collectff(root, folders, files, check_dir_exclusion=True))

        self.assertEqual(folders, {"keep": root / "keep"})
        self.assertEqual(files, {"photo.jpg": root / "photo.jpg"})

    def test_remove_modes_mark_and_purge_expected_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            destination = root / "dst"
            destination.mkdir()
            top_level = destination / "top-level"
            nested = destination / "album" / "photo.jpg"
            nested.parent.mkdir()
            top_level.write_text("old")
            nested.write_text("old")

            mark_cp = copyphotos2.CopyPhotos(
                ignores=["excl", "ign"],
                log2file=False,
                read_only=False,
                remove_mode=copyphotos2.RemoveMode.MARK,
            )
            mark_cp.remove([top_level], mark_cp.rmfile)
            self.assertFalse(top_level.exists())
            self.assertTrue((destination / "_REMOVED_top-level").exists())

            purge_level2_cp = copyphotos2.CopyPhotos(
                ignores=["excl", "ign"],
                log2file=False,
                read_only=False,
                remove_mode=copyphotos2.RemoveMode.PURGE_LEVEL2,
            )
            purge_level2_cp.dst = destination
            purge_level2_cp.remove(
                [destination / "_REMOVED_top-level", nested], purge_level2_cp.rmfile
            )

            self.assertTrue((destination / "_REMOVED_top-level").exists())
            self.assertFalse(nested.exists())

    def test_copyremovefiles_matches_equal_files_copies_new_files_and_removes_stale_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            dst = root / "dst"
            src.mkdir()
            dst.mkdir()
            left_same = src / "same.jpg"
            left_new = src / "new.jpg"
            right_same = dst / "same.jpg"
            right_stale = dst / "stale.jpg"
            left_same.write_text("same")
            right_same.write_text("same")
            os.utime(left_same, (1, 1))
            os.utime(right_same, (1, 1))
            left_new.write_text("new")
            right_stale.write_text("stale")

            self.cp.readonly = False
            self.cp.copyqueue = mock.Mock()
            self.cp.remove = mock.Mock()

            matched = asyncio.run(
                self.cp.copyremovefiles(
                    {"same.jpg": left_same, "new.jpg": left_new},
                    {"same.jpg": right_same, "stale.jpg": right_stale},
                    dst,
                )
            )

        self.assertEqual(matched, [(left_same, right_same)])
        self.cp.copyqueue.copyfile.assert_called_once_with(left_new, dst / "new.jpg")
        self.cp.remove.assert_called_once()
        self.assertEqual(list(self.cp.remove.call_args.args[0]), [right_stale])

    def test_copyremovedirs_matches_existing_dirs_copies_new_dirs_and_removes_stale_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            dst = root / "dst"
            src.mkdir()
            dst.mkdir()
            left_existing = src / "existing"
            left_new = src / "new"
            right_existing = dst / "existing"
            right_stale = dst / "stale"
            left_existing.mkdir()
            left_new.mkdir()
            right_existing.mkdir()
            right_stale.mkdir()

            self.cp.readonly = False
            self.cp.copyqueue = mock.Mock()
            self.cp.remove = mock.Mock()

            matched = asyncio.run(
                self.cp.copyremovedirs(
                    {"existing": left_existing, "new": left_new},
                    {"existing": right_existing, "stale": right_stale},
                    dst,
                )
            )

        self.assertEqual(matched, [(left_existing, right_existing)])
        self.cp.copyqueue.copydir.assert_called_once_with(left_new, dst / "new")
        self.cp.remove.assert_called_once()
        self.assertEqual(list(self.cp.remove.call_args.args[0]), [right_stale])

    def test_dowork_copies_new_tree_and_marks_removed_destination_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            dst = root / "dst"
            src.mkdir()
            dst.mkdir()
            (src / "album").mkdir()
            (src / "album" / "photo.jpg").write_text("new photo")
            (dst / "stale.jpg").write_text("stale")
            cp = copyphotos2.CopyPhotos(
                ignores=["excl", "ign"],
                log2file=False,
                read_only=False,
                remove_mode=copyphotos2.RemoveMode.MARK,
            )

            copied_count = asyncio.run(cp.dowork(src, dst))

            self.assertEqual(copied_count, 1)
            self.assertEqual((dst / "album" / "photo.jpg").read_text(), "new photo")
            self.assertFalse((dst / "stale.jpg").exists())
            self.assertEqual((dst / "_REMOVED_stale.jpg").read_text(), "stale")

    def test_dowork_propagates_copy_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            dst = root / "dst"
            src.mkdir()
            dst.mkdir()
            source = src / "photo.jpg"
            source.write_text("photo")
            cp = copyphotos2.CopyPhotos(log2file=False, read_only=False)

            with mock.patch("scripts.photos.copyphotos2.shutil.copy2") as copy2:
                copy2.side_effect = OSError("copy failed")

                with self.assertRaises(OSError):
                    asyncio.run(cp.dowork(src, dst))

    def test_main_returns_nonzero_when_work_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            current_dir = Path.cwd()
            os.chdir(tmp)
            try:
                with (
                    mock.patch.object(
                        sys, "argv", ["copyphotos2.py", "/missing/src", "/missing/dst"]
                    ),
                    mock.patch.object(
                        copyphotos2.CopyPhotos,
                        "dowork",
                        mock.AsyncMock(side_effect=RuntimeError("copy failed")),
                    ),
                    mock.patch("scripts.photos.copyphotos2.Path.exists", return_value=True),
                    self.assertRaises(SystemExit) as err,
                ):
                    copyphotos2.main()
            finally:
                os.chdir(current_dir)

        self.assertEqual(err.exception.code, 1)

    def test_main_does_not_swallow_keyboard_interrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            current_dir = Path.cwd()
            os.chdir(tmp)
            try:
                with (
                    mock.patch.object(
                        sys, "argv", ["copyphotos2.py", "/missing/src", "/missing/dst"]
                    ),
                    mock.patch.object(
                        copyphotos2.CopyPhotos,
                        "dowork",
                        mock.AsyncMock(side_effect=KeyboardInterrupt),
                    ),
                    mock.patch("scripts.photos.copyphotos2.Path.exists", return_value=True),
                    self.assertRaises(KeyboardInterrupt),
                ):
                    copyphotos2.main()
            finally:
                os.chdir(current_dir)


if __name__ == "__main__":
    unittest.main(exit=False)
