import os
import re
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from ucasdesk import core
from ucasdesk.core import Vault
from ucasdesk.ui import load_fonts, style_sheet


class MacVaultTests(unittest.TestCase):
    @patch('ucasdesk.core._keychain_set')
    @patch('ucasdesk.core._keychain_get')
    def test_vault_uses_macos_keychain(self, get_secret, set_secret):
        keychain = {'__index': {'keys': ['sep']}, 'sep': {'username': 'mac-user', 'password': 'mac-pass'}}
        get_secret.side_effect = keychain.get
        vault = Vault()
        self.assertEqual(vault.get('sep'), {'username': 'mac-user', 'password': 'mac-pass'})
        vault.set('iclass', 'student', 'secret', True)
        set_secret.assert_called_with('__index', {'keys': ['sep', 'iclass']})

    def test_saved_keys_survive_a_new_vault(self):
        store = {}
        with patch('ucasdesk.core._keychain_get', side_effect=store.get), \
             patch('ucasdesk.core._keychain_set', side_effect=store.__setitem__):
            Vault().set('sep', 'mac-user', 'mac-pass', True)
            Vault().set('iclass', 'student', 'secret', True)
            self.assertEqual(Vault().get('sep'), {'username': 'mac-user', 'password': 'mac-pass'})
            self.assertEqual(Vault().get('iclass'), {'username': 'student', 'password': 'secret'})
            Vault().set('iclass', 'student', 'secret', False)
            self.assertEqual(Vault().get('iclass'), {'username': '', 'password': ''})
            self.assertEqual(Vault().get('sep'), {'username': 'mac-user', 'password': 'mac-pass'})


class FontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        if not isinstance(app, QApplication):
            raise unittest.SkipTest('this process already created a QCoreApplication; Qt allows only one')
        cls.app = app

    def test_selected_font_family_exists_on_this_system(self):
        load_fonts()
        self.assertIn(self.app.font().family(), set(QFontDatabase.families()))

    def test_style_sheet_only_names_installed_families(self):
        self.app.setStyleSheet(style_sheet())
        named = re.findall(r'font-family:\s*([^;}]+)', style_sheet())
        families = set(QFontDatabase.families())
        used = [name.strip().strip('"\'') for group in named for name in group.split(',')]
        missing = [name for name in used if name not in families]
        self.assertEqual(missing, [], 'stylesheet names unavailable families: %s' % missing)


class BrowserDriverTests(unittest.TestCase):
    def test_browser_kind_matches_an_installed_browser(self):
        self.assertIn(core.browser_kind(), ('chrome', 'edge'))
        expected = 'edge' if 'edge' in core.browser_path().name.lower() else 'chrome'
        self.assertEqual(core.browser_kind(), expected)

    def test_driver_service_omits_windows_only_flags_on_posix(self):
        if os.name == 'nt':
            self.skipTest('POSIX-only check')
        service = core.driver_service('/tmp/ucas-driver-test.log', executable_path='/usr/bin/true')
        self.assertFalse(getattr(service, 'creation_flags', 0))

    def test_driver_service_hides_console_on_windows(self):
        with patch('ucasdesk.core.browser_kind', return_value='chrome'):
            with patch.object(os, 'name', 'nt'):
                service = core.driver_service('/tmp/ucas-driver-test.log', executable_path='/usr/bin/true')
        self.assertEqual(service.creation_flags, 0x08000000)

    def test_browser_options_carry_the_shared_startup_flags(self):
        options = core.browser_options('/tmp/ucas-profile')
        self.assertIn('--no-first-run', options.arguments)
        self.assertIn('--user-data-dir=/tmp/ucas-profile', options.arguments)
        self.assertEqual(options.page_load_strategy, 'eager')


if __name__ == '__main__':
    unittest.main()
