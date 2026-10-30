# Public, windowed, one-folder release. Build with build_windows.ps1.
from pathlib import Path
import sys
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH)
notices = copy_metadata("openai", recursive=True)
for package in ("PySide6", "PySide6_Essentials", "shiboken6"):
    notices += copy_metadata(package)
notices.append((str(Path(sys.base_prefix) / "LICENSE.txt"), "licenses/python"))

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    # The original fallback is drawn by app/character.py. Deliberately do not
    # collect assets/, exports/, user data, or third-party character artwork.
    datas=notices,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ChibiMate",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    # No existing licensed application icon is present; use the standard icon.
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ChibiMate")
