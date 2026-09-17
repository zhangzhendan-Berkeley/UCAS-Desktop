import unittest
from unittest.mock import patch
from ucasdesk.core import Vault


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


if __name__ == '__main__':
    unittest.main()
