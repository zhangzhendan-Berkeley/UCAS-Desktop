"""Child process used by the macOS job-runner smoke test."""
import json
import sys
import time

payload = json.loads(sys.stdin.read() or '{}')
print(json.dumps({'echo': payload.get('message'), 'secret': payload.get('secret')}, ensure_ascii=False), flush=True)
if '--sleep' in sys.argv:
    print('started', flush=True)
    time.sleep(60)
