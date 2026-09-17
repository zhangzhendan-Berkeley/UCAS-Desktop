import unittest
from unittest.mock import MagicMock
from ucasdesk.overview_refresh import RefreshBatch, read_iclass_overview
from ucasdesk.mail import send_mail
import smtplib


class RefreshTests(unittest.TestCase):
    def test_partial_query_failure_keeps_other_results_and_never_signs(self):
        factory = MagicMock()
        client = factory.return_value
        client.query.side_effect = RuntimeError('temporary network failure')
        client.my_courses.return_value = {'courses': []}
        result = read_iclass_overview({'username':'fixture','password':'fixture'}, '20260917', factory)
        self.assertFalse(result['today']['ok'])
        self.assertTrue(result['enrollment']['ok'])
        client.login.assert_called_once()
        client.sign.assert_not_called()

    def test_batch_reports_partial_failure_and_cannot_overwrite_success(self):
        batch = RefreshBatch()
        batch.result('today', True, '2 courses')
        for part in batch.parts: batch.result(part, False, 'not queried')
        self.assertTrue(batch.finished)
        self.assertEqual(batch.parts['today'], ('ok', '2 courses'))
        self.assertIn('部分项目未更新', batch.summary())


class MailStagesTests(unittest.TestCase):
    def factory(self):
        factory = MagicMock()
        smtp = factory.return_value
        smtp.esmtp_features = {'auth':'LOGIN PLAIN'}
        smtp.send_message.return_value = {}
        return factory, smtp

    def test_qq_login_challenge_and_quit_disconnect_after_accepted_send(self):
        factory, smtp = self.factory()
        smtp.quit.side_effect = smtplib.SMTPServerDisconnected('bye')
        result = send_mail({'username':'fixture@qq.com','password':'code'}, test=True, smtp_factory=factory)
        self.assertIn('已接受发送', result)
        smtp.auth.assert_called_once_with('LOGIN', smtp.auth_login, initial_response_ok=False)
        smtp.send_message.assert_called_once()
        smtp.close.assert_called_once()

    def test_quit_disconnect_does_not_mask_auth_failure_or_send_email(self):
        factory, smtp = self.factory()
        smtp.auth.side_effect = smtplib.SMTPAuthenticationError(535, b'server details')
        smtp.quit.side_effect = smtplib.SMTPServerDisconnected('bye')
        with self.assertRaisesRegex(ValueError, '535.*未发送'):
            send_mail({'username':'fixture@qq.com','password':'code'}, test=True, smtp_factory=factory)
        smtp.send_message.assert_not_called()

    def test_auth_disconnect_is_unsent_but_data_disconnect_is_uncertain(self):
        factory, smtp = self.factory()
        smtp.auth.side_effect = smtplib.SMTPServerDisconnected()
        with self.assertRaisesRegex(RuntimeError, '未发送.*认证'):
            send_mail({'username':'fixture@qq.com','password':'code'}, test=True, smtp_factory=factory)
        smtp.auth.side_effect = None
        smtp.send_message.side_effect = smtplib.SMTPServerDisconnected()
        with self.assertRaisesRegex(RuntimeError, '发送结果未确认'):
            send_mail({'username':'fixture@qq.com','password':'code'}, test=True, smtp_factory=factory)
