import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication
from ucasdesk.automation import Automation, lecture_slot, next_lecture_slot
from ucasdesk.sign_ledger import SignLedger
from adapters.iclass_worker import daily_courses, main


class Jobs:
    def __init__(self):
        self.active, self.calls = {}, []

    def start(self, *args):
        self.calls.append(args)
        return str(len(self.calls))

    def stop(self, key):
        self.active.pop(key, None)


class Vault:
    def get(self, key):
        return {'username': 'fixture', 'password': 'fixture-password'}

    def secret_values(self):
        return ['fixture-password']


class AutomationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_clock_alignment_grace_and_midnight(self):
        self.assertIsNone(lecture_slot(datetime(2026, 9, 16, 8, 0, 59), [8]))
        self.assertEqual(lecture_slot(datetime(2026, 9, 16, 8, 1), [8]), '2026-09-16T08:01')
        self.assertIsNotNone(lecture_slot(datetime(2026, 9, 16, 8, 32, 59), [8]))
        self.assertIsNone(lecture_slot(datetime(2026, 9, 16, 8, 33), [8]))
        self.assertIsNone(lecture_slot(datetime(2026, 9, 16, 9, 1), [8]))
        self.assertEqual(next_lecture_slot(datetime(2026, 9, 16, 23, 32), [0]), datetime(2026, 9, 17, 0, 1))

    def test_daily_once_then_next_day_and_restart_catchup(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = Jobs()
            engine = Automation(jobs, Vault(), directory=Path(tmp))
            engine.timer.stop()
            engine.save('course', {'enabled': True, 'minutes_before': 5})
            engine.tick(datetime(2026, 9, 16, 7, 59))
            self.assertEqual(len(jobs.calls), 0)
            engine.tick(datetime(2026, 9, 16, 8))
            engine.tick(datetime(2026, 9, 16, 8, 0, 5))
            self.assertEqual(len(jobs.calls), 1)
            self.assertEqual(jobs.calls[0][-1]['date'], '20260916')
            self.assertEqual(jobs.calls[0][-1]['timing'], 'random-before-20m')
            self.assertNotIn('minutes_before', jobs.calls[0][-1], 'Old fixed-offset settings must not reach the worker')
            engine.tick(datetime(2026, 9, 17, 8))
            self.assertEqual(len(jobs.calls), 2)
            restarted = Automation(jobs, Vault(), directory=Path(tmp))
            restarted.timer.stop()
            restarted.tick(datetime(2026, 9, 18, 12))
            self.assertEqual(jobs.calls[-1][-1]['date'], '20260918')
            self.assertNotIn('fixture-password', engine.path.read_text())
            restarted.disable('course')
            restarted.save('course', {'enabled': True, 'minutes_before': 5})
            restarted.tick(datetime(2026, 9, 18, 13))
            self.assertEqual(len(jobs.calls), 4, 'Re-enabling a stopped plan must work on the same day')

    def test_lecture_restart_dedup_busy_and_no_catchup_storm(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Only module-presence probing is mocked; all scheduler state is real on disk.
            jobs = Jobs()
            engine = Automation(jobs, Vault(), directory=Path(tmp))
            engine.timer.stop()
            engine.save('lecture', {'enabled': True, 'hours': [8], 'book': False})
            with patch.object(Path, 'exists', return_value=True):
                engine.tick(datetime(2026, 9, 16, 8, 1))
            self.assertEqual(len(jobs.calls), 1)
            restarted = Automation(jobs, Vault(), directory=Path(tmp))
            restarted.timer.stop()
            restarted.tick(datetime(2026, 9, 16, 8, 2))
            self.assertEqual(len(jobs.calls), 1)
            jobs.active['other'] = {'module': 'lecture'}
            restarted.tick(datetime(2026, 9, 16, 8, 31))
            self.assertEqual(len(jobs.calls), 1)
            jobs.active.clear()
            restarted.tick(datetime(2026, 9, 16, 8, 35))
            self.assertEqual(len(jobs.calls), 1)
            restarted.disable('lecture')
            self.assertFalse(restarted.enabled('lecture'))

    def test_daily_filters_ended_signed_and_duplicate_courses(self):
        course = {'id': '1234567', 'classBeginTime': '2026-09-16 10:00:00',
                  'classEndTime': '2026-09-16 11:00:00', 'signStatus': '0'}
        class Client:
            def query(self, date):
                return [course, course, course | {'id': '1234568', 'signStatus': '1'},
                        course | {'id': '1234569', 'classBeginTime': '2026-09-16 07:00:00', 'classEndTime': '2026-09-16 08:00:00'}]
        self.assertEqual(daily_courses(Client(), '20260916', datetime(2026, 9, 16, 8)), [course])

    def test_ledger_survives_restart_unknown_and_accounts_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ledger.db'
            ledger = SignLedger('one', path)
            self.assertEqual(ledger.claim('1234567'), 'claimed')
            self.assertEqual(SignLedger('one', path).claim('1234567'), 'skip')
            self.assertEqual(SignLedger('two', path).claim('1234567'), 'claimed')
            ledger.finish('1234567', 'unknown')
            self.assertEqual(ledger.claim('1234567'), 'skip')

    def test_atomic_claim_and_bounded_retry_across_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ledger.db'
            ledger = SignLedger('one', path)
            with ThreadPoolExecutor(2) as pool:
                results = list(pool.map(lambda _: SignLedger('one', path).claim('1234567'), range(2)))
            self.assertEqual(sorted(results), ['claimed', 'skip'])
            for n in range(2):
                ledger.finish('1234567', 'retry', 120)
                self.assertEqual(ledger.claim('1234567', 119), 'wait')
                self.assertEqual(SignLedger('one', path).claim('1234567', 120), 'claimed')
            ledger.finish('1234567', 'retry', 120)
            self.assertEqual(ledger.claim('1234567', 121), 'skip')

    def test_unknown_submission_not_replayed_by_restarted_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = SignLedger('fixture', Path(tmp) / 'ledger.db')
            payload = {'mode': 'single', 'username': 'fixture', 'password': 'secret', 'identifier': '1234567'}
            with patch('adapters.iclass_worker.SignLedger', return_value=ledger), patch('adapters.iclass_worker.IClass') as client:
                client.return_value.sign.side_effect = RuntimeError('connection lost after submission')
                with self.assertRaises(RuntimeError): main(payload)
                self.assertEqual(main(payload), 1)
                self.assertEqual(client.return_value.sign.call_count, 1)

    def test_early_rejection_keeps_an_attempt_for_class_start(self):
        class Clock:
            seconds = datetime(2026, 9, 16, 8, 25).timestamp()
            def time(self): return self.seconds
            def monotonic(self): return self.seconds
            def sleep(self, seconds): self.seconds += seconds
        clock = Clock()
        class Dates:
            @staticmethod
            def now(): return datetime.fromtimestamp(clock.seconds)
            fromtimestamp = datetime.fromtimestamp
        course = {'id': '1234567', 'courseName': 'fixture', 'signStatus': '0',
                  'classBeginTime': '2026-09-16 08:30:00', 'classEndTime': '2026-09-16 09:30:00'}
        calls = []
        def sign(identifier):
            calls.append(Dates.now())
            return {'success': len(calls) > 1, 'retryable': len(calls) == 1, 'message': 'fixture'}
        with tempfile.TemporaryDirectory() as tmp:
            ledger = SignLedger('fixture', Path(tmp) / 'ledger.db')
            with patch('adapters.iclass_worker.SignLedger', return_value=ledger), \
                 patch('adapters.iclass_worker.IClass') as client, \
                 patch('adapters.iclass_worker.datetime', Dates), patch('adapters.iclass_worker.time', clock), \
                 patch('ucasdesk.sign_ledger.time.time', side_effect=clock.time), \
                 patch('ucasdesk.sign_ledger.secrets.randbelow', return_value=0):
                client.return_value.query.return_value = [course]
                client.return_value.sign.side_effect = sign
                result = main({'mode': 'scheduled', 'courses': [course], 'minutes_before': 5, 'username': 'fixture', 'password': 'secret'})
            self.assertEqual(result, 0)
            self.assertEqual(calls, [datetime(2026, 9, 16, 8, 25), datetime(2026, 9, 16, 8, 30)])

    def test_random_plan_window_restart_and_late_start(self):
        start = datetime(2026, 9, 16, 8, 30).timestamp()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'ledger.db'
            ledger = SignLedger('one', path)
            with patch('ucasdesk.sign_ledger.secrets.randbelow', return_value=0) as draw:
                first = ledger.planned_time('1234567', start, start - 3600)
                self.assertEqual(first, start - 1200)
                self.assertEqual(SignLedger('one', path).planned_time('1234567', start, start - 600), first)
                self.assertEqual(draw.call_count, 1, 'Restart must not redraw a due or future time')
            with patch('ucasdesk.sign_ledger.secrets.randbelow', side_effect=lambda upper: upper-1):
                self.assertEqual(SignLedger('two', path).planned_time('1234567', start, start-3600), start-1)
                self.assertEqual(ledger.planned_time('1234568', start, start-30.5), start-1)
            with patch('ucasdesk.sign_ledger.secrets.randbelow') as draw:
                self.assertEqual(ledger.planned_time('1234569', start, start+30), start+30)
                draw.assert_not_called()
            with patch('ucasdesk.sign_ledger.secrets.randbelow', return_value=0):
                self.assertEqual(ledger.planned_time('1234567', start+86400, start+80000), start+86400-1200)

    def test_concurrent_workers_share_one_random_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = SignLedger('one', Path(tmp) / 'ledger.db')
            with patch('ucasdesk.sign_ledger.secrets.randbelow', return_value=437) as draw:
                with ThreadPoolExecutor(2) as pool:
                    times = list(pool.map(lambda _: ledger.planned_time('1234567', 10000, 7000), range(2)))
                self.assertEqual(times, [9237, 9237])
                self.assertEqual(draw.call_count, 1)

    def test_worker_waits_for_selected_second_and_jitters_retry(self):
        class Clock:
            seconds = datetime(2026, 9, 16, 8).timestamp()
            def time(self): return self.seconds
            def monotonic(self): return self.seconds
            def sleep(self, seconds): self.seconds += seconds
        clock = Clock()
        class Dates:
            @staticmethod
            def now(): return datetime.fromtimestamp(clock.seconds)
            fromtimestamp = datetime.fromtimestamp
        course = {'id':'1234567', 'courseName':'fixture', 'signStatus':'0',
                  'classBeginTime':'2026-09-16 08:30:00', 'classEndTime':'2026-09-16 09:30:00'}
        calls = []
        def sign(identifier):
            calls.append(Dates.now())
            return {'success':len(calls)>1, 'retryable':len(calls)==1}
        with tempfile.TemporaryDirectory() as tmp:
            ledger = SignLedger('fixture', Path(tmp)/'ledger.db')
            with patch('adapters.iclass_worker.SignLedger',return_value=ledger), \
                 patch('adapters.iclass_worker.IClass') as client, \
                 patch('adapters.iclass_worker.datetime',Dates), patch('adapters.iclass_worker.time',clock), \
                 patch('ucasdesk.sign_ledger.time.time',side_effect=clock.time), \
                 patch('ucasdesk.sign_ledger.secrets.randbelow',side_effect=[443,17]):
                client.return_value.query.return_value=[course]
                client.return_value.sign.side_effect=sign
                self.assertEqual(main({'mode':'scheduled','courses':[course], 'minutes_before':5,
                    'username':'fixture','password':'secret'}),0)
            self.assertEqual(calls,[datetime(2026,9,16,8,17,23),datetime(2026,9,16,8,30,17)])


if __name__ == '__main__':
    unittest.main()
