"""Secret Service / KWallet integration with a disposable service and no real accounts."""
import sys
import tempfile
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucasdesk import core, linux_keyring

if not sys.platform.startswith('linux'):
    raise SystemExit('Run this check on Linux with an unlocked system keyring.')
linux_keyring.SERVICE = 'UCAS-Desktop-SelfTest-' + uuid.uuid4().hex
with tempfile.TemporaryDirectory() as tmp:
    core.DATA = Path(tmp)
    try:
        vault = core.Vault()
        assert not vault.warning, vault.warning
        vault.set('sep', 'fixture-student', 'disposable-test-secret')
        vault.set('addon', 'fixture-addon', 'disposable-addon-secret')
        restored = core.Vault()
        assert restored.get('sep')['password'] == 'disposable-test-secret'
        assert restored.get('addon')['username'] == 'fixture-addon'
        restored.set('sep', 'fixture-student', 'memory-only', False)
        assert core.Vault().get('sep')['password'] == ''
        assert list(core.DATA.iterdir()) == [], 'Credentials must not be written to application data files'
        print('Linux system keyring save/read/restart/forget: PASS')
    finally:
        for key in ('sep', 'addon', '__index'):
            linux_keyring.delete(key)
