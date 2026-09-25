import json
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from ucasdesk import macos_calendar as calendar


class CalendarTests(unittest.TestCase):
    def test_packaged_helper_does_not_require_swift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / 'runtime/calendar/ucas-calendar'
            binary.parent.mkdir(parents=True)
            binary.touch()
            self.assertEqual(calendar.helper_command(root), [str(binary)])

    def test_cached_tomorrow_courses_and_eligible_lectures(self):
        day = (datetime.now(calendar.BEIJING) + timedelta(days=1)).strftime('%Y-%m-%d')
        course = {'courseName':'测试课程', 'classBeginTime':day+' 08:30', 'classEndTime':day+' 10:10', 'classroomName':'教一楼'}
        lecture = {'title':'测试讲座', 'start':day+' 14:00', 'end':day+' 16:00', 'registrationStatus':'registered', 'department':'研究生部', 'location':'雁栖湖'}
        snapshots = {'calendar-courses':{'courses':[course]}, 'today':{'courses':[course]}, 'calendar-humanity':{'rows':[lecture, lecture | {'title':'未报名', 'registrationStatus':'unregistered'}]}}
        activity = Mock()
        activity.get_snapshot.side_effect = lambda account, key: {'payload':snapshots.get(key,{})}
        with tempfile.TemporaryDirectory() as temp, patch.object(calendar.sys,'platform','darwin'), patch('ucasdesk.core.DATA',Path(temp)), patch.object(calendar.subprocess,'run') as run:
            run.return_value = Mock(returncode=0, stderr='')
            count, message = calendar.sync_tomorrow(activity,'course-scope','sep-scope')
            self.assertEqual(count,2)
            payload = json.loads(run.call_args.kwargs['input'])
            self.assertEqual(payload[0]['location'],'教一楼')
            self.assertEqual(payload[0]['end']-payload[0]['start'],6000)
            self.assertIn('本机',message)
            activity.get_snapshot.assert_any_call('course-scope','calendar-courses')
            activity.get_snapshot.assert_any_call('sep-scope','calendar-humanity')

    def test_empty_data_does_not_request_calendar_permission(self):
        activity=Mock();activity.get_snapshot.return_value={}
        with tempfile.TemporaryDirectory() as temp, patch.object(calendar.sys,'platform','darwin'), patch('ucasdesk.core.DATA',Path(temp)), patch.object(calendar.subprocess,'run') as run:
            count,message=calendar.sync_range(activity,'c','s')
            self.assertEqual(count,0)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
