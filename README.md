# ChibiMate — Phase 2.5

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
- Sprite PNGs load from `assets/characters/alya/{walk,idle,blink,happy,surprised}/`.
  Numbered names sort naturally (`walk_1.png`, `walk_2.png`, …). Walking loops
  at 8 fps and needs at least two valid frames; idle loops at 2 fps or holds
  a single pose with bobbing. Blink and expression folders can hold one pose.
  The supplied walk sequence is `walk_01.png` through `walk_08.png`, making
  one complete loop per second.
- During idle, blink frames appear every 3–6 seconds; happy/surprised poses
  occasionally appear for 1.2 seconds. Walking takes priority over expressions.
- Frames are centered at the feet on a fixed transparent canvas, fit within
  200 × 150 logical pixels, and retain their aspect ratios. Missing, empty,
  or insufficient walk/idle sequences fall back to `assets/alya.png`; missing
  optional expressions are skipped. If the static PNG is missing or unreadable,
  a console warning accompanies the built-in placeholder.
  Asset paths work from any launch directory. White-background originals are
  preserved in `assets/characters/alya/originals/`; playback uses the prepared PNGs.

Adjust `WALK_SPEED` (logical pixels/second), `IDLE_SECONDS`, `WALK_SECONDS`,
and the bob settings in `app/window.py` to tune the behavior. The character
stays 150 pixels tall, with a small transparent margin for the idle bob.

Sprite rates and blink/expression intervals are in `app/sprites.py`.
Phase 2.5 only: folder-based frames using the existing timer; no AI or threads.

Checks: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
