import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
from pathlib import Path
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication, QDialog, QTableWidget, QPushButton
from PySide6.QtCore import QEventLoop, QTimer
import json
from ucasdesk.ui import Window, load_fonts, style_sheet
from ucasdesk.core import ROOT, LOGS, PYTHON

app = QApplication([])
app.setStyle('Fusion')
load_fonts()
app.setStyleSheet(style_sheet())
window = Window()
window.resize(1380, 910)
window.show()
created = []
slot_errors = []
sys.excepthook = lambda kind, value, tb: slot_errors.append(str(value))

def wait_until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents(QEventLoop.AllEvents, 100)
        if predicate(): return
        time.sleep(.02)
    raise AssertionError('UI operation timed out')

try:
    app.processEvents()
    window.grab().save(str(ROOT / 'docs/desktop-home.png'))
    window.nav.setCurrentRow(4)
    wait_until(lambda: window.planner is not None)
    assert len(window.planner.db.get_all_courses()) > 1000
    assert window.planner.campus_combo.currentData() == 'H'
    app.processEvents()
    window.grab().save(str(ROOT / 'docs/desktop-planner.png'))
    print('Planner courses:', len(window.planner.db.get_all_courses()))
    window.receive_output('fixture', json.dumps({'event': 'lecture.science-schedule', 'rows': [
        {'title': 'Fixture lecture', 'time': '2026-10-16 19:00-20:30', 'location': 'Room',
         'start': '2026-10-16 19:00:00', 'end': '2026-10-16 20:30:00'}]}) + '\n')
    assert window.science_choose.isEnabled()
    window.lecture_id.setText('7654321')
    def select_fixture():
        dialog = window.findChild(QDialog)
        dialog.findChild(QTableWidget).selectRow(0)
        next(b for b in dialog.findChildren(QPushButton) if b.text() == '填入选中场次时间').click()
    QTimer.singleShot(50, select_fixture)
    window.choose_science_lecture()
    assert window.lecture_start.dateTime().toString('yyyy-MM-dd HH:mm:ss') == '2026-10-16 19:00:00'
    assert window.lecture_end.dateTime().toString('yyyy-MM-dd HH:mm:ss') == '2026-10-16 20:30:00'
    assert window.lecture_id.text() == '', 'Never carry a previous lecture QR into a new selected event'
    assert window.science_match.isEnabled()
    job = window.jobs.start('offline-test', '离线验证：中文输出', PYTHON, ['-c', 'print("中文输出验证")'])
    created.append(job)
    window.nav.setCurrentRow(6)
    window.select_job(job)
    wait_until(lambda: job not in window.jobs.active)
    assert '中文输出验证' in (LOGS / f'{job}.log').read_text(encoding='utf-8')
    assert next(x for x in window.store.list() if x['id'] == job)['status'] == 'completed'
    job = window.jobs.start('offline-test', '离线验证：停止进程', PYTHON, ['-c', 'import time; print("started",flush=True); time.sleep(60)'])
    created.append(job)
    wait_until(lambda: window.jobs.active[job]['process'].processId() > 0)
    window.jobs.stop(job)
    wait_until(lambda: job not in window.jobs.active)
    assert next(x for x in window.store.list() if x['id'] == job)['status'] == 'stopped'
    assert not slot_errors, slot_errors
    print('UI, Chinese process output, and stop action: PASS')
finally:
    window.close()
    for job in created:
        with window.store.connect() as db: db.execute('DELETE FROM jobs WHERE id=?', (job,))
        path = LOGS / f'{job}.log'
        if path.exists(): path.unlink()
