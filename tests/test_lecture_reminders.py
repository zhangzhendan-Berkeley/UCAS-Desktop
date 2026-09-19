import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from ucasdesk.lecture_reminders import LectureReminders, BEIJING


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name); self.reminders=LectureReminders(self.path)
        self.start=datetime(2026,9,19,10,tzinfo=BEIJING)
        self.row={'title':'fixture','start':self.start.isoformat(),'location':'雁栖湖'}
        self.calendars={'science':[self.row,self.row]}

    def test_default_off_custom_time_restart_and_account_isolation(self):
        r=self.reminders;now=self.start-timedelta(minutes=19)
        self.assertFalse(r.due('a',self.calendars,now))
        r.save('a',enabled=True,minutes=20)
        self.assertEqual(len(r.due('a',self.calendars,now)),1)
        self.assertFalse(r.due('a',self.calendars,now-timedelta(minutes=2)))
        r.mark_sent('a',r.due('a',self.calendars,now),now)
        self.assertFalse(LectureReminders(self.path).due('a',self.calendars,now))
        r.save('b',enabled=True)
        self.assertEqual(len(r.due('b',self.calendars,now)),1)

    def test_per_lecture_overrides_and_late_wakeup(self):
        r=self.reminders;r.save('a',enabled=True)
        r.save_lecture('a','science',self.row,True,5)
        self.assertFalse(r.due('a',self.calendars,self.start-timedelta(minutes=6)))
        self.assertTrue(r.due('a',self.calendars,self.start-timedelta(minutes=4)))
        r.save_lecture('a','science',self.row,False,5)
        self.assertFalse(r.due('a',self.calendars,self.start-timedelta(minutes=1)))
        r.save_lecture('a','science',self.row,True)
        self.assertTrue(r.due('a',self.calendars,self.start-timedelta(minutes=10)))
        self.assertFalse(r.due('a',self.calendars,self.start+timedelta(seconds=1)))
        r.save('a',enabled=False)
        self.assertFalse(r.due('a',self.calendars,self.start))

    def test_midnight_changes_unknown_dates_and_zero_minutes(self):
        r=self.reminders;r.save('a',enabled=True,minutes=20)
        row=self.row|{'start':'2026-09-20 00:05:00'}
        self.assertTrue(r.due('a',{'science':[row]},datetime(2026,9,19,23,50,tzinfo=BEIJING)))
        self.assertFalse(r.due('a',{'science':[row|{'start':'unknown'}]},self.start))
        r.mark_sent('a',[('science',self.row)],self.start)
        changed=self.row|{'start':'2026-09-19 10:10:00'}
        self.assertTrue(r.due('a',{'science':[changed]},self.start))
        r.save('b',enabled=True,minutes=0)
        self.assertTrue(r.due('b',self.calendars,self.start))
        self.assertTrue(r.due('b',self.calendars,self.start+timedelta(seconds=3)))
        self.assertFalse(r.due('b',self.calendars,self.start+timedelta(seconds=11)))


if __name__=='__main__':unittest.main()
