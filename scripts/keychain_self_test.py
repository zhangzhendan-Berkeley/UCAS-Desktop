"""Manual check: does macOS keychain save/read/delete work for this app?"""
import json
import subprocess

SERVICE = 'UCAS-Desktop-KeychainSelfTest'
ACCOUNT = 'sep'


def run(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=15)


result = run(['security', 'add-generic-password', '-U', '-s', SERVICE, '-a', ACCOUNT, '-w',
              json.dumps({'username': 'self-test', 'password': 'self-test-secret'}, ensure_ascii=False)])
print('add returncode', result.returncode, result.stderr.strip()[:200])
read = run(['security', 'find-generic-password', '-s', SERVICE, '-a', ACCOUNT, '-w'])
print('read returncode', read.returncode, read.stdout.strip()[:200])
delete = run(['security', 'delete-generic-password', '-s', SERVICE, '-a', ACCOUNT])
print('delete returncode', delete.returncode, delete.stderr.strip()[:200])
