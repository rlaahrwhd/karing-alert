import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app


class Value:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


def settings_object():
    obj = app.App.__new__(app.App)
    obj.gauge_region = None
    obj.volume = Value(80)
    obj.font_scale = 100
    obj.font_scale_input = Value('100%')
    obj.phase, obj.voice, obj.topmost = Value('3'), Value(True), Value(True)
    obj.theme = Value('dark')
    obj.high, obj.low = 800, 100
    obj.high_input, obj.low_input = Value('800'), Value('100')
    obj.status = Value('')
    return obj


class Settings(unittest.TestCase):
    def test_roundtrip_theme_and_thresholds(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(app, 'CONFIG', Path(directory)/'settings.json'):
            original = settings_object()
            original.theme.set('light')
            original.high, original.low = 900, 200
            original.volume.set(35)
            original.font_scale = 120
            original.phase.set('1')
            original.gauge_region = {'left':10,'top':20,'width':280,'height':310}
            original.settings_save()
            loaded = settings_object()
            loaded.settings_load()
            self.assertEqual((loaded.high, loaded.low, loaded.theme.get()), (900, 200, 'light'))
            self.assertEqual((loaded.high_input.get(), loaded.low_input.get()), ('900', '200'))
            self.assertEqual(loaded.volume.get(), 35)
            self.assertEqual(loaded.font_scale, 120)
            self.assertEqual(loaded.font_scale_input.get(), '120%')
            self.assertEqual(loaded.phase.get(), '1')
            self.assertEqual(loaded.gauge_region, original.gauge_region)

    def test_old_settings_and_invalid_thresholds(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(app, 'CONFIG', Path(directory)/'settings.json'):
            for data in ({'phase': 2}, {'high': 10, 'low': 20, 'theme': 'invalid'}):
                app.CONFIG.write_text(json.dumps(data), encoding='utf-8')
                loaded = settings_object()
                loaded.settings_load()
                self.assertEqual((loaded.high, loaded.low, loaded.theme.get()), (800, 100, 'dark'))
