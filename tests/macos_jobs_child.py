"""Child process used by the macOS job-runner smoke test."""
import json
import sys
import time
import subprocess

payload = json.loads(sys.stdin.read() or '{}')
print(json.dumps({'echo': payload.get('message'), 'secret': payload.get('secret')}, ensure_ascii=False), flush=True)
if '--sleep' in sys.argv:
    if '--tree' in sys.argv:
        worker = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
        print(json.dumps({'child_pid': worker.pid}), flush=True)
    print('started', flush=True)
    time.sleep(60)
