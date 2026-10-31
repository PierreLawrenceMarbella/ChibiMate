# ChibiMate v0.1.0 — Windows pre-release

A portable desktop companion with custom characters, offline animation packs,
and configurable desktop behavior. This is the initial pre-release, not an installer.

## Highlights

- Transparent companion with dragging, automatic movement, and cursor following.
- Click reactions, speech bubbles, autonomous behaviors, and manual action controls.
- PNG characters, folder/ZIP animation packs, and persistent customization.
- Variable frame counts across 12 actions, plus blink and surprised expressions.
- Dark settings window with preview, size, opacity, and playback preferences.
- Original default placeholder; no Alya artwork or personal characters in the Windows ZIP.

## Requirements and installation

Target: Windows 10/11, 64-bit. No Python installation or API key needed for offline use.

1. Download `ChibiMate-Windows-v0.1.0.zip` and extract it completely.
2. Open the extracted `ChibiMate` folder and launch `ChibiMate.exe`.
3. Keep `_internal` beside the EXE. Left-click to react; drag to move;
   right-click for customization, movement controls, and Exit.
4. Choose **Change Character**, then **Import Animation Pack** to add your own
   authorized artwork. One frame holds a pose; multiple frames animate.

Preferences and imports persist in `%LOCALAPPDATA%\ChibiMate`. Restore a hidden
companion using its tray icon. Verify the ZIP against the accompanying SHA-256 file
using PowerShell's `Get-FileHash -Algorithm SHA256`.

## Limitations and AI restrictions

- Unsigned, portable build; no installer or automatic updates.
- The public placeholder is static. Action animations require user-supplied frames.
- Follow and edge actions remain on the character's current monitor.
- The AI Generator is optional and requires your own provider access and environment
  configuration. Explicit generation sends the reference and prompt to OpenAI and
  may incur charges. No paid API requests were used to validate this release.
- Clean-machine Windows 10/11, additional hardware, and multi-monitor testing remain
  manual release checks. This is not a claim of complete platform validation.

## Verification

Phase 10A verified the Windows build, movement, dragging, settings, PNG and pack
imports, eight-frame playback, persistence, alternate working directories, and
clean exit on the development PC. Phase 10B verification on that PC passed:

- Six release-input and resource-path tests; dependency consistency check.
- ZIP CRC validation and byte-for-byte comparison of all 346 bundled runtime files.
- Extracted EXE startup, borderless/layered window, and exit code 0 from both the
  distribution folder and an unrelated working directory, without an API key or
  Python on PATH. User preferences remained unchanged and the instance lock released.

No application behavior was changed. The full application test suite was not rerun
for documentation and archive preparation; earlier feature tests are identified above.

## Maintainer publishing steps — not performed automatically

Before publishing:

1. Select a project software license. Review dependency notices and complete the
   applicable redistribution/source-availability requirements described in
   [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
2. Resolve redistribution rights for tracked Alya artwork and the exported pack.
   The Windows ZIP excludes them, but GitHub's source archives for a tag include
   files tracked at that commit. Do not tag those assets for public distribution
   without confirmed permission or a separately approved source cleanup.
3. Review the local commit and ZIP, and perform remaining target-PC checks.
4. When authorized, push the reviewed commit on `main`, create and push tag
   `v0.1.0` at that commit. No tag was created by release preparation.
5. In GitHub **Releases → Draft a new release**, select `v0.1.0`, title it
   **ChibiMate v0.1.0**, and mark it **Pre-release**.
6. Copy the user-facing sections above (excluding this maintainer section), attach
   `releases/ChibiMate-Windows-v0.1.0.zip` and its `.sha256` file, then review the draft.
7. Publish only after the repository owner approves. Do not upload `build/`, a lone
   EXE, private characters, credentials, or the Alya export as release assets.
