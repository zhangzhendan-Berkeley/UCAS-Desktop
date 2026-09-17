"""UI fixtures must never read or overwrite a real macOS user's Keychain."""
from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def isolated_keychain():
    records = {}
    with patch('ucasdesk.core._keychain_get', side_effect=records.get), \
         patch('ucasdesk.core._keychain_set', side_effect=records.__setitem__), \
         patch('ucasdesk.core._keychain_delete', side_effect=lambda key: records.pop(key, None)):
        yield
