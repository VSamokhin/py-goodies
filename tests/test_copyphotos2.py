import asyncio
import sys
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

    def test_isignore(self):
        self.assertTrue(self.cp.isignore(SRC_PATH.joinpath("somedir/exclusion.jpg")))
        self.assertTrue(self.cp.isignore(SRC_PATH.joinpath("ignore.jpg")))

        self.assertFalse(self.cp.isignore(SRC_PATH.joinpath("excl/somefile.jpg")))
        self.assertFalse(self.cp.isignore(SRC_PATH.joinpath("somedir/somefile.jpg")))

    @mock.patch("scripts.photos.copyphotos2.Path")
    def test_collectff(self, mock_path):
        p = mock.MagicMock()
        p.iterdir.return_value = [
            SRC_PATH.joinpath("file1.jpg"),
            SRC_PATH.joinpath("file2.jpg"),
            SRC_PATH.joinpath("dir1"),
            SRC_PATH.joinpath("dir2"),
        ]
        p.is_dir.side_effect = [False, False, True, True]
        p.is_file.side_effect = [True, True]
        mock_path.return_value = p


if __name__ == "__main__":
    unittest.main(exit=False)
