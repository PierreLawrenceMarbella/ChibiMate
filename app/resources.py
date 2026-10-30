"""Read-only bundled paths and the public release's original default character."""

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root.joinpath(*parts)


PUBLIC_BUILD = bool(getattr(sys, "frozen", False))
DEFAULT_NAME = "ChibiMate" if PUBLIC_BUILD else "Alya"
RESTORE_LABEL = "Restore Default Character" if PUBLIC_BUILD else "Restore Default Alya"
# The public build draws the existing original placeholder from character.py.
# No third-party artwork or personal imported/generated files are bundled.
CHARACTER_PATH = resource_path("assets", "default.png" if PUBLIC_BUILD else "alya.png")
SPRITE_PATH = None if PUBLIC_BUILD else resource_path("assets", "characters", "alya")
DEFAULT_PACK_ID = "default-placeholder" if PUBLIC_BUILD else "default-alya"
