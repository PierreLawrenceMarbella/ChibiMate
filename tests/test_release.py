"""Release input checks without rebuilding or publishing the application."""

import struct
import tempfile
import unittest
from pathlib import Path

from package_windows import REQUIRED, inventory


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in REQUIRED:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        # Only the PE fields inspected by inventory; never executed.
        exe = bytearray(256)
        exe[:2] = b"MZ"
        struct.pack_into("<I", exe, 0x3C, 128)
        exe[128:132] = b"PE\0\0"
        struct.pack_into("<H", exe, 132, 0x8664)
        struct.pack_into("<H", exe, 128 + 24 + 68, 2)
        (self.root / "ChibiMate.exe").write_bytes(exe)

    def test_accepts_expected_runtime_and_public_certificates(self):
        cert = self.root / "_internal/certifi/cacert.pem"
        cert.parent.mkdir(parents=True)
        cert.write_text("public certificate fixture")
        self.assertEqual(len(inventory(self.root)), len(REQUIRED) + 1)

    def test_rejects_artwork_secrets_and_user_data(self):
        for name in ("_internal/alya.png", "_internal/.env", "_internal/private.pem",
                     "_internal/preferences.ini", "_internal/animation-packs/pack/file",
                     "_internal/personal.zip", "extra.txt"):
            with self.subTest(name=name):
                path = self.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
                try:
                    with self.assertRaises(ValueError):
                        inventory(self.root)
                finally:
                    path.unlink()

    def test_missing_qt_platform_plugin_fails(self):
        (self.root / "_internal/PySide6/plugins/platforms/qwindows.dll").unlink()
        with self.assertRaisesRegex(ValueError, "Required runtime"):
            inventory(self.root)

    def test_console_build_fails(self):
        exe = self.root / "ChibiMate.exe"
        data = bytearray(exe.read_bytes())
        struct.pack_into("<H", data, 128 + 24 + 68, 3)
        exe.write_bytes(data)
        with self.assertRaisesRegex(ValueError, "windowed"):
            inventory(self.root)


if __name__ == "__main__":
    unittest.main()
