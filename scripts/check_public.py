"""Check the exact Git index before committing; never print matched secrets."""
import re
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')
blocked_roots = {'data', 'logs', 'vendor', 'updates', '.venv', '.runtime', 'node_modules'}
patterns = {
    'GitHub credential': rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})',
    'private key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'developer home path': rb'[A-Za-z]:[\\/](?:Users|Desktop)[\\/]',
}
failures = []
for name in filter(None, names):
    path = Path(name)
    if (path.parts[0] in blocked_roots or path.suffix.lower() in
            {'.exe', '.dpapi', '.sqlite3', '.db', '.pfx', '.pem', '.key', '.zip'} or
            name == 'adapters/mooc_helpers.mjs' or path.name.startswith('.env')):
        failures.append((name, 'runtime/private/external file'))
    content = subprocess.check_output(['git', 'show', ':' + name], cwd=ROOT)
    if len(content) > 2_000_000:
        failures.append((name, 'unexpectedly large file'))
    if path.suffix.lower() not in {'.png', '.ico'}:
        for label, pattern in patterns.items():
            if re.search(pattern, content):
                failures.append((name, label))
if failures:
    for name, reason in failures:
        print(f'REVIEW REQUIRED: {name} ({reason})')
    sys.exit(1)
print(f'PASS: {len(list(filter(None, names)))} staged files; no blocked paths or credential patterns.')
print('This scan complements manual review; it is not a guarantee that arbitrary text contains no secrets.')
