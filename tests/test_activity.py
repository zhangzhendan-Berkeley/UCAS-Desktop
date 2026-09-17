import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from ucasdesk.activity import Activity
from ucasdesk.mail import send_mail


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.activity = Activity(Path(self.tmp.name) / 'activity.db')

    def test_account_isolation_dedup_days_and_manual_exclusion(self):
        a = self.activity
        self.assertTrue(a.record('a', 'sign', '1', '课', at='2026-09-17T08:30:00'))
        self.assertFalse(a.record('a', 'sign', '1', '重复', at='2026-09-18T08:30:00'))
        a.record('a', 'sign', '2', '课', at='2026-09-17T10:30:00')
        a.record('a', 'sign', '3', '手动', automatic=False)
        a.record('b', 'sign', '1', '其他账号')
        self.assertEqual(a.counts('a', 'sep'), dict(signs=2, days=1, bookings=0, selections=0))
        self.assertEqual(a.counts('b', 'sep')['signs'], 1)
        self.assertEqual(a.unlock('a', 'sep'), ['签到初体验'])
        self.assertEqual(a.unlock('a', 'sep'), [])

    def test_outbox_claim_restart_and_sent_dedup(self):
        a = self.activity
        a.record('sep', 'booking', 'id', '讲座')
        a.queue_mail('sep', 'id', True)
        self.assertIsNone(a.next_mail('other'))
        self.assertEqual(a.next_mail('sep')['title'], '讲座')
        self.assertIsNone(a.next_mail('sep'))
        restarted = Activity(a.path)
        restarted.recover_mail()
        self.assertEqual(a.mail_status('sep')[0], 'unknown')
        self.assertIsNone(a.next_mail('sep'), 'Uncertain sends must not replay automatically')
        a.mail_result('sep', 'id', 'pending')
        self.assertIsNotNone(a.next_mail('sep'))
        a.mail_result('sep', 'id', 'sent')
        a.queue_mail('sep', 'id', True)
        self.assertIsNone(a.next_mail('sep'))

    def test_disabled_notifications_are_not_sent_retroactively(self):
        a = self.activity
        a.record('s', 'booking', '1', '讲座')
        a.queue_mail('s', '1', False)
        a.queue_mail('s', '1', True)
        self.assertIsNone(a.next_mail('s'))

    def test_mail_tls_auth_check_no_send_and_self_only(self):
        factory = MagicMock()
        smtp = factory.return_value
        smtp.send_message.return_value = {}
        smtp.esmtp_features = {'auth': 'LOGIN PLAIN'}
        account = {'username': 'fixture@mails.ucas.ac.cn', 'password': 'fixture-password'}
        send_mail(account, smtp_factory=factory)
        smtp.send_message.assert_not_called()
        self.assertEqual(factory.call_args.args, ('mail.cstnet.cn', 465))
        self.assertTrue(factory.call_args.kwargs['context'].check_hostname)
        send_mail(account, test=True, smtp_factory=factory)
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message['To'], account['username'])
        self.assertNotIn(account['password'], message.as_string())

    def test_failed_auth_hides_server_response(self):
        import smtplib
        factory = MagicMock()
        factory.return_value.login.side_effect = smtplib.SMTPAuthenticationError(535, b'secret server echo')
        with self.assertRaisesRegex(ValueError, '客户端专用密码') as caught:
            send_mail({'username': 'fixture@mails.ucas.ac.cn', 'password': 'fixture-password'}, smtp_factory=factory)
        self.assertNotIn('secret', str(caught.exception))

    def test_qq_sender_separate_recipient_and_header_injection(self):
        factory = MagicMock()
        smtp = factory.return_value
        smtp.send_message.return_value = {}
        smtp.esmtp_features = {'auth': 'LOGIN PLAIN'}
        account = {'username': 'fixture@qq.com', 'password': 'fixture-authorization-code'}
        send_mail(account, test=True, smtp_factory=factory, recipient='receiver@mails.ucas.ac.cn')
        self.assertEqual(factory.call_args.args, ('smtp.qq.com', 465))
        message = smtp.send_message.call_args.args[0]
        self.assertEqual(message['From'], 'fixture@qq.com')
        self.assertEqual(message['To'], 'receiver@mails.ucas.ac.cn')
        self.assertNotIn(account['password'], message.as_string())
        with self.assertRaises(ValueError):
            send_mail(account, test=True, smtp_factory=factory, recipient='receiver@mails.ucas.ac.cn\r\nBcc: other@example.com')
        self.assertEqual(smtp.send_message.call_count, 1)

    def test_generic_notification_without_booking_and_selection_atomic_queue(self):
        a = self.activity
        a.queue_mail('local', 'job:1', True, {'kind': 'mooc_completed', 'title': '慕课', 'at': '2026-09-17', 'detail': {}})
        self.assertEqual(a.next_mail('local')['kind'], 'mooc_completed')
        a.record('s', 'selection', 'code|2026秋', '选课', notify=True)
        self.assertEqual(a.next_mail('s')['kind'], 'selection')
        self.assertFalse(a.record('s', 'selection', 'code|2026秋', '选课', notify=True))
        self.assertIsNone(a.next_mail('s'))


if __name__ == '__main__': unittest.main()
