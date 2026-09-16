from __future__ import annotations
from datetime import datetime, timedelta
import re
import threading
import time
from urllib.parse import urlsplit, parse_qs
import requests

BASE = 'https://iclass.ucas.edu.cn:8181/app'
UA = 'student_5.0.1.2_android_12_20_100000000000000_110000'


def course_id(value: str) -> str:
    value = value.strip()
    if value.startswith(('http://', 'https://')):
        parsed = urlsplit(value)
        if parsed.hostname != 'iclass.ucas.edu.cn' or parsed.path != '/app/course/stu_scan_sign.action':
            raise ValueError('此二维码不是已适配的轻新课堂课程签到接口，未提交。')
        value = parse_qs(parsed.query).get('courseSchedId', [''])[0]
    if not re.fullmatch(r'\d{7}', value):
        raise ValueError('请输入 7 位课程排课 ID，或包含 courseSchedId 的轻新课堂二维码链接。')
    return value


def parse_time(value):
    return datetime.strptime(value, '%Y-%m-%d %H:%M:%S')


def eligible(course, now=None, minutes_before=5):
    now = now or datetime.now()
    if str(course.get('signStatus')) == '1':
        return False
    start, end = parse_time(course['classBeginTime']), parse_time(course['classEndTime'])
    return start - timedelta(minutes=min(30, max(0, minutes_before))) <= now < end


class IClass:
    api_version = 1

    def __init__(self, username, password, transport=None):
        if not username.strip() or not password:
            raise ValueError('请先填写轻新课堂学号和密码。')
        self.username, self.password = username.strip(), password
        self.session = transport or requests.Session()
        self.session.headers.update({'User-Agent': UA})
        self.session_id = None
        self.user_id = None
        self.login_at = 0
        self.lock = threading.RLock()

    def _request(self, method, path, **kwargs):
        try:
            response = self.session.request(method, BASE + path, timeout=15, **kwargs)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.SSLError:
            raise RuntimeError('学校接口 TLS 证书校验失败，请检查网络或证书。') from None
        except requests.exceptions.RequestException:
            raise RuntimeError('学校接口无法连接或响应超时，请检查网络。') from None
        except ValueError:
            raise RuntimeError('学校接口未返回 JSON，可能发生接口变更。') from None
        if not isinstance(data, dict):
            raise RuntimeError('学校接口结构发生变化。')
        return data

    def login(self):
        with self.lock:
            if self.session_id and time.monotonic() - self.login_at < 600:
                return
            data = self._request('POST', '/user/login.action', data={
                'phone': self.username, 'password': self.password, 'verificationType': '1',
                'verificationUrl': 'http://iclass.ucas.edu.cn:88/ve/webservices/mobileCheck.shtml?method=mobileLogin&username=${0}&password=${1}&lx=${2}',
                'userLevel': '1',
            }, headers={'User-Agent': 'student_5.0.1.2_android_12_20__110000'})
            result = data.get('result') or {}
            if str(data.get('STATUS')) != '0' or not result.get('sessionId') or not result.get('id'):
                raise RuntimeError('轻新课堂登录失败，请检查账号、密码及账号绑定状态。')
            self.session_id, self.user_id = result['sessionId'], result['id']
            self.login_at = time.monotonic()

    def query(self, date):
        datetime.strptime(date, '%Y%m%d')
        with self.lock:
            self.login()
            data = self._request('GET', '/course/get_stu_course_sched.action',
                                 params={'id': self.user_id, 'dateStr': date}, headers={'sessionId': self.session_id})
            if str(data.get('STATUS')) != '0':
                self.session_id = None
                raise RuntimeError('课表查询失败或登录已失效，请重新查询。')
            result = data.get('result') or []
            if not isinstance(result, list):
                raise RuntimeError('课表数据结构发生变化。')
            fields = ('id', 'uuid', 'courseName', 'teacherName', 'classBeginTime', 'classEndTime', 'signStatus')
            return [{key: str(c.get(key, '')) for key in fields} for c in result]

    def server_time(self):
        data = self._request('POST', '/common/get_timestamp.do', params={'id': int(time.time())})
        stamp = data.get('timestamp')
        if str(data.get('STATUS')) != '0' or not isinstance(stamp, (int, float)) or isinstance(stamp, bool):
            raise RuntimeError('无法校准学校时间，已停止签到。')
        return int(stamp) - 3000

    def sign(self, identifier):
        identifier = course_id(identifier)
        with self.lock:
            self.login()
            data = self._request('GET', '/course/stu_scan_sign.action', params={
                'courseSchedId': identifier, 'timestamp': self.server_time(), 'id': self.user_id,
            }, headers={'sessionId': self.session_id})
            result = data.get('result') or {}
            success = str(data.get('STATUS')) == '0' and str(result.get('stuSignStatus')) == '1'
            message = '签到成功' if success else str(result.get('msg') or data.get('ERRMSG') or data.get('msg') or '学校未确认签到成功，请核对课堂记录。')
            retryable = str(data.get('STATUS')) != '0' and any(text in message for text in ('未在上课时间', '尚未开始', '时间戳已过期', '二维码已过期'))
            return {'success': success, 'message': message, 'retryable': retryable,
                    'record': str(result.get('stuSignId', '')), 'status': str(result.get('stuSignStatus', ''))}

    def health(self):
        return {'server_timestamp': self.server_time(), 'api_version': 1}

    def execute(self, action, payload):
        if action == 'query':
            return {'courses': self.query(payload['date'])}
        if action == 'sign':
            return self.sign(payload['course_id'])
        raise ValueError('不支持的接口操作')
