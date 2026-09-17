"""Native macOS Keychain round-trip in a unique disposable service."""
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ucasdesk import macos_keychain

if sys.platform != 'darwin': raise SystemExit('Run this self-test on macOS.')
macos_keychain.SERVICE = 'UCAS-Desktop-SelfTest-' + uuid.uuid4().hex
try:
    expected = {'username':'self-test', 'password':'disposable-test-value'}
    macos_keychain.set('profile', expected)
    assert macos_keychain.get('profile') == expected
    macos_keychain.delete('profile')
    assert macos_keychain.get('profile') is None
    print('Native Keychain save/read/delete: PASS')
finally:
    macos_keychain.delete('profile')
