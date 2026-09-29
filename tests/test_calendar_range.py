import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ucasdesk import macos_calendar as calendar
from ucasdesk.dashboard import DashboardMixin


class CalendarRangeTests(unittest.TestCase):
    def test_supported_choices_and_old_settings(self):
        for value in (7, 14, 30):
            self.assertEqual(calendar.selected_days({'calendar_days': value}), value)
        for value in (None, True, 1, 365, '30'):
            self.assertEqual(calendar.selected_days({'calendar_days': value}), 7)
        self.assertEqual(calendar.selected_days({}), 7)

    def test_each_range_queries_all_dates_and_passes_same_range_to_eventkit(self):
        for days in (7, 14, 30):
            with self.subTest(days=days):
                errors=[]
                window=SimpleNamespace(settings={'calendar_days':days},
                    account=lambda _: {'username':'fixture','password':'fixture'},
                    vault=Mock(get=Mock(return_value={'username':'fixture'})),activity=Mock(),calendar_import_button=Mock(),refresh_summary=Mock(),
                    error=errors.append,
                    background=lambda work,done,failed:done(work()))
                with patch('ucasdesk.iclass.IClass') as cls, patch('sys.platform','darwin'), \
                        patch('ucasdesk.macos_calendar.sync_range',return_value=(1,'fixture')) as sync:
                    cls.return_value.query.return_value=[]
                    DashboardMixin.import_calendar_week(window)
                    self.assertFalse(errors,errors)
                    expected=[(datetime.now(calendar.BEIJING).date()+timedelta(days=i)).strftime('%Y%m%d') for i in range(days)]
                    self.assertEqual([call.args[0] for call in cls.return_value.query.call_args_list],expected)
                    self.assertEqual(sync.call_args.kwargs['days'],days)
                    self.assertFalse(window._calendar_import_running)

    def test_calendar_includes_today_and_last_day_but_not_outside_window(self):
        for days in (7, 14, 30):
            today=datetime.now(calendar.BEIJING).date()
            rows=[{'courseName':str(offset),'classBeginTime':str(today+timedelta(days=offset))+' 08:30',
                   'classEndTime':str(today+timedelta(days=offset))+' 10:10'} for offset in (-1,0,days-1,days)]
            activity=Mock();activity.get_snapshot.return_value={}
            with self.subTest(days=days), tempfile.TemporaryDirectory() as temp, \
                    patch.object(calendar.sys,'platform','darwin'), patch('ucasdesk.core.DATA',Path(temp)), \
                    patch.object(calendar.subprocess,'run',return_value=Mock(returncode=0)) as run:
                count,_=calendar.sync_range(activity,'course','sep',days=days,courses=rows)
                self.assertEqual(count,2)
                payload=json.loads(run.call_args.kwargs['input'])
                self.assertEqual([x['title'] for x in payload],['0',str(days-1)])
