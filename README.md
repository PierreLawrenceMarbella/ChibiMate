# ChibiMate - Phase 7

A small, transparent, always-on-top desktop chibi for Windows 10/11.
Requires Python 3.11 or newer. Dependencies are PySide6 and the official OpenAI Python SDK.

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
- Left-click for a random happy, surprised, or shy reaction lasting 1.5–2
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
- **Dance** is enabled only when `assets/characters/alya/dance/` contains at least
  two different readable poses (`dance_01.png`, `dance_02.png`, …). It loops for
  6 seconds at 8 fps, suspends walking, then resumes the previous behavior.
  Dragging interrupts dancing; reactions and dances never overlap.
  No dance or shy frames are currently supplied. The supplied blink is a wink pose.
- Sprite PNGs load from `assets/characters/alya/{walk,idle,blink,happy,surprised}/`.
  Numbered names sort naturally (`walk_1.png`, `walk_2.png`, …). Walking loops
  at 8 fps and needs at least two distinct valid poses; idle loops at 2 fps or holds
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

Edit dialogue and reaction timing in `app/dialogue.py`; `FRAME_RATES`,
`BLINK_SECONDS`, and `DANCE_SECONDS` are in `app/sprites.py`. Restart or choose
**Restore Default Alya** after adding sprite files. Phase 6 uses local PNG frames
with optional AI generation of static custom characters.

Checks: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`

## AI Chibi Generator

Install updated dependencies with `python -m pip install -r requirements.txt`.
Set `OPENAI_API_KEY` in your environment before launching (PowerShell:
`$env:OPENAI_API_KEY = "your-key"`). Right-click **AI Chibi Generator**, choose a
PNG/JPG/JPEG/WebP reference, optionally enter details, and click **Generate Chibi**.
This sends the image and prompt to OpenAI and may incur charges. No requests run
at startup. Canceling stops the local request but may not prevent server charges.

The default is `gpt-image-2.5-flare`, low quality, one 1024x1024 transparent PNG.
Override the model with `CHIBIMATE_IMAGE_MODEL` using a model supporting these
[image edit options](https://developers.openai.com/api/reference/python/resources/images/methods/edit).
Edit `DEFAULT_PROMPT` in `app/generation.py` to adjust the base instructions.
Model access depends on your API account; resemblance and transparency can vary.

Preview results before choosing **Use as ChibiMate** or **Save PNG**. Accepted
characters are saved in `%LOCALAPPDATA%\ChibiMate\generated-characters`, retain
your size preference, and use static movement and dialogue. Rejected previews
stay out of persistent storage. Reference files and Alya's sprites are unchanged.

## Offline animation packs

Choose your custom PNG with **Change Character**, then **Import Animation Pack**.
Select a folder or ZIP containing `idle/`, `walk/`, `blink/`, `happy/`,
`surprised/`, optional `shy/`, and/or `dance/` PNG frames. A ZIP may wrap these
inside one character folder. Preview available actions, choose 8?12 FPS for
walking/dancing, then apply or cancel. Missing actions use the character PNG or
dialogue; walking and dancing need at least two distinct poses.

Accepted packs live in `%LOCALAPPDATA%\ChibiMate\animation-packs`. Associations
survive restarts; selecting the same unchanged PNG again restores its pack.
Alya keeps her bundled sprites. Source assets are never overwritten.
Imports are limited to 256 PNGs, 2048px per side, 12 MB per frame, 24 megapixels
decoded total, and 100 MB compressed/expanded. Unsafe paths, links, damaged
images, and duplicate paths are rejected. This workflow is entirely offline,
needs no API key, and does not create animation artwork from a static image.
