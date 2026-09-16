"""Windows tray integration test with isolated accounts, jobs, logs and HTTP port."""
import sys
import time
import tempfile
import subprocess
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtCore import QEventLoop
from ucasdesk import core, ui, jobs, api
from ucasdesk.instance import InstanceServer, server_name

app = QApplication([])
ui.load_fonts()
app.setStyleSheet(ui.STYLE)
assert QSystemTrayIcon.isSystemTrayAvailable(), 'This test needs a Windows desktop tray'
errors = []
sys.excepthook = lambda kind, value, tb: errors.append(str(value))


def wait_until(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.AllEvents, 50)
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError('Timed out')


with tempfile.TemporaryDirectory(prefix='ucas-tray-') as folder, ExitStack() as stack:
    data = Path(folder)
    for module in (core, ui, api):
        stack.enter_context(patch.object(module, 'DATA', data))
    for module in (core, ui, jobs):
        stack.enter_context(patch.object(module, 'LOGS', data))
    stack.enter_context(patch.object(ui, 'LocalAPI', lambda store, **_: api.LocalAPI(store, port=0)))
    window = ui.Window()
    instance = InstanceServer(server_name(data), window.show_window, app)
    try:
        window.show()
        app.processEvents()
        assert window.tray.isVisible() and not window.windowIcon().isNull()
        heartbeat = data / 'heartbeat.txt'
        code = ('import time\nfrom pathlib import Path\np=Path(' + repr(str(heartbeat)) + ')\n'
                'for n in range(300):\n p.write_text(str(n)); time.sleep(.1)\n')
        job = window.jobs.start('tray-test', '托盘持续运行验证', core.PYTHON, ['-c', code])
        wait_until(lambda: heartbeat.exists() and heartbeat.read_text().isdigit())
        assert '1 个任务' in window.tray.toolTip()
        window.close()
        assert not window.isVisible() and window.clock.isActive()
        before = int(heartbeat.read_text())
        wait_until(lambda: heartbeat.read_text().isdigit() and int(heartbeat.read_text()) >= before + 3)
        assert job in window.jobs.active and window.api.thread.is_alive()
        window.tray_activated(QSystemTrayIcon.Trigger)
        assert window.isVisible()
        window.showMinimized()
        wait_until(lambda: not window.isVisible())
        # A fresh process uses the same IPC mechanism as a second shortcut launch.
        child = subprocess.run([str(core.PYTHON), '-c',
            'from PySide6.QtCore import QCoreApplication; '
            'from ucasdesk.instance import activate_existing; '
            'app=QCoreApplication([]); '
            f'assert activate_existing({server_name(data)!r})'],
            cwd=core.ROOT, capture_output=True, timeout=10)
        assert child.returncode == 0, child.stderr.decode(errors='replace')
        wait_until(lambda: window.isVisible() and not window.isMinimized())
        window.show_jobs()
        assert window.nav.currentRow() == 6
        window.tray_menu.actions()[-1].trigger()
        assert not window.jobs.active
        assert window.store.list()[0]['status'] == 'stopped'
        assert not window.api.thread.is_alive() and not window.tray.isVisible()
        window.shutdown()  # Cleanup is idempotent on Qt's aboutToQuit signal.
        assert not errors, errors
        print('PASS: close/minimize preserve live job and API; tray/IPC restore; explicit exit stops job')
    finally:
        window.shutdown()
        instance.close()
