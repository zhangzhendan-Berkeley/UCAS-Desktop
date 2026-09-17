import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from PySide6.QtCore import QLockFile
from scripts.apply_update import apply


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source, self.target = self.root/'update', self.root/'app'
        for p in (self.source/'ucasdesk', self.target/'ucasdesk', self.target/'data'): p.mkdir(parents=True)
        (self.target/'app.py').write_text('# app')
        (self.target/'ucasdesk/ui.py').write_text('old')
        (self.source/'ucasdesk/ui.py').write_text('new')
        self.manifest = {'version':'test','files':{'ucasdesk/ui.py':hashlib.sha256(b'new').hexdigest()}}
        self.save()

    def save(self):
        (self.source/'update-manifest.json').write_text(json.dumps(self.manifest))

    def test_running_app_refused_and_data_preserved_when_stopped(self):
        lock = QLockFile(str(self.target/'data/app.lock'))
        self.assertTrue(lock.tryLock(100))
        try:
            with self.assertRaisesRegex(RuntimeError, '仍在运行'): apply(self.source,self.target)
            self.assertEqual((self.target/'ucasdesk/ui.py').read_text(),'old')
        finally: lock.unlock()
        (self.target/'data/accounts.dpapi').write_bytes(b'unchanged-encrypted-fixture')
        apply(self.source,self.target)
        self.assertEqual((self.target/'ucasdesk/ui.py').read_text(),'new')
        self.assertEqual((self.target/'data/accounts.dpapi').read_bytes(),b'unchanged-encrypted-fixture')
        backups = list((self.target/'data/update-backups').glob('*/ucasdesk/ui.py'))
        self.assertEqual(backups[0].read_text(),'old')

    def test_bad_hash_and_data_paths_rejected_before_mutation(self):
        self.manifest['files']['ucasdesk/ui.py']='bad';self.save()
        with self.assertRaises(ValueError): apply(self.source,self.target)
        self.assertEqual((self.target/'ucasdesk/ui.py').read_text(),'old')
        self.manifest['files']={'data/accounts.dpapi':'bad'};self.save()
        with self.assertRaises(ValueError): apply(self.source,self.target)
