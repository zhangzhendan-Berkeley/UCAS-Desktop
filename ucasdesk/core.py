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
import subprocess
from datetime import datetime
from typing import Protocol

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
LOGS = ROOT / 'logs'
VENDOR = ROOT / 'vendor'
PYTHON = ROOT / '.venv/Scripts/python.exe'
# An explicit override or a system Node installation; no developer-machine paths.
NODE = Path(os.environ.get('UCAS_NODE') or shutil.which('node') or 'node.exe')
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
        if self.path.exists():
            try:
                self.accounts = json.loads(protect(self.path.read_bytes(), decrypt=True))
            except Exception:
                self.warning = '无法解密已保存账号，请在本机重新输入。原文件已保留。'

    def get(self, key):
        return self.accounts.get(key, {'username': '', 'password': ''})

    def set(self, key, username, password, remember=False):
        self.accounts[key] = {'username': username.strip(), 'password': password}
        stored = {}
        if self.path.exists():
            try:
                stored = json.loads(protect(self.path.read_bytes(), decrypt=True))
            except Exception:
                raise RuntimeError('旧账号文件不能解密，请先备份并移走 data/accounts.dpapi')
        if remember:
            stored[key] = self.accounts[key]
        else:
            stored.pop(key, None)
        temp = self.path.with_suffix('.tmp')
        temp.write_bytes(protect(json.dumps(stored).encode()))
        os.replace(temp, self.path)

    def secret_values(self):
        return [v for a in self.accounts.values() for v in a.values() if v]


class Store:
    def __init__(self, path=None):
        self.path = path or DATA / 'tasks.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, module TEXT, title TEXT, status TEXT, created TEXT, updated TEXT, log TEXT)')
            db.execute("UPDATE jobs SET status='interrupted' WHERE status IN ('running','stopping')")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

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
    candidates = [
        Path(os.environ.get('PROGRAMFILES(X86)', 'C:/Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe',
        Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe',
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise RuntimeError('未找到 Edge 或 Chrome，请安装其中一种浏览器。')


def child_env(extra=None):
    env = dict(os.environ)
    env.update({'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1', 'NODE_TLS_REJECT_UNAUTHORIZED': '1', 'NEXT_TELEMETRY_DISABLED': '1', 'MSEDGEDRIVER_TELEMETRY_OPTOUT': '1', 'SE_AVOID_STATS': 'true', 'NO_COLOR': '1'})
    env['PATH'] = str(NODE.parent) + os.pathsep + str(PYTHON.parent) + os.pathsep + env.get('PATH', '')
    env['NO_PROXY'] = ','.join(filter(None, [env.get('NO_PROXY', ''), 'localhost', '127.0.0.1', '::1']))
    env['no_proxy'] = env['NO_PROXY']
    env.update(extra or {})
    return env


def git_output(args, cwd):
    return subprocess.check_output(['git', *args], cwd=str(cwd), timeout=60,
                                   creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8').strip()


def check_updates():
    results = []
    for module in read_json(ROOT / 'modules.json', []):
        repo_dir = ROOT / module['path']
        try:
            remote = git_output(['ls-remote', module['source'], 'HEAD'], ROOT).split()[0]
            local = git_output(['rev-parse', 'HEAD'], repo_dir)
            results.append({'id': module['id'], 'name': module['name'], 'installed': local, 'latest': remote, 'update': local != remote})
        except Exception as exc:
            results.append({'id': module['id'], 'name': module['name'], 'error': str(exc)[:200]})
    write_json(DATA / 'updates.json', results)
    return results


def stage_updates():
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
        target.mkdir(parents=True, exist_ok=True)
        if not (target / '.git').exists():
            git_output(['init'], target)
            git_output(['remote', 'add', 'origin', item['source']], target)
        git_output(['fetch', '--depth', '1', 'origin', sha], target)
        git_output(['checkout', '--detach', 'FETCH_HEAD'], target)
        if git_output(['rev-parse', 'HEAD'], target) != sha:
            raise RuntimeError('暂存版本校验失败')
        staged.append(str(target))
    return staged
