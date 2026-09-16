"""Offline profile persistence and checked-only enrollment/planner integration."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt, QEventLoop
from PySide6.QtWidgets import QApplication
from ucasdesk.ui import Window, STYLE, load_fonts
from ucasdesk.automation import Automation
from ucasdesk.core import ROOT, Vault, Store

app = QApplication([])
load_fonts()
app.setStyleSheet(STYLE)

with tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
    planner = directory / 'planner'
    planner.mkdir()
    codes = [f'180086081200P100{i}H' for i in range(1, 4)]
    with closing(sqlite3.connect(planner / 'courses.db')) as db, db:
        db.execute('CREATE TABLE courses(id INTEGER PRIMARY KEY, course_name TEXT, credits TEXT, hours TEXT, course_code TEXT)')
        db.execute('CREATE TABLE course_schedules(course_id INTEGER, day_of_week INTEGER, time_slots TEXT, location TEXT, weeks TEXT, semester TEXT)')
        for i, code in enumerate(codes, 1):
            db.execute('INSERT INTO courses VALUES(?,?,?,?,?)', (i, '离线测试课程' + str(i), '2', '40', code))
            db.execute('INSERT INTO course_schedules VALUES(?,?,?,?,?,?)', (i, i, '1、2', '雁栖湖教一楼', '1-16', '2026年秋季学期'))
    def engine(jobs, vault, parent):
        value = Automation(jobs, vault, parent, directory=directory)
        value.timer.stop()
        return value
    with patch('ucasdesk.ui.DATA', directory), patch('ucasdesk.core.DATA', directory), \
         patch('ucasdesk.ui.Store', lambda: Store(directory / 'tasks.db')), \
         patch('ucasdesk.ui.Automation', engine), patch('ucasdesk.ui.LocalAPI', side_effect=OSError('offline')):
        window = Window()
        errors = []
        window.error = errors.append
        try:
            for key in ('sep', 'iclass'):
                user, password, _ = window.account_fields[key]
                user.setText('fixture-' + key)
                password.setText('fixture-password')
                password.editingFinished.emit()
                assert Vault().get(key)['password'] == 'fixture-password'
                assert b'fixture-password' not in (directory / 'accounts.dpapi').read_bytes()
            window.account_fields['sep'][1].setText('updated-password')
            window.save_profile('sep')
            assert Vault().get('sep')['password'] == 'updated-password'
            version = window.account_version('iclass')
            window.checked_account('iclass', version, False, '账号密码不正确')
            assert errors.pop() == '账号密码不正确'
            window.load_planner()
            assert window.planner is not None, errors
            window.planner.selected = {c.id: c for c in window.planner.db.get_courses_with_schedules([2, 3])}
            snapshot = {'source': 'iclass', 'complete': True, 'semester': '2026年秋季',
                        'fetched_at': '2026-09-16T12:00:00', 'courses': [{'code': codes[0], 'name': '离线测试课程1'}]}
            window.enrollment_received(snapshot, 'fixture-iclass', 'iclass', version)
            assert set(window.planner.selected) == {1, 2, 3}
            assert not errors, errors
            for index in range(window.planner.selected_list.count()):
                item = window.planner.selected_list.item(index)
                identifier = item.data(Qt.UserRole)
                if identifier == 1:
                    assert '已选上' in item.text()
                    assert not item.flags() & Qt.ItemIsUserCheckable
                if identifier == 2:
                    item.setCheckState(Qt.Checked)
            window.transfer_courses()
            assert window.course_codes.toPlainText() == codes[1], 'Only explicitly checked, not all planned courses'
            # Completed enrollment clears that course from future grab imports.
            snapshot['courses'].append({'code': codes[1], 'name': '离线测试课程2'})
            window.enrollment_received(snapshot, 'fixture-iclass', 'iclass', version)
            assert not window.planner.checked_pending_codes()
            # Exercise asynchronous account rejection rather than only direct result display.
            with patch('ucasdesk.ui.IClass') as client:
                client.return_value.login.side_effect = RuntimeError('测试：密码错误')
                window.test_account('iclass')
                deadline = time.monotonic() + 5
                while not errors and time.monotonic() < deadline:
                    app.processEvents(QEventLoop.AllEvents, 50)
                    time.sleep(.01)
            assert errors.pop() == '测试：密码错误'
            assert not errors, errors
            window.nav.setCurrentRow(8)
            window.resize(1380, 910)
            window.show()
            app.processEvents()
            window.grab().save(str(ROOT / 'docs/desktop-profile.png'))
            window.nav.setCurrentRow(4)
            app.processEvents()
            window.grab().save(str(ROOT / 'docs/desktop-enrollment.png'))
            print('Profile encrypted save/reload/edit, invalid-login popup, enrollment status and checked-only transfer: PASS')
        finally:
            window.request_exit()
