"""Linux credentials use a supported system keyring, never a plaintext fallback."""
from functools import lru_cache
import json
import sys

SERVICE = 'UCAS-Desktop'
_ALLOWED = {
    ('keyring.backends.SecretService', 'Keyring'),
    ('keyring.backends.kwallet', 'DBusKeyring'),
    ('keyring.backends.kwallet', 'DBusKeyringKWallet4'),
}


def _identity(value):
    return type(value).__module__, type(value).__name__


def select_backend(selected):
    candidates = selected.backends if _identity(selected) == ('keyring.backends.chainer', 'ChainerBackend') else [selected]
    for candidate in candidates:
        if _identity(candidate) in _ALLOWED:
            return candidate
    raise RuntimeError('请配置并解锁 Linux Secret Service / KWallet 系统密钥环；不支持明文文件或空后端。')


@lru_cache(maxsize=1)
def backend():
    if not sys.platform.startswith('linux'):
        raise RuntimeError('此安全存储仅支持 Linux。')
    try:
        import keyring
        return select_backend(keyring.get_keyring())
    except Exception as exc:
        raise RuntimeError(f'无法访问 Linux 系统密钥环（{type(exc).__name__}）；请检查 Secret Service / KWallet、D-Bus 会话并解锁，不会回退到明文保存。') from None


def get(key):
    try:
        value = backend().get_password(SERVICE, key)
    except Exception as exc:
        raise RuntimeError(f'无法读取 Linux 系统密钥环（{type(exc).__name__}）；请检查 D-Bus 会话和已解锁的 Secret Service / KWallet。') from None
    if value is None:
        return None
    try:
        result = json.loads(value)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise RuntimeError('Linux 密钥环记录格式不正确；原记录未修改。') from None


def set(key, value):
    try:
        store = backend()
        payload = json.dumps(value, ensure_ascii=False)
        store.set_password(SERVICE, key, payload)
        if store.get_password(SERVICE, key) != payload:
            raise RuntimeError('write verification failed')
    except Exception as exc:
        raise RuntimeError(f'未能确认 Linux 账号已保存（{type(exc).__name__}），请检查并解锁系统密钥环后重试。') from None


def delete(key):
    try:
        store = backend()
        if store.get_password(SERVICE, key) is not None:
            store.delete_password(SERVICE, key)
            if store.get_password(SERVICE, key) is not None:
                raise RuntimeError('delete verification failed')
    except Exception as exc:
        raise RuntimeError(f'未能删除 Linux 密钥环中的账号（{type(exc).__name__}），请检查并解锁后重试。') from None
