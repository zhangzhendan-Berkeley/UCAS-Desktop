from datetime import datetime, timedelta
import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

from ucasdesk.selection_safety import (RecoveryBudget, SessionExpired, confirmed_full,
    login_required, login_time, prepare_course, scheduled_start, wait_until)

CODE = '180081050100P1001H'


class RateLimitedError(RuntimeError):
    pass


class SelectionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.driver = Mock(current_url='https://xkgo.ucas.ac.cn:3000/courseManage/main')
        self.driver.execute_script.return_value = False
        self.flow = SimpleNamespace(RateLimitedError=RateLimitedError, RequestPacer=Mock(),
            assert_not_rate_limited=Mock(), open_query_page=Mock(), query_course=Mock(), target_checkbox=Mock())
        self.flow.target_checkbox.return_value.is_enabled.return_value = True
        self.selected, self.login = Mock(return_value=False), Mock()
        self.budget = RecoveryBudget()

    def prepare(self):
        return prepare_course(self.driver, {}, CODE, flow=self.flow,
            already_selected=self.selected, login=self.login, budget=self.budget)

    def test_valid_session_has_no_extra_login(self):
        self.assertEqual(self.prepare(), 'available')
        self.login.assert_not_called()
        self.flow.query_course.assert_called_once()

    def test_expiry_during_query_recovers_then_rechecks_selected(self):
        def query(*args):
            self.driver.execute_script.return_value = True
            raise TimeoutError('redirected to login')
        self.flow.query_course.side_effect = query
        def login(*args, **kwargs):
            self.driver.execute_script.return_value = False
            self.selected.return_value = True
        self.login.side_effect = login
        self.assertEqual(self.prepare(), 'already-selected')
        self.login.assert_called_once()
        self.assertEqual(self.selected.call_count, 2)

    def test_network_error_does_not_trigger_login(self):
        self.flow.query_course.side_effect = TimeoutError('network')
        with self.assertRaises(TimeoutError): self.prepare()
        self.login.assert_not_called()

    def test_rate_limit_takes_precedence_over_expiry(self):
        self.driver.execute_script.return_value = True
        self.flow.assert_not_rate_limited.side_effect = RateLimitedError('limit')
        with self.assertRaises(RateLimitedError): self.prepare()
        self.login.assert_not_called()

    def test_persistent_expiry_stops_after_one_recovery(self):
        self.driver.execute_script.return_value = True
        with self.assertRaises(SessionExpired): self.prepare()
        self.login.assert_called_once()
        self.assertEqual(self.budget.remaining, 1)

    def test_total_recoveries_are_bounded(self):
        self.driver.execute_script.return_value = True
        self.budget.remaining = 0
        with self.assertRaises(SessionExpired): self.prepare()
        self.login.assert_not_called()

    def test_unrecognized_host_is_not_evidence_of_expiry(self):
        self.driver.current_url = 'https://example.org/login'
        self.driver.execute_script.return_value = True
        self.assertFalse(login_required(self.driver))
        self.driver.execute_script.assert_not_called()

    def test_schedule_is_near_execution_and_wait_is_interruptible(self):
        start = scheduled_start('2026-09-25T18:00:00')
        self.assertEqual(login_time(start), start-timedelta(minutes=5))
        now = [start-timedelta(seconds=2.5)]
        sleeps = []
        def sleep(seconds): sleeps.append(seconds); now[0] += timedelta(seconds=seconds)
        wait_until(start, lambda: now[0], sleep)
        self.assertEqual(sleeps, [1, 1, .5])
        with self.assertRaises(InterruptedError):
            wait_until(start, lambda: start-timedelta(seconds=10), Mock(side_effect=InterruptedError))
        with self.assertRaises(ValueError): scheduled_start('bad date')
        with self.assertRaises(ValueError): scheduled_start('2026-09-25T18:00:00+08:00')

    def test_only_terminal_full_outcome_allows_polling(self):
        full = f'↷ 课程 {CODE} 已满，结束本门任务'
        self.assertTrue(confirmed_full(full, CODE))
        self.assertTrue(confirmed_full(f'↷ 课程 {CODE} 已满或不可选，结束本门任务', CODE))
        for output in ('', '已满', full+'\n提交结果未知', full+'\n验证码错误', full.replace(CODE,'other-course')):
            with self.subTest(output=output): self.assertFalse(confirmed_full(output, CODE))


class WorkerBoundaryTests(unittest.TestCase):
    def setUp(self):
        # Test the actual adapter orchestration without importing opt-in vendor code.
        flow = SimpleNamespace(**{name:Mock() for name in (
            'run_course_selection','assert_not_rate_limited','open_query_page','query_course','target_checkbox','RequestPacer')}, RateLimitedError=RateLimitedError)
        upstream = SimpleNamespace(course_already_selected=Mock(return_value=False), return_to_course_home=Mock(return_value=True))
        path = Path(__file__).resolve().parents[1]/'adapters/selection_worker.py'
        spec = importlib.util.spec_from_file_location('selection_worker_fixture', path)
        self.worker = importlib.util.module_from_spec(spec)
        old_path = sys.path[:]
        with patch.dict(sys.modules, {'main':upstream, 'course_flow':flow}): spec.loader.exec_module(self.worker)
        sys.path[:] = old_path
        self.driver = Mock()
        self.order = []
        for name, value in {
            'browser_options':Mock(), 'driver_service':Mock(), 'browser_label':Mock(return_value='fixture'),
            'browser_driver':Mock(side_effect=lambda *args:(self.order.append('browser') or self.driver)),
            'login_sep':Mock(side_effect=lambda *args,**kw:self.order.append('login')),
            'wait_until':Mock(side_effect=lambda target:self.order.append('wait')),
            'prepare_course':Mock(return_value='available'),
        }.items():
            p=patch.object(self.worker,name,value);p.start();self.addCleanup(p.stop)
        p=patch.object(self.worker.time,'sleep');p.start();self.addCleanup(p.stop)
        self.config={'codes':[CODE],'username':'fixture','password':'fixture','rounds':2}

    def run_worker(self):
        with contextlib.redirect_stdout(io.StringIO()), patch.object(self.worker,'Tee',io.StringIO):
            return self.worker.run(self.config)

    def test_waits_before_opening_browser_and_logging_in(self):
        self.config.update(start_at='2099-01-01T08:00:00',preview=True)
        self.assertEqual(self.run_worker(),0)
        self.assertEqual(self.order,['wait','browser','login','wait'])

    def test_unknown_after_submit_is_never_replayed_or_relogged(self):
        def uncertain(*args,**kwargs):
            print(f'↷ 课程 {CODE} 已满，结束本门任务')
            print('提交结果未知，请核对预选列表。')
            return False
        self.worker.run_course_selection.side_effect=uncertain
        self.assertEqual(self.run_worker(),1)
        self.worker.run_course_selection.assert_called_once()
        self.worker.login_sep.assert_called_once()
        self.driver.quit.assert_called_once()

    def test_confirmed_full_keeps_existing_polling(self):
        attempts=[]
        def full_then_success(*args,**kwargs):
            attempts.append(1)
            if len(attempts)==1:
                print(f'↷ 课程 {CODE} 已满，结束本门任务');return False
            return True
        self.worker.run_course_selection.side_effect=full_then_success
        self.assertEqual(self.run_worker(),0)
        self.assertEqual(len(attempts),2)

    def test_preview_never_calls_submit_executor(self):
        self.config['preview']=True
        self.assertEqual(self.run_worker(),0)
        self.worker.run_course_selection.assert_not_called()


if __name__ == '__main__': unittest.main()
