from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
from contextlib import contextmanager
import subprocess
import sys
from datetime import datetime
from typing import Protocol

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
LOGS = ROOT / 'logs'
VENDOR = ROOT / 'vendor'
PYTHON = ROOT / 'runtime/python/python.exe'
if not PYTHON.is_file():
    PYTHON = ROOT / '.venv/Scripts/python.exe'
if not PYTHON.is_file():
    PYTHON = ROOT / '.venv/bin/python'
if not PYTHON.is_file():
    PYTHON = Path(sys.executable)
# An explicit override or a system Node installation; no developer-machine paths.
NODE = ROOT / 'runtime/node/node.exe'
if not NODE.is_file():
    NODE = Path(os.environ.get('UCAS_NODE') or shutil.which('node') or 'node')
for directory in (DATA, LOGS):
    directory.mkdir(exist_ok=True)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path: Path, value):
    path.parent.mkdir(exist_ok=True, parents=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def redact(text: str, values=()) -> str:
    for value in values:
        if value and len(str(value)) >= 3:
            text = text.replace(str(value), '[REDACTED]')
    text = re.sub(r'(?i)(password|sessionid|authorization|jtoken|enc|token|ticket)([=\s:"\x27]+)[^\s&,"\x27}]+', r'\1\2[REDACTED]', text)
    text = re.sub(r'(?i)(/portal/site/[^\s"<>]*)', lambda m: re.sub(r'[a-f0-9]{24,}', '[REDACTED]', m.group(0), flags=re.I), text)
    # Older adapters included the whole SEP profile card in error messages.
    text = re.sub(r'(?im)(\bbody=)[^\r\n]*', r'\1[页面正文已省略]', text)
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def _keychain_get(key):
    if sys.platform.startswith('linux'):
        from .linux_keyring import get
    else:
        from .macos_keychain import get
    return get(key)


def _keychain_set(key, value):
    if sys.platform.startswith('linux'):
        from .linux_keyring import set
    else:
        from .macos_keychain import set
    set(key, value)


def _keychain_delete(key):
    if sys.platform.startswith('linux'):
        from .linux_keyring import delete
    else:
        from .macos_keychain import delete
    delete(key)


def _child_options():
    flag = getattr(subprocess, 'CREATE_NO_WINDOW', None)
    return {'creationflags': flag} if os.name == 'nt' and flag is not None else {}


KEY_INDEX = '__index'


def _keychain_keys():
    index = _keychain_get(KEY_INDEX)
    if index is None: return []
    keys = index.get('keys')
    if not isinstance(keys, list) or any(not isinstance(k, str) or k == KEY_INDEX for k in keys):
        raise RuntimeError('系统密钥环账号索引格式不正确；原记录未修改。')
    return list(dict.fromkeys(keys))


def _keychain_remember(key, remember):
    keys = [k for k in _keychain_keys() if k != key]
    if remember:
        keys.append(key)
    _keychain_set(KEY_INDEX, {'keys': keys})


class Blob(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def protect(data: bytes, decrypt=False) -> bytes:
    if os.name != 'nt':
        raise RuntimeError('账号保存仅支持 Windows DPAPI')
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    dll = ctypes.WinDLL('crypt32', use_last_error=True)
    func = dll.CryptUnprotectData if decrypt else dll.CryptProtectData
    func.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    func.restype = wintypes.BOOL
    if not func(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(target.pbData, ctypes.c_void_p))


class Vault:
    def __init__(self):
        self.path = DATA / 'accounts.dpapi'
        self.accounts = {}
        self.warning = ''
        if sys.platform == 'darwin' or sys.platform.startswith('linux'):
            try:
                # Known profiles also recover accounts written before an index update failed.
                for key in dict.fromkeys(_keychain_keys() + ['sep', 'iclass', 'email']):
                    account = _keychain_get(key)
                    if account is None: continue
                    if not all(isinstance(account.get(k), str) for k in ('username', 'password')):
                        raise RuntimeError('系统密钥环账号格式不正确；原记录未修改。')
                    self.accounts[key] = account
            except RuntimeError as exc:
                self.warning = str(exc)
            if self.path.exists():
                self.warning += ' 检测到 Windows 账号文件；当前系统无法读取，请重新输入账号。'
        elif self.path.exists():
            try:
                self.accounts = json.loads(protect(self.path.read_bytes(), decrypt=True))
            except Exception:
                self.warning = '无法解密已保存账号，请在本机重新输入。原文件已保留。'

    def get(self, key):
        return self.accounts.get(key, {'username': '', 'password': ''})

    def set(self, key, username, password, remember=True):
        account = {'username': username.strip(), 'password': password}
        if sys.platform == 'darwin' or sys.platform.startswith('linux'):
            _keychain_keys()  # Fail before changing records if the keychain is locked/unreadable.
            if remember:
                _keychain_set(key, account)
            else:
                _keychain_delete(key)
            _keychain_remember(key, remember)
            self.accounts[key] = account
            return
        stored = {}
        if self.path.exists():
            try:
                stored = json.loads(protect(self.path.read_bytes(), decrypt=True))
            except Exception:
                raise RuntimeError('旧账号文件不能解密，请先备份并移走 data/accounts.dpapi')
        if remember:
            stored[key] = account
        else:
            stored.pop(key, None)
        temp = self.path.with_suffix('.tmp')
        temp.write_bytes(protect(json.dumps(stored).encode()))
        os.replace(temp, self.path)
        self.accounts[key] = account

    def secret_values(self):
        return [v for a in self.accounts.values() for v in a.values() if v]


class Store:
    def __init__(self, path=None):
        self.path = path or DATA / 'tasks.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, module TEXT, title TEXT, status TEXT, created TEXT, updated TEXT, log TEXT)')
            db.execute("UPDATE jobs SET status='interrupted' WHERE status IN ('running','stopping')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, module, title):
        job_id = secrets.token_hex(6)
        now = datetime.now().isoformat(timespec='seconds')
        log = str(LOGS / f'{job_id}.log')
        with self.connect() as db:
            db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)', (job_id, module, title, 'running', now, now, log))
        return job_id

    def status(self, job_id, status):
        with self.connect() as db:
            db.execute('UPDATE jobs SET status=?, updated=? WHERE id=?', (status, datetime.now().isoformat(timespec='seconds'), job_id))

    def list(self):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 200')]


class Connector(Protocol):
    """Connector API v1: return data only; callers own scheduling and UI."""
    api_version: int
    def health(self) -> dict: ...
    def execute(self, action: str, payload: dict) -> dict: ...


def browser_path():
    if sys.platform == 'darwin':
        candidates = [
            Path('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'),
            Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
            Path.home() / 'Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
            Path.home() / 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        ]
    elif sys.platform.startswith('linux'):
        candidates = [Path('/usr/bin/microsoft-edge'), Path('/usr/bin/microsoft-edge-stable'), Path('/usr/bin/google-chrome'), Path('/usr/bin/google-chrome-stable'), Path('/usr/bin/chromium'), Path('/usr/bin/chromium-browser')]
    else:
        candidates = [
            Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe',
            Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Microsoft/Edge/Application/msedge.exe',
            Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft/Edge/Application/msedge.exe',
            Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
            Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Google/Chrome/Application/chrome.exe',
            Path(os.environ.get('LOCALAPPDATA', '')) / 'Google/Chrome/Application/chrome.exe',
        ]
    for path in candidates:
        if path.is_file():
            return path
    raise RuntimeError('未找到 Edge、Chrome 或 Linux Chromium，请安装对应浏览器。')


def browser_kind():
    """'edge' when Microsoft Edge is installed, otherwise 'chrome'."""
    return 'edge' if 'edge' in browser_path().name.lower() else 'chrome'


def browser_label():
    """Display name of the browser this machine will drive."""
    return 'Microsoft Edge' if browser_kind() == 'edge' else 'Google Chrome'


def browser_options(profile=None):
    """Selenium options for the installed browser; callers add task-specific flags."""
    from selenium import webdriver
    options = webdriver.EdgeOptions() if browser_kind() == 'edge' else webdriver.ChromeOptions()
    options.binary_location = str(browser_path())
    options.add_argument('--no-first-run')
    options.page_load_strategy = 'eager'
    if profile:
        options.add_argument('--user-data-dir=' + str(profile))
    return options


def driver_service(log_path, **kwargs):
    """Selenium service for the installed browser. The console-hiding flag is Windows-only."""
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.edge.service import Service as EdgeService
    service = (EdgeService if browser_kind() == 'edge' else ChromeService)(log_output=str(log_path), **kwargs)
    if os.name == 'nt':
        service.creation_flags = 0x08000000
    return service


def browser_driver(options, service):
    from selenium import webdriver
    factory = webdriver.Edge if browser_kind() == 'edge' else webdriver.Chrome
    return factory(options=options, service=service)


def child_env(extra=None):
    env = dict(os.environ)
    env.update({'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1', 'NODE_TLS_REJECT_UNAUTHORIZED': '1', 'NEXT_TELEMETRY_DISABLED': '1', 'MSEDGEDRIVER_TELEMETRY_OPTOUT': '1', 'SE_AVOID_STATS': 'true', 'NO_COLOR': '1', 'UCAS_PYTHON': str(PYTHON)})
    env['PATH'] = str(NODE.parent) + os.pathsep + str(PYTHON.parent) + os.pathsep + env.get('PATH', '')
    env['NO_PROXY'] = ','.join(filter(None, [env.get('NO_PROXY', ''), 'localhost', '127.0.0.1', '::1']))
    env['no_proxy'] = env['NO_PROXY']
    env.update(extra or {})
    return env


def git_output(args, cwd):
    return subprocess.check_output(['git', *args], cwd=str(cwd), timeout=60,
                                   encoding='utf-8', **_child_options()).strip()


def check_updates():
    from .portable import download, ready
    results = []
    for module in read_json(ROOT / 'modules.json', []):
        repo_dir = ROOT / module['path']
        try:
            repo = module['source'].removeprefix('https://github.com/').removesuffix('.git')
            remote = json.loads(download(f'https://api.github.com/repos/{repo}/commits?per_page=1'))[0]['sha']
            local = read_json(repo_dir / '.ucas-source.json', {}).get('commit', module['commit']) if ready(ROOT, module) else None
            results.append({'id': module['id'], 'name': module['name'], 'installed': local, 'latest': remote, 'update': local != remote})
        except Exception as exc:
            results.append({'id': module['id'], 'name': module['name'], 'error': str(exc)[:200]})
    write_json(DATA / 'updates.json', results)
    return results


def stage_updates():
    from .portable import download, archive_url, unpack_repo
    results = read_json(DATA / 'updates.json', [])
    manifest = {m['id']: m for m in read_json(ROOT / 'modules.json', [])}
    staged = []
    for result in results:
        if not result.get('update'):
            continue
        item = manifest[result['id']]
        sha = result['latest']
        if not re.fullmatch(r'[0-9a-f]{40}', sha):
            raise ValueError('非法提交哈希')
        target = ROOT / 'updates' / item['id'] / sha
        if target.exists():
            staged.append(str(target))
            continue
        import tempfile
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.download-', dir=target.parent) as temporary:
            source = Path(temporary) / 'source'
            unpack_repo(download(archive_url(item | {'commit': sha})), source)
            write_json(source / '.ucas-source.json', {'commit': sha, 'source': item['source']})
            source.rename(target)
        staged.append(str(target))
    return staged
