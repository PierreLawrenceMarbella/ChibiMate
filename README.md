# ChibiMate — Phase 4

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
  pauses during dragging and menus; dragging ends with a fresh idle period.
  Releasing outside the desktop brings her fully onto the nearest screen.
- Left-click for a random happy, surprised, or shy reaction lasting 1.5–2.5
  seconds, with a speech bubble for 3 seconds. Dragging never counts as a click.
  Missing reaction sprites keep the current image and show dialogue instead.
- Right-click for **Change Character** to select a PNG, **Character Size** for
  Small (100px), Medium (150px), or Large (200px), and **Restore Default Alya**.
  Images keep their transparency and aspect ratio, fitting fully inside the window.
  The selected image is copied into `%LOCALAPPDATA%\ChibiMate` alongside local
  preferences, so the character and size persist even if the original is moved.
  Missing or damaged saved images fall back to Alya. Custom PNGs use their own
  static image during movement and reactions; restoring Alya restores her sprites.
- The menu also offers **Pause Movement / Resume Movement**, **Trigger Random
  Reaction**, and **Exit ChibiMate**. Pausing still allows dragging and reactions.
- Sprite PNGs load from `assets/characters/alya/{walk,idle,blink,happy,surprised}/`.
  Numbered names sort naturally (`walk_1.png`, `walk_2.png`, …). Walking loops
  at 8 fps and needs at least two valid frames; idle loops at 2 fps or holds
  a single pose with bobbing. Blink and expression folders can hold one pose.
  The supplied walk sequence is `walk_01.png` through `walk_08.png`, making
  one complete loop per second.
- During idle, blink frames appear every 3–6 seconds. Automatic reactions are
  scheduled every 20–45 seconds and wait for idle; speech bubbles never stack.
  Bubbles stay on screen, let mouse clicks through, and hide automatically.
  An optional `shy/` sprite folder is supported alongside the existing poses.
- Frames are centered at the feet on a fixed transparent canvas, fit within
  200 × 150 logical pixels at Medium size, and retain their aspect ratios. Missing, empty,
  or insufficient walk/idle sequences fall back to `assets/alya.png`; missing
  reaction poses use dialogue instead. If the static PNG is missing or unreadable,
  a console warning accompanies the built-in placeholder.
  Asset paths work from any launch directory. White-background originals are
  preserved in `assets/characters/alya/originals/`; playback uses the prepared PNGs.

Adjust `WALK_SPEED` (logical pixels/second), `IDLE_SECONDS`, `WALK_SECONDS`,
and the bob settings in `app/window.py` to tune the behavior. A small transparent
margin keeps the idle bob inside the window at every size.

Edit dialogue and reaction timing in `app/dialogue.py`; sprite rates and blink
timing are in `app/sprites.py`. Phase 4 adds local character personalization;
no AI, voice features, or additional dependencies.

Checks: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`
