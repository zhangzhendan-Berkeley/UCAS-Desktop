"""Native macOS Keychain access: secrets never appear in subprocess arguments."""
import json
import sys

SERVICE = 'UCAS-Desktop'


def backend():
    if sys.platform != 'darwin':
        raise RuntimeError('此安全存储仅支持 macOS。')
    try:
        # Select the native backend explicitly; never fall back to a file backend.
        from keyring.backends.macOS import Keyring
        return Keyring()
    except ImportError:
        raise RuntimeError('缺少 macOS 钥匙串组件，请重新运行 scripts/setup.py。') from None


def get(key):
    try:
        value = backend().get_password(SERVICE, key)
    except Exception as exc:
        raise RuntimeError(f'无法读取 macOS 钥匙串（{type(exc).__name__}），请解锁钥匙串并允许访问后重试。') from None
    if value is None:
        return None
    try:
        result = json.loads(value)
        if not isinstance(result, dict): raise ValueError()
        return result
    except (ValueError, TypeError):
        raise RuntimeError('macOS 钥匙串记录格式不正确；原记录未修改。') from None


def set(key, value):
    try:
        backend().set_password(SERVICE, key, json.dumps(value, ensure_ascii=False))
    except Exception as exc:
        raise RuntimeError(f'无法保存 macOS 钥匙串（{type(exc).__name__}），请解锁并允许访问后重试。') from None


def delete(key):
    try:
        store = backend()
        if store.get_password(SERVICE, key) is not None:
            store.delete_password(SERVICE, key)
    except Exception as exc:
        raise RuntimeError(f'未能删除已保存的 macOS 账号（{type(exc).__name__}），请解锁钥匙串后重试。') from None
