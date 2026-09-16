import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile
from ucasdesk.portable import unpack_repo, apply_patch_file, archive_url, download, ready


class PortableTests(unittest.TestCase):
    def test_zip_traversal_rejected(self):
        for name in ('root/../../outside', '/absolute.txt', 'root/C:/outside', 'root/..\\outside'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, 'w') as z:
                    z.writestr(name, 'bad')
                with self.assertRaises(ValueError): unpack_repo(stream.getvalue(), Path(tmp))

    def test_strict_multi_file_patch_and_wrong_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'one.txt').write_text('hello\nworld\n')
            (root / 'two.txt').write_text('old\n')
            patch_file = root / 'fix.patch'
            patch_file.write_text('--- a/one.txt\n+++ b/one.txt\n@@ -1,2 +1,2 @@\n hello\n-world\n+new\n--- a/two.txt\n+++ b/two.txt\n@@ -1 +1 @@\n-old\n+replaced\n')
            apply_patch_file(root, patch_file)
            self.assertEqual((root / 'one.txt').read_text(), 'hello\nnew\n')
            self.assertEqual((root / 'two.txt').read_text(), 'replaced\n')
            with self.assertRaises(ValueError): apply_patch_file(root, patch_file)

    def test_archive_fixed_revision_and_completion_marker(self):
        module = {'id': 'lecture', 'path': 'vendor/lecture', 'source': 'https://github.com/owner/repo.git', 'commit': 'a' * 40}
        self.assertEqual(archive_url(module), 'https://codeload.github.com/owner/repo/zip/' + 'a' * 40)
        with self.assertRaises(ValueError): archive_url(module | {'commit': '../latest'})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / module['path']
            target.mkdir(parents=True)
            self.assertFalse(ready(root, module))
            (target / 'dist/src').mkdir(parents=True)
            (target / 'dist/src/workflow.js').write_text('')
            self.assertTrue(ready(root, module))

    def test_hash_mismatch_fails_closed(self):
        with patch('requests.Session') as session:
            session.return_value.__enter__.return_value.get.return_value.content = b'wrong'
            with self.assertRaises(ValueError):
                download('https://example.com/source.zip', hashlib.sha256(b'expected').hexdigest())


if __name__ == '__main__': unittest.main()
