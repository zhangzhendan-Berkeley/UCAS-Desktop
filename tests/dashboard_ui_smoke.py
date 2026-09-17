"""Offline dashboard, confirmed events, layout persistence and copy integration."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton, QComboBox
from ucasdesk.ui import Window, STYLE, load_fonts
from ucasdesk.core import Store, Vault, read_json
from ucasdesk.automation import Automation
from ucasdesk.activity import scope
from ucasdesk.presentation import copy_table, log_state

app = QApplication([])
load_fonts()
app.setStyleSheet(STYLE)
with tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
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
        window.settings['achievement_popups'] = False
        window.settings['booking_email'] = False
        try:
            for key in ('sep', 'iclass', 'email'):
                user, password, _ = window.account_fields[key]
                user.setText('fixture@mails.ucas.ac.cn' if key == 'email' else 'fixture-' + key)
                password.setText('fixture-secret')
                window.save_profile(key)
            assert b'fixture-secret' not in (directory / 'accounts.dpapi').read_bytes()
            iclass, sep = scope(window.vault, 'iclass'), scope(window.vault, 'sep')
            today = datetime.now().strftime('%Y-%m-%d')
            rows = [dict(id=str(1000000+i), courseName='测试课'+str(i), teacherName='老师', classBeginTime=today+' 08:30:00', classEndTime=today+' 10:10:00', signStatus=str(i)) for i in range(2)]
            window.populate_courses(rows)
            assert window.course_table.item(0, 5).background() != window.course_table.item(1, 5).background()
            window.course_table.selectRow(0)
            copy_table(window.course_table)
            assert '测试课0' in app.clipboard().text()
            assert window.home_status.textInteractionFlags() & Qt.TextSelectableByMouse
            window.jobs.active['sign'] = {'module':'iclass-daily','account':iclass,'preview':False}
            window.activity_event('sign', {'event':'iclass.today','date':today.replace('-',''),'courses':rows})
            event = {'event':'iclass.sign-success','id':'1000000','title':'测试课0','automatic':True}
            window.activity_event('sign', event)
            window.activity_event('sign', event)
            assert window.activity.counts(iclass, sep)['signs'] == 1
            assert window.course_table.item(0,5).text() == '已签到'
            assert window.today_table.item(0,4).text() == '已签到'
            assert window.activity.badges(iclass, sep) == ['签到初体验']
            window.jobs.active['lecture'] = {'module':'lecture','account':sep,'preview':True}
            booking = {'event':'run.register.result','lectureId':'booking-1','title':'测试人文讲座','outcome':'registered'}
            window.activity_event('lecture', booking)
            assert window.activity.counts(iclass, sep)['bookings'] == 0
            window.jobs.active['lecture']['preview'] = False
            window.activity_event('lecture', booking)
            window.activity_event('lecture', booking)
            assert window.activity.counts(iclass, sep)['bookings'] == 1
            assert window.activity.mail_status(sep)[0] == 'disabled'
            window.settings['mail_enabled'] = True
            window.settings['mail_events'] = {'task_failed': True, 'selection': False, 'mooc_completed': True}
            with patch.object(window, 'pump_mail'):
                window.task_notification('preview', {'module':'selection','preview':True,'status':'failed','account':sep})
                window.task_notification('stopped', {'module':'mooc','status':'stopped'})
                assert window.activity.next_mail('local') is None
                window.task_notification('mooc-finished', {'module':'mooc','status':'completed','title':'慕课本轮'})
                notice = window.activity.next_mail('local')
                assert notice['kind'] == 'mooc_completed'
                window.activity.mail_result('local', notice['identifier'], 'sent')
                for job_id in ('loop1','loop2'):
                    window.task_notification(job_id, {'module':'lecture-clock','account':sep,'status':'failed','title':'巡检失败'})
                assert window.activity.next_mail(sep)['kind'] == 'task_failed'
                assert window.activity.next_mail(sep) is None, 'Only one periodic failure notice per module per day'
                window.jobs.active['selection'] = {'module':'selection','account':sep,'preview':False}
                window.activity_event('selection', {'event':'selection.success','id':'code','semester':'2026秋','title':'测试课'})
                assert window.activity.counts(iclass, sep)['selections'] == 1
                assert window.activity.next_mail(sep) is None, 'Unchecked event type never sends'
            window.settings['mail_enabled'] = False
            for kind in ('science','humanity'):
                window.activity_event('lecture', {'event':'lecture.calendar','kind':kind,'rows':[
                    {'title':'今日测试讲座','time':today+' 15:30-17:30','location':'雁栖湖'},
                    {'title':'昨日讲座','time':'2000-01-01 15:30-17:30','location':'雁栖湖'}]})
                assert '今日测试讲座' in window.lecture_today_text(kind)
                assert '昨日讲座' not in window.lecture_today_text(kind)
            assert '今日测试讲座' in window.home_cards[9].text()
            window.activity_event('lecture', {'event':'lecture.attendance','records':{'humanity':{'valid':0,'total':2},'science':{'valid':1,'total':1}}})
            assert '人文 0 次 / 科研 1 次' in window.attendance_status.text()
            def configure():
                dialog = app.activeModalWidget()
                checks = dialog.findChildren(QCheckBox)
                checks[0].setChecked(False)
                dialog.findChildren(QComboBox)[1].setCurrentIndex(0)
                next(b for b in dialog.findChildren(QPushButton) if b.text() == '保存布局').click()
            QTimer.singleShot(0, configure)
            window.customize_home()
            assert window.home_card_widgets[1].isHidden()
            assert '\n' not in window.home_cards[2].text()
            assert read_json(directory/'settings.json')['dashboard']['1']['visible'] is False
            window.settings['dashboard'] = {}
            window.refresh_dashboard()
            assert '\n' in window.home_cards[2].text()
            assert log_state('成功 0 次，失败 1 次') == 'failed'
            assert log_state('{"event":"run.register.result","outcome":"registered"}') == 'success'
            assert window.lecture_all_day.isChecked()
            assert window.lecture_from.time().toString('HH:mm') == '00:00'
            window.show()
            window.resize(1450, 1200)
            app.processEvents()
            target = Path(__file__).resolve().parents[1] / 'docs/desktop-dashboard.png'
            window.grab().save(str(target))
            assert not errors, errors
        finally:
            window.jobs.active.clear()
            window._quitting = True
            window.close()
print('Dashboard outcomes, account isolation, copy, calendars, customization, achievements and encrypted email: PASS')
