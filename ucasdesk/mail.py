"""UCAS/CSTNET SMTP with verified TLS. Credentials never enter task payloads/logs."""
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import smtplib
import ssl
import re
from .activity import NOTICE_TYPES

HOST, PORT = 'mail.cstnet.cn', 465


def validate_address(value):
    address = value.strip()
    if not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}', address):
        raise ValueError('请填写一个有效邮箱地址（不支持多个收件人）。')
    return address


def send_mail(account, booking=None, test=False, smtp_factory=None, recipient=None):
    address = validate_address(account.get('username', ''))
    domain = address.rsplit('@', 1)[1].lower()
    host = {'mails.ucas.ac.cn': HOST, 'ucas.ac.cn': HOST, 'qq.com': 'smtp.qq.com', 'foxmail.com': 'smtp.qq.com'}.get(domain)
    if not host: raise ValueError('发件端目前支持 QQ / Foxmail 或国科大邮箱，请使用相应邮箱的授权码或客户端专用密码。')
    receiver = validate_address(recipient or address)
    if not account.get('password'):
        raise ValueError('请填写邮箱密码或客户端专用密码。')
    try:
        with (smtp_factory or smtplib.SMTP_SSL)(host, PORT, timeout=20, context=ssl.create_default_context()) as smtp:
            smtp.login(address, account['password'])
            if booking is None and not test:
                return '邮箱登录验证成功（未发送邮件）。'
            message = EmailMessage()
            message['From'] = address
            message['To'] = receiver
            message['Date'] = formatdate(localtime=True)
            message['Message-ID'] = make_msgid(domain=domain)
            if test:
                message['Subject'] = 'UCAS 桌面助手 · 邮件通知测试'
                body = '这是一封由你本机的 UCAS 桌面助手发送的测试邮件。你已勾选的重要消息将发送至此收件邮箱。'
            else:
                kind = booking.get('kind', 'booking')
                message['Subject'] = NOTICE_TYPES.get(kind, '任务提醒') + ' · ' + str(booking['title']).replace('\r', ' ').replace('\n', ' ')[:100]
                detail = booking.get('detail', {})
                body = '\n'.join(['学校已确认本次人文讲座预约成功。', '',
                    '讲座：' + booking['title'], '编号：' + booking['identifier'],
                    '预约确认时间：' + booking['at'], '讲座时间：' + str(detail.get('time') or '请查看学校页面'),
                    '地点：' + str(detail.get('location') or '请查看学校页面'), '',
                    '请按时参加，并在学校系统核对讲座安排及听讲要求。',
                    'https://xkcts.ucas.ac.cn:8443/subject/humanityLecture'])
                if kind != 'booking':
                    summaries = {'selection': '选课流程返回成功。请到 SEP 核对预选结果及后续审核要求。',
                        'sign': '学校接口已明确返回本次签到成功。有效听讲仍以学校统计为准。',
                        'task_failed': '任务失败或仍有未完成项，请在 App 的“任务与日志”查看具体原因。',
                        'mooc_completed': '本轮自动处理已结束；请在国科大在线核对任务点、测验和课程完成度。这不代表整门课程通过。'}
                    body = '\n'.join([summaries.get(kind, '请查看 App 任务日志。'), '',
                        '任务 / 课程：' + str(booking['title']), '确认时间：' + str(booking.get('at', '')),
                        str(detail.get('message', '')), '', '由你本机的 UCAS 桌面助手发送。'])
            message.set_content(body)
            refused = smtp.send_message(message)
            if refused:
                raise RuntimeError('收件地址被服务器拒绝。')
        return '邮件服务器已接受发送，请在收件箱或垃圾邮件中确认。'
    except smtplib.SMTPAuthenticationError:
        raise ValueError('邮箱登录失败：QQ 邮箱请使用 SMTP 授权码；国科大邮箱请检查客户端专用密码。') from None
    except (smtplib.SMTPException, OSError) as exc:
        # Never expose server response bodies, which may contain login identifiers.
        raise RuntimeError('邮件连接或发送未确认（' + type(exc).__name__ + '）；请核对网络和收件箱，可手动重试。') from None
