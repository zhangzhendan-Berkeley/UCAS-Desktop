import io,json,zipfile,hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from ucasdesk.portable import install_module,ready
from scripts.migrate_data import migrate

class InstallRecoveryTests(unittest.TestCase):
 def archive(self,complete=True):
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:
   z.writestr('root/main.py','fresh')
   if complete:z.writestr('root/course_flow.py','flow')
  return out.getvalue()
 def test_failed_prepare_keeps_old_and_success_backs_up(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);target=root/'vendor/selection';target.mkdir(parents=True);(target/'custom.txt').write_text('keep old')
   (root/'data').mkdir();(root/'data/account.fixture').write_text('private fixture')
   module={'id':'selection','name':'fixture','path':'vendor/selection','commit':'a'*40,'source':'https://github.com/o/r.git'}
   for complete in (False,True):
    content=self.archive(complete);manifest={'selection':{'commit':module['commit'],'archive_sha256':hashlib.sha256(content).hexdigest()}}
    with patch('ucasdesk.portable.download',return_value=content):
     if complete:install_module(root,module,manifest,log=lambda *_:None)
     else:
      with self.assertRaises(RuntimeError):install_module(root,module,manifest,log=lambda *_:None)
      self.assertEqual((target/'custom.txt').read_text(),'keep old')
   self.assertTrue(ready(root,module));self.assertEqual((root/'data/account.fixture').read_text(),'private fixture')
   self.assertEqual(len(list((root/'data/module-backups').rglob('custom.txt'))),1)
   with patch('ucasdesk.portable.download',side_effect=AssertionError('no re-download')):install_module(root,module,manifest,log=lambda *_:None)
 def test_migration_preserves_old_and_backs_up_destination(self):
  with tempfile.TemporaryDirectory() as tmp:
   source=Path(tmp)/'old';target=Path(tmp)/'new'
   for root in (source,target):
    (root/'data').mkdir(parents=True);(root/'app.py').write_text('fixture')
   (source/'data/settings.json').write_text('old configuration');(target/'data/settings.json').write_text('new configuration')
   self.assertEqual(migrate(source,target),1)
   self.assertEqual((source/'data/settings.json').read_text(),'old configuration')
   self.assertEqual((target/'data/settings.json').read_text(),'old configuration')
   self.assertEqual(next((target/'data/migration-backups').rglob('settings.json')).read_text(),'new configuration')
   with self.assertRaises(ValueError):migrate(source,source)

if __name__=='__main__':unittest.main()
