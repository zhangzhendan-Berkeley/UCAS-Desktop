import unittest
from unittest.mock import patch
from ucasdesk.core import Vault


class MacVaultTests(unittest.TestCase):
    @patch('ucasdesk.core._keychain_set')
    @patch('ucasdesk.core._keychain_get', side_effect=lambda key: {'sep': {'username': 'mac-user', 'password': 'mac-pass'}}.get(key))
    def test_vault_uses_macos_keychain(self, get_secret, set_secret):
        vault = Vault()
        self.assertEqual(vault.get('sep'), {'username': 'mac-user', 'password': 'mac-pass'})
        vault.set('iclass', 'student', 'secret', True)
        set_secret.assert_called_once_with('iclass', {'username': 'student', 'password': 'secret'})


if __name__ == '__main__':
    unittest.main()
