"""Persistent, wall-clock plans. The GUI owns timers; adapters own network work."""
from datetime import datetime, timedelta
from PySide6.QtCore import QObject, QTimer, Signal
from .core import DATA, ROOT, PYTHON, NODE, read_json, write_json, redact
import sys


def lecture_slot(now, hours):
    """Only the current slot, with a two-minute wake-up grace; never replay a backlog."""
    for minute in (31, 1):
        slot = now.replace(minute=minute, second=0, microsecond=0)
        if slot.hour in hours and 0 <= (now - slot).total_seconds() < 120:
            return slot.isoformat(timespec='minutes')
    return None


def next_lecture_slot(now, hours):
    for offset in range(49):
        hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=offset)
        for minute in (1, 31):
            candidate = hour.replace(minute=minute)
            if candidate > now and candidate.hour in hours:
                return candidate
    return None


class Automation(QObject):
    changed = Signal()

    def __init__(self, jobs, vault, parent=None, directory=DATA):
        super().__init__(parent)
        self.jobs, self.vault, self.directory = jobs, vault, directory
        self.path = directory / 'automation.json'
        self.state_path = directory / 'automation-state.json'
        self.config = read_json(self.path, {})
        self.state = read_json(self.state_path, {})
        self.daily_started = None
        self.calendar_sync_day = None
        self.messages = {}
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(5000)

    def save(self, kind, values):
        self.config[kind] = values
        write_json(self.path, self.config)
        if kind == 'course' and not any(item['module'] == 'iclass-daily' for item in self.jobs.active.values()):
            self.daily_started = None
        self.messages.pop(kind, None)
        self.changed.emit()

    def disable(self, kind):
        self.save(kind, self.config.get(kind, {}) | {'enabled': False})
        if kind == 'course':
            self.daily_started = None
        module = 'iclass-daily' if kind == 'course' else ('science-daily' if kind == 'science' else 'lecture-clock')
        for job_id, item in list(self.jobs.active.items()):
            if item['module'] == module:
                self.jobs.stop(job_id)

    def enabled(self, kind):
        return self.config.get(kind, {}).get('enabled', False)

    def credentials(self, kind):
        account = self.vault.get('iclass' if kind == 'course' else 'sep').copy()
        if not account.get('username') or not account.get('password'):
            raise ValueError('缺少已保存的账号密码，请填写账号并保存后台计划。')
        return account

    def tick(self, now=None):
        now = now or datetime.now()
        for kind in ('course', 'lecture', 'science'):
            if not self.enabled(kind):
                continue
            try:
                self.run_due(kind, now)
            except Exception as exc:
                self.messages[kind] = redact(str(exc), self.vault.secret_values())
        if sys.platform == 'darwin' and now.hour == 22 and now.minute == 0 and self.calendar_sync_day != now.date():
            try:
                from .macos_calendar import sync_tomorrow
                activity = getattr(self.parent(), 'activity', None)
                if activity is None:
                    raise RuntimeError('本地日历同步尚未准备好')
                count, message = sync_tomorrow(activity, self.vault.get('iclass').get('username',''), self.vault.get('sep').get('username',''))
                self.calendar_sync_day = now.date()
                self.messages['calendar'] = message
            except Exception as exc:
                self.messages['calendar'] = redact(str(exc), self.vault.secret_values())
        self.changed.emit()

    def run_due(self, kind, now):
        config = self.config[kind]
        active = {item['module'] for item in self.jobs.active.values()}
        if kind == 'course':
            today = now.date().isoformat()
            if now.hour < 8 or self.daily_started == today or 'iclass-daily' in active:
                return
            account = self.credentials(kind)
            # The worker rechecks school records; its durable ledger prevents replay on restart.
            self.jobs.start('iclass-daily', f'每日 08:00 课程计划 · {today}', PYTHON,
                            [ROOT / 'adapters/iclass_worker.py'], account | {
                                'mode': 'daily', 'date': now.strftime('%Y%m%d'),
                                'timing': 'random-before-20m'})
            self.daily_started = today
            self.messages[kind] = f'{today} 已启动课表检查与定时签到；结果见任务日志'
        elif kind == 'science':
            today = now.date().isoformat()
            if now.hour < 8 or self.state.get('science_daily') == today or 'science-daily' in active:
                return
            account = self.credentials(kind)
            if not (ROOT / 'vendor/ucas-humanity-lecture-bot/dist/src/workflow.js').exists():
                raise ValueError('请先安装人文/科研讲座外部模块。')
            self.state['science_daily'] = today
            write_json(self.state_path, self.state)
            self.jobs.start('science-daily', f'每日 08:00 科研讲座报名 · {today}', NODE,
                            [ROOT / 'adapters/lecture.mjs'], account | {
                                'action': 'science-book', 'lectureUrl': 'https://xkcts.ucas.ac.cn:8443/subject/lecture',
                                'science': True, 'scienceMode': True, 'onePerStartTime': True,
                                'scienceKeywords': ['人工智能', '机器学习', '深度学习', '神经网络', '大模型', '自然语言处理', '计算机视觉', '机器人', '具身智能'],
                                'preview': False})
            self.messages[kind] = f'{today} 已启动科研讲座报名；结果见任务日志'
        else:
            slot = lecture_slot(now, config.get('hours', list(range(24))))
            if not slot or self.state.get('lecture_slot') == slot:
                return
            if active & {'lecture', 'lecture-clock'}:
                self.messages[kind] = '讲座模块仍在运行，本时点等待；超过 2 分钟后跳过'
                return
            account = self.credentials(kind)
            if not (ROOT / 'vendor/ucas-humanity-lecture-bot/dist/src/workflow.js').exists():
                raise ValueError('请先安装人文讲座外部模块。')
            self.state['lecture_slot'] = slot
            write_json(self.state_path, self.state)
            self.jobs.start('lecture-clock', f'讲座定点检查 · {slot}', NODE,
                            [ROOT / 'adapters/lecture.mjs'], account | config | {
                                'observe': True, 'scheduled': False, 'slot': slot,
                                'preview': not config.get('book', False)})
            self.messages[kind] = f'已启动 {slot} 检查；结果见任务日志'

    def description(self, kind):
        if not self.enabled(kind):
            return '后台计划：未启用'
        message = self.messages.get(kind, '已保存；应用运行时自动执行')
        if kind == 'lecture':
            due = next_lecture_slot(datetime.now(), self.config[kind].get('hours', list(range(24))))
            if due:
                message += ' · 下次 ' + due.strftime('%m-%d %H:%M')
        return message
