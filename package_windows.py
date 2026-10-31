"""Package the existing public Windows build; no rebuild, upload, or API calls."""

import hashlib
import stat
import struct
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VERSION = "0.1.0"
DOCUMENTS = (
    "README.md", "RELEASE_NOTES.md", "THIRD_PARTY_NOTICES.md",
    "docs/screenshots/settings.png",
    "licenses/qt/LGPL-3.0-only.txt", "licenses/qt/GPL-2.0-only.txt",
    "licenses/qt/GPL-3.0-only.txt",
)
REQUIRED = (
    "ChibiMate.exe", "_internal/base_library.zip", "_internal/python3.dll",
    "_internal/PySide6/Qt6Core.dll", "_internal/PySide6/Qt6Gui.dll",
    "_internal/PySide6/Qt6Widgets.dll",
    "_internal/PySide6/plugins/platforms/qwindows.dll",
    "_internal/licenses/python/LICENSE.txt",
)


def inventory(distribution: Path) -> list[Path]:
    """Fail closed on personal assets, links, or a non-windowed/non-x64 EXE."""
    for relative in REQUIRED:
        if not (distribution / relative).is_file():
            raise ValueError(f"Required runtime file missing: {relative}. Run build_windows.ps1.")
    files = []
    for path in sorted(distribution.rglob("*")):
        relative = path.relative_to(distribution)
        parts = tuple(part.lower() for part in relative.parts)
        if path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0) & 0x400:
            raise ValueError(f"Linked/reparse entry in distribution: {relative}")
        if not path.is_file():
            continue
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError(f"Non-regular distribution file: {relative}")
        if relative.as_posix() != "ChibiMate.exe" and relative.parts[0] != "_internal":
            raise ValueError(f"Unexpected distribution file: {relative}")
        if (any(part in {"assets", "exports", "user-data", "generated-characters",
                        "animation-packs", ".git", "__pycache__"} for part in parts)
                or any(part.startswith((".env", "credentials")) for part in parts)
                or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif",
                                           ".ini", ".log", ".tmp", ".key", ".pfx"}
                or (path.suffix.lower() == ".pem"
                    and relative.as_posix() != "_internal/certifi/cacert.pem")
                or (path.suffix.lower() == ".zip" and relative.as_posix() != "_internal/base_library.zip")):
            raise ValueError(f"Personal, artwork, or unexpected data in distribution: {relative}")
        files.append(path)
    exe = (distribution / "ChibiMate.exe").read_bytes()
    if exe[:2] != b"MZ":
        raise ValueError("Invalid Windows executable.")
    pe = struct.unpack_from("<I", exe, 0x3C)[0]
    if (exe[pe:pe + 4] != b"PE\0\0" or struct.unpack_from("<H", exe, pe + 4)[0] != 0x8664
            or struct.unpack_from("<H", exe, pe + 24 + 68)[0] != 2):
        raise ValueError("Expected a windowed, x64 Windows executable.")
    return files


def main() -> None:
    distribution = ROOT / "dist" / "ChibiMate"
    entries = [(path, "ChibiMate/" + path.relative_to(distribution).as_posix())
               for path in inventory(distribution)]
    entries += [(ROOT / name, "ChibiMate/" + name) for name in DOCUMENTS]
    for path, _ in entries:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing or linked release input: {path.name}")
    if len({name.casefold() for _, name in entries}) != len(entries):
        raise ValueError("Duplicate release paths.")
    output = ROOT / "releases" / f"ChibiMate-Windows-v{VERSION}.zip"
    output.parent.mkdir(exist_ok=True)
    staging = output.with_suffix(".zip.part")
    try:
        with zipfile.ZipFile(staging, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path, name in entries:
                archive.write(path, name)
        with zipfile.ZipFile(staging) as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise ValueError(f"ZIP integrity check failed: {corrupt}")
        staging.replace(output)
    finally:
        staging.unlink(missing_ok=True)
    with output.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n", encoding="ascii")
    print(f"Prepared {output}\n{len(entries)} files; {output.stat().st_size:,} bytes\nSHA256 {digest}")
    print("Review RELEASE_NOTES.md before publishing. Nothing was uploaded.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, struct.error, zipfile.BadZipFile) as error:
        raise SystemExit(f"Release packaging failed: {error}") from None
