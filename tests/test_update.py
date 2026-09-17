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

    def test_missing_lazy_import_dependency_rejected_before_mutation(self):
        code = 'def start_job():\n    from .portable import ready\n'
        (self.source/'ucasdesk/ui.py').write_text(code)
        self.manifest['files']['ucasdesk/ui.py'] = hashlib.sha256((self.source/'ucasdesk/ui.py').read_bytes()).hexdigest()
        self.save()
        with self.assertRaisesRegex(ValueError, 'portable.py'): apply(self.source, self.target)
        self.assertEqual((self.target/'ucasdesk/ui.py').read_text(), 'old')
        (self.source/'ucasdesk/portable.py').write_text('def ready(): pass')
        self.manifest['files']['ucasdesk/portable.py'] = hashlib.sha256(b'def ready(): pass').hexdigest()
        self.save()
        apply(self.source, self.target)
        self.assertTrue((self.target/'ucasdesk/portable.py').exists())

    def test_complete_overlay_includes_unchanged_dependencies(self):
        from scripts.build_update import prepare
        root = self.root/'source';(root/'ucasdesk').mkdir(parents=True)
        for name in ('ui.py','portable.py'): (root/'ucasdesk'/name).write_text('# source')
        for name in ('README.md','使用指南.md'): (root/name).write_text('fixture')
        manifest = prepare(root, self.root/'prepared', 'test')
        self.assertIn('ucasdesk/portable.py', manifest)
