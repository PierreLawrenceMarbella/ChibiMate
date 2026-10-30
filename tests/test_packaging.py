"""Resource resolution and public/source identity separation without a build."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.resources import resource_path


class PackagingTests(unittest.TestCase):
    def test_resource_paths_do_not_depend_on_launch_directory(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                self.assertTrue(resource_path("assets", "alya.png").is_file())
                with patch.object(sys, "_MEIPASS", folder, create=True):
                    self.assertEqual(resource_path("assets", "example.png"), Path(folder) / "assets" / "example.png")
            finally:
                os.chdir(previous)

    def test_public_build_uses_original_placeholder_and_separate_default_pack(self):
        root = Path(__file__).resolve().parent.parent
        code = '''
import sys,tempfile
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEvent
sys.frozen=True
with tempfile.TemporaryDirectory() as folder:
    sys._MEIPASS=folder
    from app.window import CharacterWindow
    from app.preferences import CharacterPreferences
    from app.resources import SPRITE_PATH,RESTORE_LABEL
    from app.settings_dialog import CharacterSettingsDialog
    app=QApplication([])
    prefs=CharacterPreferences(Path(folder)/'data')
    assert prefs._pack_key('')=='packs/default-placeholder'
    old=Path(folder)/'data'/'animation-packs'/('pack-'+'a'*32)
    old.mkdir(parents=True)
    prefs.settings.setValue('packs/default-alya/folder',old.name)
    assert prefs.pack_for('')[0] is None
    w=CharacterWindow(preferences=prefs)
    assert SPRITE_PATH is None and set(w._sprites.frames)=={'static'}
    assert not w._character.isNull() and w._character.hasAlphaChannel()
    d=CharacterSettingsDialog(w)
    assert 'placeholder' in d.pack_info.text()
    assert RESTORE_LABEL=='Restore Default Character'
    for widget in app.topLevelWidgets(): widget.close();widget.deleteLater()
    app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
'''
        result = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
