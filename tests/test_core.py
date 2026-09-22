import json
import os
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from ucasdesk.core import protect, Vault, Store, redact
from ucasdesk.iclass import IClass, course_id, eligible
from ucasdesk.api import LocalAPI


class Response:
    def __init__(self, data): self.data = data
    def raise_for_status(self): pass
    def json(self): return self.data


class Transport:
    def __init__(self, data): self.data, self.calls, self.headers = iter(data), [], {}
    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return Response(next(self.data))


class Tests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI only')
    def test_dpapi_roundtrip(self):
        original = '账号与密码测试'.encode()
        encrypted = protect(original)
        self.assertNotIn(original, encrypted)
        self.assertEqual(protect(encrypted, decrypt=True), original)

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI only')
    def test_vault_remember_and_forget(self):
        with tempfile.TemporaryDirectory() as tmp, patch('ucasdesk.core.DATA', Path(tmp)):
            vault = Vault()
            vault.set('sep', 'fake-user', 'fake-secret', True)
            self.assertEqual(Vault().get('sep')['password'], 'fake-secret')
            self.assertNotIn(b'fake-secret', vault.path.read_bytes())
            vault.set('sep', 'fake-user', 'fake-secret', False)
            self.assertEqual(vault.get('sep')['password'], 'fake-secret')
            self.assertEqual(Vault().get('sep')['password'], '')

    def test_qr_allows_only_known_protocol(self):
        self.assertEqual(course_id('https://iclass.ucas.edu.cn:8181/app/course/stu_scan_sign.action?courseSchedId=1234567&timestamp=9'), '1234567')
        for bad in ['abcdef', 'https://evil.example/?courseSchedId=1234567', 'https://iclass.ucas.edu.cn/other?courseSchedId=1234567']:
            with self.assertRaises(ValueError): course_id(bad)

    def test_window_boundaries_and_already_signed(self):
        c = dict(classBeginTime='2026-09-16 10:00:00', classEndTime='2026-09-16 11:00:00', signStatus='0')
        self.assertFalse(eligible(c, datetime(2026, 9, 16, 9, 54)))
        self.assertTrue(eligible(c, datetime(2026, 9, 16, 9, 55)))
        self.assertFalse(eligible(c, datetime(2026, 9, 16, 11, 0)))
        c['signStatus'] = '1'
        self.assertFalse(eligible(c, datetime(2026, 9, 16, 10, 5)))

    def test_login_rejection_makes_no_sign_request(self):
        transport = Transport([{'STATUS': '1'}])
        with self.assertRaises(RuntimeError): IClass('user', 'secret', transport).sign('1234567')
        self.assertEqual(len(transport.calls), 1)

    def test_sign_requires_both_status_fields(self):
        for response, expected in [({'STATUS': '0', 'result': {'stuSignStatus': '0'}}, False),
                                   ({'STATUS': '1', 'result': {'stuSignStatus': '1'}}, False),
                                   ({'STATUS': '0', 'result': {'stuSignStatus': '1'}}, True)]:
            transport = Transport([{'STATUS': '0', 'result': {'sessionId': 'secret', 'id': '99'}}, {'STATUS': '0', 'timestamp': 1789500000000}, response])
            result = IClass('user', 'pass', transport).sign('1234567')
            self.assertEqual(result['success'], expected)
            self.assertEqual(transport.calls[-1][1]['params']['timestamp'], 1789499997000)

    def test_timetable_empty_day_and_real_errors(self):
        for reply, empty in [({'STATUS': '2'}, True), ({'STATUS': 2, 'result': []}, True),
                             ({'STATUS': '1'}, False), ({'STATUS': '2', 'result': {'error': 'bad'}}, False)]:
            transport = Transport([{'STATUS': '0', 'result': {'sessionId': 'secret', 'id': '99'}}, reply])
            client = IClass('user', 'pass', transport)
            if empty:
                self.assertEqual(client.query('20260926'), [])
                self.assertEqual(client.session_id, 'secret')
            else:
                with self.assertRaises(RuntimeError): client.query('20260926')

    def test_logs_remove_credentials(self):
        text = redact('password=hidden sessionId=secret enc=abcdef my-password', ['my-password'])
        for value in ('hidden', 'secret', 'abcdef', 'my-password'):
            self.assertNotIn(value, text)

    def test_api_authentication_and_no_log_paths(self):
        with tempfile.TemporaryDirectory() as tmp, patch('ucasdesk.api.DATA', Path(tmp)):
            store = Store(Path(tmp) / 'tasks.db')
            job_id = store.create('test', '离线测试')
            api = LocalAPI(store, port=0)
            base = f'http://127.0.0.1:{api.server.server_port}'
            try:
                with self.assertRaises(HTTPError) as ctx: urlopen(base + '/v1/jobs')
                self.assertEqual(ctx.exception.code, 401)
                req = Request(base + '/v1/jobs', headers={'Authorization': 'Bearer ' + api.token, 'Origin': 'https://example.vercel.app'})
                with urlopen(req) as response:
                    data = json.load(response)
                    self.assertEqual(response.headers['Access-Control-Allow-Origin'], '*')
                    self.assertEqual(response.headers['Access-Control-Allow-Headers'], 'Authorization')
                self.assertEqual(data[0]['id'], job_id)
                self.assertNotIn('log', data[0])
                options = Request(base + '/v1/jobs', method='OPTIONS', headers={'Origin': 'https://example.vercel.app'})
                with urlopen(options) as response:
                    self.assertEqual(response.status, 204)
                    self.assertEqual(response.headers['Access-Control-Allow-Methods'], 'GET, OPTIONS')
                with self.assertRaises(HTTPError) as ctx: urlopen(Request(base + '/v1/jobs', data=b'{}'))
                self.assertEqual(ctx.exception.code, 405)
            finally: api.close()

    def test_restart_marks_unfinished_jobs_interrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'jobs.db'
            store = Store(path)
            store.create('test', 'offline')
            self.assertEqual(Store(path).list()[0]['status'], 'interrupted')


if __name__ == '__main__': unittest.main()
