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
from PySide6.QtCore import Qt, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QTextBrowser, QMessageBox
from ucasdesk.ui import Window, load_fonts, style_sheet
from ucasdesk.automation import Automation
from tests.vault_fixture import isolated_keychain
from ucasdesk.core import ROOT, Vault, Store


def preview(name):
    """Keep regenerated screenshots out of tracked docs unless explicitly asked."""
    target = ROOT / ('docs' if os.environ.get('UCAS_UPDATE_DOCS') == '1' else 'logs/previews') / name
    target.parent.mkdir(parents=True, exist_ok=True)
    return str(target)

app = QApplication([])
load_fonts()
app.setStyleSheet(style_sheet())

with isolated_keychain(), tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
    planner = directory / 'planner'
    planner.mkdir()
    codes = [f'180086081200P100{i}H' for i in range(1, 4)]
    with closing(sqlite3.connect(planner / 'courses.db')) as db, db:
        db.execute('CREATE TABLE courses(id INTEGER PRIMARY KEY, course_name TEXT, credits TEXT, hours TEXT, course_code TEXT, department TEXT, teacher TEXT, attribute TEXT)')
        db.execute('CREATE TABLE course_schedules(course_id INTEGER, day_of_week INTEGER, time_slots TEXT, location TEXT, weeks TEXT, semester TEXT)')
        for i, code in enumerate(codes, 1):
            db.execute('INSERT INTO courses VALUES(?,?,?,?,?,?,?,?)', (i, '离线测试课程' + str(i), '2', '40', code, '测试学院', '测试教师' + str(i), ['学科核心课', '公共选修课', '专业课'][i-1]))
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
                if os.name == 'nt':
                    assert b'fixture-password' not in (directory / 'accounts.dpapi').read_bytes()
                else:
                    leaked = [p.name for p in directory.rglob('*') if p.is_file() and b'fixture-password' in p.read_bytes()]
                    assert not leaked, '密码以明文落盘：' + ', '.join(leaked)
            window.account_fields['sep'][1].setText('updated-password')
            window.save_profile('sep')
            assert Vault().get('sep')['password'] == 'updated-password'
            version = window.account_version('iclass')
            window.checked_account('iclass', version, False, '账号密码不正确')
            assert errors.pop() == '账号密码不正确'
            window.load_planner()
            assert window.planner is not None, errors
            from coursesystem.state import load_state
            assert load_state()['db_path'] == 'courses.db', 'Portable state uses relative in-app database paths'
            p = window.planner
            p.search_input.setText('测试教师2 测试学院')
            assert p.course_table.rowCount() == 1
            assert p.course_table.item(0, 0).text() == codes[1]
            p.course_table.selectRow(0)
            p.save_alternative()
            assert not p.selected, 'Shortlist must not add a timetable entry'
            assert p.alternatives_list.count() == 1
            from ucasdesk.core import read_json
            assert read_json(p.alternatives_path)[0]['code'] == codes[1]
            p.save_alternative()
            assert p.alternatives_list.count() == 1, 'Shortlist deduplicates'
            p.alternatives_list.setCurrentRow(0)
            p.promote_alternative()
            assert set(p.selected) == {2}
            assert not p.checked_pending_codes(), 'Promotion does not opt into grabbing'
            p._on_clear_search()
            p.type_filter.setCurrentIndex(p.type_filter.findData('学科核心课'))
            assert p.course_table.rowCount() == 1
            p._on_clear_search()
            assert p.course_table.rowCount() == 3
            p.week_view.week_spin.setValue(2)
            from ucasdesk.catalog import colors
            assert p.week_view.table.item(0, 2).background().color().name() == colors('公共选修课')[0]
            assert p.week_view.table.rowSpan(0, 2) == 2
            overlap = p.db.get_courses_with_schedules([3])[0]
            original_schedule = overlap.schedules[0]
            overlap.schedules = p.selected[2].schedules
            p.selected[3] = overlap
            p._refresh_views()
            assert p.week_view.table.item(0, 2).background().color().name() == '#f8d7da', 'Conflict red takes priority'
            overlap.schedules = [original_schedule]
            p._refresh_views()
            p.week_view.week_spin.setValue(20)
            assert not p.week_view.table.item(0, 2)
            assert p.week_view.table.rowSpan(0, 2) == 1, 'Week changes clear old merged blocks'
            p.week_view.week_spin.setValue(2)
            details = []
            def close_details():
                dialog = p.findChild(QDialog)
                details.append(dialog.findChild(QTextBrowser).toPlainText())
                dialog.accept()
            QTimer.singleShot(0, close_details)
            p.show_course(2)
            assert '测试教师2' in details[0] and '计算机科学与技术' in details[0]
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
            window.refresh_selection_courses()
            assert window.selection_table.item(0, 0).text() == '离线测试课程2'
            assert window.selection_table.item(0, 4).text() == '测试教师2'
            assert window.selection_table.item(0, 6).text() == '公共选修课'
            window.course_codes.setPlainText(codes[1] + '\n' + codes[1] + '\n' + codes[1] + '-99')
            window.refresh_selection_courses()
            assert window.selection_table.rowCount() == 2
            assert '未唯一匹配' in window.selection_table.item(1, 0).text()
            window.course_codes.setPlainText(codes[1])
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
            window.grab().save(preview('desktop-profile.png'))
            window.nav.setCurrentRow(4)
            app.processEvents()
            window.grab().save(preview('desktop-enrollment.png'))
            window.planner_tabs.setCurrentIndex(0)
            app.processEvents()
            window.grab().save(preview('desktop-catalog.png'))
            window.planner_tabs.setCurrentIndex(2)
            app.processEvents()
            window.grab().save(preview('desktop-week.png'))
            window.nav.setCurrentRow(5)
            window.refresh_selection_courses()
            app.processEvents()
            window.grab().save(preview('desktop-selection.png'))
            print('Profile, enrollment, metadata, search, category colors, shortlist persistence, details and checked-only transfer: PASS')
        finally:
            window.request_exit()
