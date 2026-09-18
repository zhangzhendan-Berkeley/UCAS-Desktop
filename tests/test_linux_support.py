import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ucasdesk import core, linux_keyring as keyring


class MemoryBackend:
    def __init__(self): self.records = {}
    def get_password(self, service, key): return self.records.get((service, key))
    def set_password(self, service, key, value): self.records[service, key] = value
    def delete_password(self, service, key): del self.records[service, key]


class LinuxVaultTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.store = MemoryBackend()
        for item in (patch('ucasdesk.core.DATA', self.directory), patch('ucasdesk.core.sys.platform', 'linux'),
                     patch('ucasdesk.linux_keyring.backend', return_value=self.store)):
            item.start(); self.addCleanup(item.stop)

    def test_existing_patch_accounts_extensions_and_forget(self):
        self.store.set_password(keyring.SERVICE, 'sep', json.dumps({'username':'student','password':'fixture-secret'}))
        vault = core.Vault()
        self.assertEqual(vault.get('sep')['username'], 'student')
        vault.set('extension', 'addon', 'extension-secret')
        self.assertEqual(core.Vault().get('extension')['password'], 'extension-secret')
        vault.set('extension', 'addon', 'session-only', False)
        self.assertEqual(vault.get('extension')['password'], 'session-only')
        self.assertEqual(core.Vault().get('extension')['password'], '')
        self.assertEqual(core.Vault().get('sep')['username'], 'student')
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_locked_keyring_warns_and_cannot_report_saved(self):
        with patch.object(self.store, 'get_password', side_effect=RuntimeError('sensitive error content')):
            vault = core.Vault()
            self.assertIn('Linux', vault.warning)
            self.assertNotIn('sensitive error content', vault.warning)
            with self.assertRaises(RuntimeError): vault.set('sep','student','secret')
        self.assertEqual(self.store.records,{})

    def test_denied_or_silent_delete_keeps_current_account(self):
        vault = core.Vault();vault.set('sep','student','secret')
        for error in [RuntimeError('denied'), None]:
            with patch.object(self.store,'delete_password',side_effect=error):
                with self.assertRaises(RuntimeError): vault.set('sep','student','secret',False)
            self.assertEqual(vault.get('sep')['password'],'secret')
            self.assertIn('sep',core._keychain_keys())

    def test_silent_write_is_not_success(self):
        with patch.object(self.store,'set_password'):
            with self.assertRaises(RuntimeError): core.Vault().set('sep','student','secret')

    def test_invalid_record_warns_and_is_not_exposed(self):
        for value in ['not-json','[]',json.dumps({'username':'student'})]:
            self.store.records[keyring.SERVICE,'sep']=value
            vault=core.Vault()
            self.assertTrue(vault.warning)
            self.assertEqual(vault.get('sep')['password'],'')
            self.assertEqual(self.store.records[keyring.SERVICE,'sep'],value)


class BackendSelectionTests(unittest.TestCase):
    def test_only_supported_secure_backends_are_selected(self):
        def instance(module, name): return type(name,(),{'__module__':module})()
        plain=instance('keyrings.alt.file','PlaintextKeyring')
        secure=instance('keyring.backends.SecretService','Keyring')
        wallet=instance('keyring.backends.kwallet','DBusKeyring')
        for unsafe in [plain,instance('keyring.backends.null','Keyring'),instance('keyring.backends.fail','Keyring')]:
            with self.assertRaises(RuntimeError): keyring.select_backend(unsafe)
        chain=instance('keyring.backends.chainer','ChainerBackend');chain.backends=[plain,secure,wallet]
        self.assertIs(keyring.select_backend(chain),secure)
        self.assertIs(keyring.select_backend(wallet),wallet)

    def test_python_browser_paths_cover_linux_variants(self):
        paths=['/usr/bin/microsoft-edge','/usr/bin/microsoft-edge-stable','/usr/bin/google-chrome',
               '/usr/bin/google-chrome-stable','/usr/bin/chromium','/usr/bin/chromium-browser']
        with patch('ucasdesk.core.sys.platform','linux'):
            for executable in paths:
                with self.subTest(executable=executable), patch.object(Path,'is_file',lambda p:str(p).replace('\\','/')==executable):
                    self.assertEqual(str(core.browser_path()).replace('\\','/'),executable)
                    self.assertEqual(core.browser_kind(),'edge' if 'edge' in executable else 'chrome')


if __name__=='__main__': unittest.main()
