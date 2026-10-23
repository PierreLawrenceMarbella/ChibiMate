"""Generator checks with local fixtures and mocked providers; no paid requests."""
import asyncio
import base64
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from openai import AsyncOpenAI
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.generation import OpenAIImageProvider
from app.generator_dialog import GeneratorDialog
from app.preferences import CharacterPreferences
from app.window import CharacterWindow


class FakeProvider:
    def __init__(self, data, fail=False, delay=0.03):
        self.data, self.fail, self.delay = data, fail, delay
        self.calls = 0
        self.cancelled = False

    async def generate(self, reference, prompt, key):
        self.calls += 1
        try:
            await asyncio.sleep(self.delay)
            if self.fail:
                raise RuntimeError('sensitive provider details')
            return self.data
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        image = QImage(60, 100, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        image.setPixelColor(30, 50, Qt.GlobalColor.red)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, 'PNG')
        self.png = bytes(buffer.data())
        self.source = self.root / 'reference.png'
        self.source.write_bytes(self.png)
        self.provider = FakeProvider(self.png)
        self.window = CharacterWindow(preferences=CharacterPreferences(self.root / 'data'))
        self.window.show()
        self.window._timer.stop()
        self.window.open_generator()
        self.dialog = self.window._generator
        self.dialog.provider = self.provider
        self.env = patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only-not-a-real-key'})
        self.env.start()

    def tearDown(self):
        if self.window._generator is not None:
            self.dialog.reject()
            self.wait_finished()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.env.stop()
        self.temp.cleanup()

    def wait_finished(self):
        for _ in range(500):
            if self.dialog.worker is None:
                return
            time.sleep(0.01)
            self.app.processEvents()
        self.fail('Worker did not finish')

    def choose(self, path=None):
        with patch('app.generator_dialog.QFileDialog.getOpenFileName', return_value=(str(path or self.source), '')):
            self.dialog.choose_reference()

    def generate(self):
        self.choose()
        self.dialog.start_generation()
        self.wait_finished()

    def test_dialog_reference_formats_and_invalid_input(self):
        self.assertTrue(self.dialog.isVisible())
        self.assertEqual(self.provider.calls, 0)
        for extension in ('png', 'jpg', 'jpeg', 'webp'):
            path = self.root / ('reference.' + extension)
            image = QImage.fromData(self.png)
            self.assertTrue(image.save(str(path)))
            before = path.read_bytes()
            self.choose(path)
            self.assertFalse(self.dialog.reference_preview.pixmap().isNull())
            self.assertEqual(before, path.read_bytes())
        previous = self.dialog.reference
        self.source.write_bytes(b'bad image')
        self.choose()
        self.assertIn('readable', self.dialog.status.text())
        self.assertEqual(self.dialog.reference, previous)
        with patch('app.generator_dialog.QFileDialog.getOpenFileName', return_value=('', '')):
            self.dialog.choose_reference()
        self.assertEqual(self.dialog.reference, previous)

    def test_missing_key_and_duplicate_clicks(self):
        self.choose()
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            self.dialog.start_generation()
        self.assertIn('OPENAI_API_KEY', self.dialog.status.text())
        self.assertEqual(self.provider.calls, 0)
        self.dialog.start_generation()
        self.assertFalse(self.dialog.generate.isEnabled())
        self.assertIn('Generating', self.dialog.status.text())
        self.dialog.start_generation()
        self.wait_finished()
        self.assertEqual(self.provider.calls, 1)
        self.assertTrue(self.dialog.use.isEnabled())

    def test_success_accept_persists_size_and_static_identity(self):
        self.window.set_character_size(200)
        before = self.window._custom_file
        self.generate()
        self.assertEqual(self.window._custom_file, before)
        self.assertEqual(self.dialog.generated, self.png)
        self.dialog.use.click()
        filename = self.window._custom_file
        self.assertTrue(filename.startswith('generated-characters/'))
        self.assertEqual((self.root / 'data' / filename).read_bytes(), self.png)
        prefs = CharacterPreferences(self.root / 'data')
        self.assertEqual(prefs.load_character()[0], filename)
        self.assertEqual(prefs.height, 200)
        self.assertEqual(set(self.window._sprites.frames), {'static'})

    def test_rejection_and_export_leave_active_character_unchanged(self):
        before = self.window._character.toImage()
        self.generate()
        exported = self.root / 'saved.png'
        with patch('app.generator_dialog.QFileDialog.getSaveFileName', return_value=(str(exported), '')):
            self.dialog.save_png()
        self.assertEqual(exported.read_bytes(), self.png)
        self.dialog.reject()
        self.assertEqual(self.window._character.toImage(), before)
        self.assertFalse((self.root / 'data' / 'generated-characters').exists())

    def test_failures_invalid_result_and_retry(self):
        self.provider.fail = True
        self.generate()
        self.assertIn('failed', self.dialog.status.text())
        self.assertNotIn('sensitive', self.dialog.status.text())
        self.assertFalse(self.dialog.use.isEnabled())
        self.provider.fail = False
        self.provider.data = b'not png'
        self.dialog.start_generation()
        self.wait_finished()
        self.assertFalse(self.dialog.use.isEnabled())
        self.provider.data = self.png
        self.dialog.start_generation()
        self.wait_finished()
        self.assertTrue(self.dialog.use.isEnabled())

    def test_close_in_flight_cancels_and_cleans_up(self):
        self.provider.delay = 60
        self.choose()
        self.dialog.start_generation()
        for _ in range(200):
            if self.provider.calls:
                break
            time.sleep(0.01)
            self.app.processEvents()
        self.assertEqual(self.provider.calls, 1)
        self.window.close()
        self.wait_finished()
        self.assertTrue(self.provider.cancelled)
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.window._timer.isActive())
        self.assertEqual(self.window._custom_file, '')

    def test_official_sdk_request_parameters_with_mock_transport(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={'created': 0, 'data': [{'b64_json': base64.b64encode(self.png).decode()}]})
        def client(**kwargs):
            return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        async def exercise():
            with patch('app.generation.AsyncOpenAI', side_effect=client):
                return await OpenAIImageProvider().generate(self.png, 'chibi', 'test-key')
        self.assertEqual(asyncio.run(exercise()), self.png)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url.path, '/v1/images/edits')
        body = requests[0].content
        for value in (b'gpt-image-2.5-flare', b'transparent', b'low', b'image/png', b'1024x1024'):
            self.assertIn(value, body)

    def test_api_errors_are_friendly_and_do_not_expose_response_bodies(self):
        self.choose()
        for status, expected in ((401, 'key'), (429, 'limit'), (500, 'could not complete')):
            def client(**kwargs):
                def handler(request):
                    return httpx.Response(status, json={'error': {'message': 'secret-image-details'}})
                return AsyncOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
            self.dialog.provider = OpenAIImageProvider()
            with patch('app.generation.AsyncOpenAI', side_effect=client):
                self.dialog.start_generation()
                self.wait_finished()
            self.assertIn(expected, self.dialog.status.text())
            self.assertNotIn('secret', self.dialog.status.text())


if __name__ == '__main__':
    unittest.main()
