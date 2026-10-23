# ChibiMate — Phase 2

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
- Alya gently bobs while idle, then walks left or right, facing her direction.
  Idle periods last 3–8 seconds; walks last 2–5 seconds. Screen edges turn her
  around, and available screen space excludes the taskbar.
- Hold the left mouse button on the character to drag it. Automatic behavior
  pauses during dragging and menus, then resumes with an idle period.
  Releasing outside the desktop brings her fully onto the nearest screen.
- Right-click the character and choose **Exit** to close the application.
- Alya loads from `assets/alya.png` at 150 logical pixels tall by default.
  Images fit within 200 × 150 logical pixels without cropping, preserving
  their transparency and aspect ratio. Missing or unreadable images print a
  warning to the console and use the original, Qt-drawn chibi placeholder.
  Asset paths work regardless of the terminal's current directory.

Adjust `WALK_SPEED` (logical pixels/second), `IDLE_SECONDS`, `WALK_SECONDS`,
and the bob settings in `app/window.py` to tune the behavior. The character
stays 150 pixels tall, with a small transparent margin for the idle bob.

Phase 2 only: static-PNG movement and bobbing; no sprite sheets, AI, or threads.

Checks: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
