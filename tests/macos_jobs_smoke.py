"""macOS job-runner smoke test: start a child job, read its log, stop one mid-run."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication  # noqa: E402
from ucasdesk.core import Store  # noqa: E402
from ucasdesk.jobs import Jobs  # noqa: E402

CHILD = ROOT / 'tests/macos_jobs_child.py'


class FakeVault:
    def get(self, key):
        return {'username': '', 'password': ''}

    def secret_values(self):
        return ['top-secret-value']


def wait_for(predicate, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    return False


def main():
    app = QCoreApplication(sys.argv)
    with tempfile.TemporaryDirectory() as tmp:
        import ucasdesk.jobs as jobs_module
        import ucasdesk.core as core_module
        jobs_module.LOGS = Path(tmp)
        store = Store(Path(tmp) / 'jobs.db')
        jobs = Jobs(store, FakeVault())
        job_id = jobs.start('iclass', 'macOS 子进程测试', sys.executable, [CHILD],
                            {'message': 'hello-from-macos', 'secret': 'top-secret-value'})
        finished = wait_for(lambda: not jobs.active and store.list()[0]['status'] != 'running')
        status = store.list()[0]['status']
        log = (Path(tmp) / f'{job_id}.log').read_text(encoding='utf-8')
        print(json.dumps({'finished': finished, 'status': status,
                          'log': log, 'redacted': 'top-secret-value' not in log,
                          'saw_payload': 'hello-from-macos' in log}, ensure_ascii=False))

        slow = jobs.start('mooc', 'macOS 停止测试', sys.executable,
                          [CHILD, '--sleep'], {'message': 'sleeping', 'secret': 'top-secret-value'})
        started = wait_for(lambda: 'started' in (Path(tmp) / f'{slow}.log').read_text(encoding='utf-8') if (Path(tmp) / f'{slow}.log').exists() else False)
        jobs.stop(slow)
        stopped = wait_for(lambda: not jobs.active)
        print(json.dumps({'sleep_job_started': started, 'stopped': stopped,
                          'status': [row for row in store.list() if row['id'] == slow][0]['status']}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
