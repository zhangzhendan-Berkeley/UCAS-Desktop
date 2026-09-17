"""Exercise the actual one-click wiring with delayed callbacks, no school writes."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
from pathlib import Path
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from ucasdesk.ui import Window
from tests.vault_fixture import isolated_keychain
from ucasdesk.core import Store
from ucasdesk.automation import Automation
from ucasdesk.activity import scope

app = QApplication([])
with isolated_keychain(), tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
    def engine(jobs, vault, parent):
        a = Automation(jobs, vault, parent, directory=directory); a.timer.stop(); return a
    with patch('ucasdesk.ui.DATA', directory), patch('ucasdesk.core.DATA', directory), \
         patch('ucasdesk.ui.Store', lambda: Store(directory/'jobs.db')), patch('ucasdesk.ui.Automation', engine), \
         patch('ucasdesk.ui.LocalAPI', side_effect=OSError('offline')):
        w = Window(); errors = []; w.error = errors.append
        try:
            for key in ('sep','iclass'):
                w.account_fields[key][0].setText('fixture-'+key)
                w.account_fields[key][1].setText('fixture-password')
                w.save_profile(key)
            callbacks = []
            def background(function, callback, error): callbacks.append((function, callback, error))
            result = {'today': {'ok':True,'value':[]}, 'enrollment':{'ok':True,'value':{
                'source':'iclass','complete':True,'courses':[],'fetched_at':'fixture','semester':'2026秋'}}}
            with patch.object(w, 'background', side_effect=background), patch.object(w, 'start_job', return_value='batch') as start, \
                 patch.object(w, 'load_planner'), patch('ucasdesk.dashboard.read_iclass_overview', return_value=result) as read:
                w.refresh_all(); batch = w._overview_refresh
                assert not w.refresh_all_button.isEnabled()
                w.refresh_all()
                assert len(callbacks) == 1 and start.call_count == 1
                assert start.call_args.args[-1]['action'] == 'dashboard-refresh'
                assert start.call_args.args[-1]['preview'] is True
                assert start.call_args.kwargs['open_logs'] is False
                value = callbacks[0][0]()  # Runs after the SEP account was prepared.
                assert read.call_args.args[0]['username'] == 'fixture-iclass', 'Do not capture SEP credentials in iClass closure'
                callbacks[0][1](value)
                assert w.enrollment.current()['source'] == 'iclass'
                w.refresh_receive_event('batch', {'event':'dashboard.part','part':'science','ok':True,'value':{'rows':[]}})
                w.refresh_receive_event('batch', {'event':'dashboard.part','part':'humanity','ok':False,'error':'session expired'})
                w.refresh_receive_event('batch', {'event':'dashboard.part','part':'science-attendance','ok':True,'value':{'valid':1,'total':1}})
                w.refresh_receive_event('batch', {'event':'dashboard.part','part':'humanity-attendance','ok':True,'value':{'valid':0,'total':2}})
                w.refresh_job_finished('batch', {'status':'failed'})
                assert batch.finished and w.refresh_all_button.isEnabled()
                assert '部分项目未更新' in w.refresh_all_status.text()
                assert batch.parts['science'][0] == 'ok', 'Task failure must not undo successful steps'
                assert '科研 1 次' in w.attendance_status.text()
                assert w.nav.currentRow() == 0
                w.refresh_all(); batch = w._overview_refresh
                old = w.activity.get_snapshot(scope(w.vault,'sep'), 'calendar-science')
                w.account_fields['sep'][1].setText('changed')
                w.refresh_receive_event('batch', {'event':'dashboard.part','part':'science','ok':True,'value':{'rows':[{'title':'must not apply'}]}})
                assert batch.parts['science'][0] == 'failed'
                assert w.activity.get_snapshot(scope(w.vault,'sep'), 'calendar-science') == old
                callbacks[-1][2]('network unavailable')
                w.refresh_job_finished('batch', {'status':'stopped'})
                assert batch.finished
            with patch.object(w,'start_job',side_effect=ModuleNotFoundError("No module named 'ucasdesk.portable'")):
                w.query_science_schedule()
                assert 'portable' in errors[-1] and '请先在' not in errors[-1]
        finally:
            if hasattr(w, '_refresh_wait'): w._refresh_wait.stop()
            w._quitting = True; w.close()
print('One-click wiring, delayed credentials, partial failures, cancellation and honest errors: PASS')
