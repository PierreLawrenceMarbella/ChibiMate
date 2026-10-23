# ChibiMate — Phase 1

A small, transparent, always-on-top desktop chibi for Windows 10/11.
Requires Python 3.11 or newer. PySide6 is the only dependency.

## Install and run (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

With an activated environment, run `python main.py`.

- The character starts near the primary screen's bottom-right, above the taskbar.
- Hold the left mouse button on the character to drag it.
- Right-click the character and choose **Exit** to close the application.
- Optionally place a transparent PNG at `assets/character.png` and restart.
  Images fit within 200 × 240 logical pixels with their aspect ratio preserved.
  Missing or unreadable images use the original, Qt-drawn chibi placeholder.
  Asset paths work regardless of the terminal's current directory.

Phase 1 only: no animations, upload UI, AI features, or background services.
