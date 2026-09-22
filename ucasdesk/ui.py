from __future__ import annotations
from datetime import datetime
import json
import os
from pathlib import Path
import socket
import sys

from PySide6.QtCore import Qt, QDate, QDateTime, QTime, QTimer, QThreadPool, QRunnable, QObject, Signal, QUrl, QEvent
from PySide6.QtGui import QDesktopServices, QTextCursor, QFontDatabase, QFont, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QCheckBox, QSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit, QFormLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QPlainTextEdit, QMessageBox,
    QFileDialog, QStackedWidget, QListWidget, QGroupBox, QScrollArea, QSplitter, QTabWidget, QSystemTrayIcon, QMenu, QDialog)

from .core import ROOT, DATA, LOGS, VENDOR, PYTHON, NODE, Vault, Store, read_json, write_json, redact, check_updates, stage_updates
from .jobs import Jobs
from .iclass import IClass
from .api import LocalAPI
from .automation import Automation
from .enrollment import Enrollment, account_hash
from .activity import Activity, NOTICE_TYPES, NOTICE_DEFAULTS
from .dashboard import DashboardMixin
from .lectures import LecturesMixin
from .presentation import color_item, LogHighlighter, enable_copy

STATUS = {'running': '运行中', 'stopping': '停止中', 'completed': '已结束', 'attention': '待处理：仍有未完成项', 'failed': '执行失败', 'stopped': '已停止', 'interrupted': '已中断'}
UI_FONTS = {
    'nt': ('Microsoft YaHei',),
    'darwin': ('PingFang SC', 'Heiti SC', 'Hiragino Sans GB', 'Songti SC'),
    'posix': ('Noto Sans CJK SC', 'Source Han Sans SC', 'WenQuanYi Micro Hei', 'DejaVu Sans'),
}


def ui_font_families():
    """Preferred installed families for this platform, most preferred first."""
    preferred = list(UI_FONTS['darwin' if sys.platform == 'darwin' else os.name])
    if isinstance(QApplication.instance(), QApplication):
        available = set(QFontDatabase.families())
        installed = [name for name in preferred if name in available]
        return installed or ['sans-serif']
    return preferred


def style_sheet():
    return STYLE.replace('__UI_FONT_STACK__', ', '.join('"%s"' % name for name in ui_font_families()))


def load_fonts():
    for font in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf'):
        path = Path('C:/Windows/Fonts') / font
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    families = ui_font_families()
    QApplication.setFont(QFont(families[0], 10))


class Signals(QObject):
    done = Signal(object)
    error = Signal(str)
    finished = Signal()


class Work(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function, self.signals = function, Signals()

    def run(self):
        try:
            self.signals.done.emit(self.function())
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            self.signals.finished.emit()


def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    widget.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, function, primary=False):
    b = QPushButton(text)
    b.clicked.connect(function)
    if primary:
        b.setObjectName('primary')
    return b


def row(*widgets):
    layout = QHBoxLayout()
    for widget in widgets:
        layout.addWidget(widget)
    return layout


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    widget.verticalHeader().setVisible(False)
    widget.setSelectionBehavior(QAbstractItemView.SelectRows)
    widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
    widget.setAlternatingRowColors(True)
    return widget


class Window(LecturesMixin, DashboardMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('UCAS 桌面助手 · 雁栖湖')
        self.setWindowIcon(QIcon(str(ROOT / 'assets/app.ico')))
        self.tray = None
        self._quitting = False
        self._shutdown_done = False
        self._tray_notice_shown = False
        self.resize(1380, 910)
        self.setMinimumSize(1080, 740)
        self.vault = Vault()
        self.store = Store()
        self.jobs = Jobs(self.store, self.vault)
        self.automation = Automation(self.jobs, self.vault, self)
        self.pool = QThreadPool.globalInstance()
        self.workers = []
        self.courses = []
        self.account_fields = {}
        self.profile_status = {}
        self.account_jobs = {}
        self.enrollment = Enrollment(DATA / 'planner', self.vault.get)
        self.settings = read_json(DATA / 'settings.json', {})
        self.activity = Activity(DATA / 'activity.sqlite3')
        self.activity.recover_mail()
        self.api = None
        self.planner = None
        self.current_log = None

        central = QWidget()
        horizontal = QHBoxLayout(central)
        horizontal.setContentsMargins(0, 0, 0, 0)
        sidebar = QWidget()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(205)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(19, 25, 19, 24)
        side.addWidget(label('UCAS', 'brand'))
        side.addWidget(label('桌面助手 / 雁栖湖', 'sideText'))
        side.addSpacing(28)
        self.nav = QListWidget()
        self.nav.setObjectName('navigation')
        self.nav.addItems(['概览', '课程签到', '人文/科研讲座', '国科大在线', '选课规划', '自动选课', '任务与日志', '设置与更新', '个人信息'])
        side.addWidget(self.nav)
        self.runtime_hint = label('本地运行 · v0.5.0\n关闭窗口后托盘运行\n右键托盘可退出程序', 'sideText')
        side.addWidget(self.runtime_hint)
        horizontal.addWidget(sidebar)
        self.pages = QStackedWidget()
        horizontal.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.build_home()
        self.build_iclass()
        self.build_lecture()
        self.build_mooc()
        self.build_planner()
        self.build_selection()
        self.build_jobs()
        self.build_settings()
        self.build_profile()
        self.build_today_lectures(self.lecture_layout)
        enable_copy(self)
        self.nav.currentRowChanged.connect(self.navigate)
        self.nav.setCurrentRow(0)
        self.jobs.changed.connect(self.refresh_jobs)
        self.jobs.output.connect(self.receive_output)
        self.jobs.ended.connect(self.task_notification)
        self.jobs.ended.connect(self.refresh_job_finished)
        self.refresh_jobs()
        self.statusBar().showMessage('就绪。自动任务需要你在相应模块配置后启动。')
        self.clock = QTimer(self)
        self.clock.timeout.connect(self.refresh_jobs)
        self.clock.start(5000)
        try:
            self.api = LocalAPI(self.store, lan=self.settings.get('lan', False))
            self.api_status.setText('API 已启动：127.0.0.1:8765 · v1（只读）')
        except OSError:
            self.api_status.setText('API 端口 8765 被占用，桌面功能仍可使用。')
        if self.vault.warning:
            self.statusBar().showMessage(self.vault.warning)
        self.setup_tray()
        self.automation.changed.connect(self.refresh_automation)
        self.refresh_automation()

    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.runtime_hint.setText('系统托盘不可用\n最小化后继续运行\n关闭窗口将退出程序')
            return
        QApplication.instance().setQuitOnLastWindowClosed(False)
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray_menu = QMenu(self)
        self.tray_status = self.tray_menu.addAction('')
        self.tray_status.setEnabled(False)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction('打开窗口', self.show_window)
        self.tray_menu.addAction('任务与日志', self.show_jobs)
        self.tray_menu.addAction('隐藏窗口', self.hide_to_tray)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction('退出程序（停止自动任务）', self.request_exit)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.messageClicked.connect(self.show_window)
        self.jobs.changed.connect(self.update_tray)
        self.update_tray()
        self.tray.show()

    def update_tray(self):
        if self.tray:
            count = len(self.jobs.active)
            status = f'{count} 个任务运行中' if count else '待命 · 暂无运行任务'
            self.tray.setToolTip('UCAS 桌面助手 · ' + status)
            self.tray_status.setText(status)

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window()

    def show_window(self):
        if self._quitting:
            return
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    def show_jobs(self):
        self.nav.setCurrentRow(6)
        self.show_window()

    def hide_to_tray(self):
        if self._quitting or not self.tray or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.hide()
        if not self._tray_notice_shown:
            self._tray_notice_shown = True
            self.tray.showMessage('UCAS 桌面助手正在后台运行',
                                  '自动任务继续执行。点击右下角图标打开窗口；右键菜单可退出程序。',
                                  QSystemTrayIcon.Information, 3500)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and self.isMinimized() and self.tray:
            QTimer.singleShot(0, lambda: self.hide_to_tray() if self.isMinimized() else None)

    def request_exit(self):
        self._quitting = True
        self.close()
        QApplication.instance().quit()

    def page(self, title, subtitle):
        outer = QWidget()
        widget = outer
        if title.startswith('人文讲座'):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)
            widget = QWidget()
            scroll.setWidget(widget)
            self.pages.addWidget(scroll)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(28, 25, 28, 22)
        layout.setSpacing(16)
        layout.addWidget(label(title, 'title'))
        layout.addWidget(label(subtitle, 'muted'))
        if not title.startswith('人文讲座'):
            self.pages.addWidget(widget)
        return layout

    def error(self, text):
        QMessageBox.warning(self, '需要处理', redact(text, self.vault.secret_values()))

    def background(self, function, callback, on_error=None):
        self.statusBar().showMessage('正在处理，请稍候…')
        worker = Work(function)
        self.workers.append(worker)
        worker.signals.done.connect(callback)
        worker.signals.error.connect(on_error or self.error)
        worker.signals.finished.connect(lambda: self.release_worker(worker))
        self.pool.start(worker)

    def release_worker(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)
        self.statusBar().showMessage('就绪')

    def account_form(self, key, title, username_hint):
        group = QGroupBox(title)
        form = QFormLayout(group)
        existing = self.vault.get(key)
        user = QLineEdit(existing['username'])
        user.setPlaceholderText(username_hint)
        password = QLineEdit(existing['password'])
        password.setEchoMode(QLineEdit.Password)
        password.setPlaceholderText('密码只在本机使用')
        remember = QCheckBox('记住账号密码（使用系统安全存储）')
        remember.setChecked(True)
        form.addRow('发件邮箱' if key == 'email' else '账号', user)
        form.addRow('授权码 / 专用密码' if key == 'email' else '密码', password)
        remember.setVisible(False)  # Compatibility with existing account callers; storage is always encrypted.
        form.addRow(label('编辑完成后自动加密保存，所有模块共用；也可点击下方保存。', 'muted'))
        self.account_fields[key] = (user, password, remember)
        user.editingFinished.connect(lambda: self.save_profile(key, quiet=True))
        password.editingFinished.connect(lambda: self.save_profile(key, quiet=True))
        form.addRow(row(button('保存账号', lambda: self.save_profile(key)), button('检测账号密码', lambda: self.test_account(key))))
        self.profile_status[key] = label('已读取本机保存的账号' if existing['password'] else '尚未保存账号', 'muted')
        form.addRow(self.profile_status[key])
        return group

    def account(self, key):
        user, password, remember = self.account_fields[key]
        if not user.text().strip() or not password.text():
            raise ValueError('请先到“个人信息”填写账号和密码。')
        self.vault.set(key, user.text(), password.text(), True)
        return self.vault.get(key).copy()

    def build_profile(self):
        layout = self.page('个人信息', '账号由当前系统的安全存储保存在本机；课程、讲座、已选同步与自动选课共用。')
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        widget = QWidget()
        layout.addWidget(scroll, 1)
        layout = QVBoxLayout(widget)
        scroll.setWidget(widget)
        layout.addWidget(self.account_form('sep', 'SEP 信息门户账号', 'SEP 邮箱 / 账号'))
        layout.addWidget(self.account_form('iclass', '轻新课堂账号', '学号'))
        layout.addWidget(self.account_form('email', '发件端 · QQ / Foxmail / 国科大邮箱', '发件邮箱，例如自己的 QQ 邮箱'))
        self.mail_recipient = QLineEdit(self.settings.get('mail_recipient', self.vault.get('email').get('username', '')))
        self.mail_recipient.setPlaceholderText('收件邮箱，可以是国科大邮箱；无需填写收件邮箱密码')
        layout.addLayout(row(label('收件邮箱'), self.mail_recipient))
        self.email_enabled = QCheckBox('启用邮件提醒（总开关）')
        self.email_enabled.setChecked(self.settings.get('mail_enabled', self.settings.get('booking_email', False)))
        self.notice_checks = {}
        choices = QGridLayout()
        for index, (kind, title) in enumerate(NOTICE_TYPES.items()):
            check = QCheckBox(title)
            check.setChecked(self.settings.get('mail_events', {}).get(kind, NOTICE_DEFAULTS[kind]))
            self.notice_checks[kind] = check
            choices.addWidget(check, index // 2, index % 2)
        self.achievements_enabled = QCheckBox('达成累计目标时显示成就提示（不打断任务）')
        self.achievements_enabled.setChecked(self.settings.get('achievement_popups', True))
        layout.addWidget(self.email_enabled)
        layout.addLayout(choices)
        layout.addWidget(self.achievements_enabled)
        self.email_enabled.toggled.connect(self.save_notification_settings)
        self.mail_recipient.editingFinished.connect(self.save_notification_settings)
        for check in self.notice_checks.values(): check.toggled.connect(self.save_notification_settings)
        self.achievements_enabled.toggled.connect(self.save_notification_settings)
        layout.addLayout(row(button('发送测试邮件到收件邮箱', lambda: self.test_email(True)), button('核对收件箱后重发未确认通知', self.retry_notification)))
        layout.addWidget(label('按发件邮箱自动选择服务器：QQ / Foxmail 使用 smtp.qq.com:465，国科大使用 mail.cstnet.cn:465，均验证 SSL 证书。QQ 填 SMTP 授权码，国科大填客户端专用密码。检测账号不发邮件；邮件失败不影响学校操作。', 'muted'))
        layout.addWidget(label('账号修改对之后启动的任务生效。检测只登录，不报名、不选课、不签到；SEP 检测会打开独立浏览器，验证码或邮箱验证需要你完成。', 'muted'))
        layout.addStretch()

    def profile_link(self, text):
        group = QWidget()
        layout = QHBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label(text + ' · 使用个人信息页保存的账号', 'muted'), 1)
        layout.addWidget(button('个人信息 / 修改账号', lambda: self.nav.setCurrentRow(8)))
        return group

    def save_profile(self, key, quiet=False):
        try:
            user, password, _ = self.account_fields[key]
            if quiet and (not user.text().strip() or not password.text()):
                return
            self.account(key)
            self.profile_status[key].setText('已加密保存；重开应用后自动读取。')
            if self.planner:
                self.planner._refresh_views()
                self.planner._apply_filters()
        except Exception as exc:
            self.error(str(exc))

    def account_version(self, key):
        import hashlib
        user, password, _ = self.account_fields[key]
        return hashlib.sha256(json.dumps([user.text().strip(), password.text()]).encode()).hexdigest()

    def checked_account(self, key, version, success, message):
        if self.account_version(key) != version:
            return
        self.profile_status[key].setText(message)
        if not success:
            self.error(message)

    def test_account(self, key):
        if key == 'email':
            self.test_email()
            return
        try:
            account = self.account(key)
            version = self.account_version(key)
            self.profile_status[key].setText('正在使用新登录检测…')
            if key == 'iclass':
                self.background(lambda: IClass(**account).login(),
                    lambda _: self.checked_account(key, version, True, '轻新课堂账号密码验证成功。'),
                    lambda error: self.checked_account(key, version, False, error))
            else:
                job = self.jobs.start('account-sep', 'SEP 账号密码检测 · 只登录', PYTHON,
                                      [ROOT / 'adapters/account_worker.py'], account | {'action': 'check'})
                self.account_jobs[job] = {'version': version, 'account': account['username'], 'action': 'check'}
        except Exception as exc:
            self.profile_status[key].setText('检测未完成：' + redact(str(exc), self.vault.secret_values()))
            self.error(str(exc))

    def build_iclass(self):
        layout = self.page('课程签到', '轻新课堂。可手动选择排课，或每天 08:00 自动安排当天全部未结束课程；电脑需联网且不休眠。')
        layout.addWidget(self.profile_link('轻新课堂'))
        self.course_date = QDateEdit(QDate.currentDate())
        self.course_date.setCalendarPopup(True)
        self.course_date.setDisplayFormat('yyyy-MM-dd')
        daily = self.automation.config.get('course', {})
        self.daily_enabled = QCheckBox('每天 08:00 自动查课表并安排签到')
        self.daily_enabled.setChecked(daily.get('enabled', False))
        layout.addLayout(row(self.daily_enabled, button('保存每日计划', self.save_daily_plan),
                             button('停用每日计划', lambda: self.disable_plan('course'))))
        self.daily_status = label('', 'muted')
        layout.addWidget(self.daily_status)
        layout.addWidget(label('个人信息页的账号自动保存，计划可随应用重启恢复；08:00 后启动会补查今天。', 'muted'))
        layout.addWidget(label('课程签到：每节课在开课前 20 分钟内随机选定一次执行时间，重启沿用；具体时间见任务日志。', 'banner'))
        layout.addLayout(row(label('日期'), self.course_date, button('查询课表', self.query_courses, True),
                             button('为勾选课程建立自动签到任务', self.schedule_courses)))
        self.course_table = table(['选择', '课程 / 讲座', '教师', '开始', '结束', '签到状态', '排课 ID'])
        layout.addWidget(self.course_table, 1)
        layout.addWidget(button('查看人文/科研讲座 →', lambda: self.nav.setCurrentRow(2)))

    def query_science_schedule(self):
        try:
            payload = self.account('sep') | {'action': 'science-schedule', 'preview': True}
            self.start_job('lecture', '科研讲座时间表 · 只读查询', NODE, [ROOT / 'adapters/lecture.mjs'], payload)
        except Exception as exc:
            self.error('科研讲座查询未启动：' + str(exc))

    def save_daily_plan(self):
        try:
            enabled = self.daily_enabled.isChecked()
            if not enabled:
                self.disable_plan('course')
                return
            self.account('iclass')
            self.automation.save('course', {'enabled': True, 'timing': 'random-before-20m'})
            self.automation.tick()
        except Exception as exc:
            self.error(str(exc))

    def disable_plan(self, kind):
        self.automation.disable(kind)
        (self.daily_enabled if kind == 'course' else self.lecture_clock).setChecked(False)

    def refresh_automation(self):
        self.daily_status.setText(self.automation.description('course'))
        self.lecture_clock_status.setText(self.automation.description('lecture'))

    def stop_all_tasks(self):
        for kind in ('course', 'lecture'):
            self.disable_plan(kind)
        self.jobs.stop_all()

    def query_courses(self):
        try:
            account = self.account('iclass')
            date = self.course_date.date().toString('yyyyMMdd')
            self.background(lambda: IClass(**account).query(date), self.populate_courses)
        except Exception as exc:
            self.error(str(exc))

    def populate_courses(self, courses):
        self.courses = courses
        self.course_table.setRowCount(len(courses))
        for index, c in enumerate(courses):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            check.setCheckState(Qt.Unchecked)
            self.course_table.setItem(index, 0, check)
            fields = [c['courseName'], c['teacherName'], c['classBeginTime'], c['classEndTime'], '已签到' if c['signStatus'] == '1' else '未签到', c['id']]
            for column, text in enumerate(fields, 1):
                cell = QTableWidgetItem(str(text))
                color_item(cell, 'success' if str(c['signStatus']) == '1' else 'pending')
                self.course_table.setItem(index, column, cell)
        self.statusBar().showMessage(f'查询到 {len(courses)} 节课程 / 排课。')

    def start_job(self, module, title, program, args, payload, open_logs=True):
        if module in ('lecture', 'selection', 'mooc'):
            from .portable import ready
            entry = next(m for m in read_json(ROOT / 'modules.json', []) if m['id'] == module)
            if not ready(ROOT, entry):
                if (ROOT / 'runtime/modules-downloads.json').is_file():
                    self.nav.setCurrentRow(7)
                    raise ValueError('请在“设置与更新”点击“一键启用讲座预约与抢课”。无需安装开发环境，完成后返回此页面启动任务。')
                command = 'python scripts/setup.py' + (' --with-external-modules' if entry.get('external_opt_in') else '')
                raise ValueError(f'此模块尚未安装。请按 README 执行：{command}')
            if module == 'mooc' and not (ROOT / 'adapters/mooc_helpers.mjs').is_file():
                raise ValueError('慕课适配器尚未生成，请重新运行 python scripts/setup.py。')
        job_id = self.jobs.start(module, title, program, args, payload)
        if open_logs:
            self.nav.setCurrentRow(6)
            self.select_job(job_id)
        return job_id

    def schedule_courses(self):
        try:
            courses = [course for index, course in enumerate(self.courses) if self.course_table.item(index, 0).checkState() == Qt.Checked]
            if not courses:
                raise ValueError('请先查询课表并勾选需要签到的课程。')
            payload = self.account('iclass') | {'mode': 'scheduled', 'courses': courses, 'timing': 'random-before-20m'}
            self.start_job('iclass', f'课程自动签到 · {len(courses)} 节', PYTHON, [ROOT / 'adapters/iclass_worker.py'], payload)
        except Exception as exc:
            self.error(str(exc))

    def build_lecture(self):
        layout = self.page('人文讲座 / 科研讲座预约', '统一管理雁栖湖讲座报名、每日自动任务、今日讲座和到场提醒。')
        self.lecture_layout = layout
        layout.addWidget(self.profile_link('SEP 信息门户'))
        group = QGroupBox('筛选可以参加的讲座')
        form = QVBoxLayout(group)
        days = QHBoxLayout()
        self.days = []
        for index, text in enumerate(['周一', '周二', '周三', '周四', '周五', '周六', '周日']):
            check = QCheckBox(text)
            check.setChecked(index < 5)
            self.days.append(check)
            days.addWidget(check)
        form.addLayout(days)
        form.addWidget(label('报名只选择地点明确为雁栖湖的讲座；首次运行会打开 Edge，出现验证时请在浏览器中完成。', 'muted'))
        form.addWidget(label('报名仅限地点明确包含“雁栖湖”的讲座；中关村、玉泉路、其他校区及地点不明均跳过。', 'muted'))
        layout.addWidget(group)
        layout.addLayout(row(button('检查候选讲座', lambda: self.run_lecture(True, False)), button('立即报名一轮', lambda: self.run_lecture(False, False), True)))
        clock = self.automation.config.get('lecture', {})
        self.lecture_clock = QCheckBox('每小时 01 分检查并记录新讲座')
        self.lecture_clock.setChecked(clock.get('enabled', False))
        self.lecture_book = QCheckBox('同时自动报名符合筛选条件的雁栖湖讲座')
        self.lecture_book.setChecked(clock.get('book', False))
        self.lecture_hours = QLineEdit(','.join(map(str, clock.get('hours', range(24)))))
        self.lecture_hours.setPlaceholderText('0–23 的小时，用英文逗号分隔')
        for index, check in enumerate(self.days):
            check.setChecked((index + 1) % 7 in clock.get('days', [0, 1, 2, 3, 4, 5, 6]))
        self.lecture_filter_hint = label('自动任务会读取全部讲座，只报名地点明确为雁栖湖的场次。', 'muted')
        layout.addWidget(self.lecture_filter_hint)
        layout.addWidget(self.lecture_clock)
        layout.addWidget(self.lecture_book)
        self.science_daily = QCheckBox('每小时 01 分查询并自动报名科研讲座（仅雁栖湖；同一开始时间只报一场，优先人工智能相关）')
        self.science_daily.setChecked(self.automation.config.get('science', {}).get('enabled', False))
        layout.addWidget(self.science_daily)
        layout.addLayout(row(label('人文自动检查小时'), self.lecture_hours))
        layout.addLayout(row(button('保存自动任务', self.save_lecture_plan, True),
                             button('停用自动任务', lambda: self.disable_plan('lecture'))))
        self.lecture_clock_status = label('', 'muted')
        layout.addWidget(self.lecture_clock_status)
        layout.addWidget(label('人文讲座按保存的检查小时自动运行；科研讲座每小时 01 分查询并自动报名。电脑需保持运行，任务结果见“任务与日志”。', 'muted'))
        layout.addWidget(label('下方同步显示今日讲座、听讲进度与提醒设置；报名成功后请按现场要求完成考勤。', 'banner'))

    def set_lecture_all_day(self, enabled):
        self.lecture_from.setEnabled(not enabled)
        self.lecture_to.setEnabled(not enabled)
        if enabled:
            self.lecture_from.setTime(QTime(0, 0))
            self.lecture_to.setTime(QTime(23, 59))

    def save_lecture_plan(self):
        try:
            if not self.lecture_clock.isChecked():
                self.disable_plan('lecture')
                self.automation.save('science', {'enabled': self.science_daily.isChecked()})
                return
            self.account('sep')
            hours = sorted({int(x.strip()) for x in self.lecture_hours.text().replace('，', ',').split(',') if x.strip()})
            days = [(index + 1) % 7 for index, c in enumerate(self.days) if c.isChecked()]
            if not hours or any(x < 0 or x > 23 for x in hours):
                raise ValueError('检查小时应为 0–23 的整数，用逗号分隔。')
            if not days:
                raise ValueError('请至少选择一天。')
            self.automation.save('lecture', {'enabled': True, 'book': self.lecture_book.isChecked(), 'hours': hours,
                'days': days, 'from': '00:00', 'to': '23:59'})
            self.automation.save('science', {'enabled': self.science_daily.isChecked()})
            self.automation.tick()
        except Exception as exc:
            self.error(str(exc))

    def lecture_data_dir(self):
        import hashlib
        username = self.account_fields['sep'][0].text().strip()
        if not username:
            raise ValueError('请先填写 SEP 账号。')
        return DATA / 'lecture' / hashlib.sha256(username.encode()).hexdigest()[:16]

    def show_lecture_report(self):
        try:
            path = self.lecture_data_dir() / '发布时间观察.md'
            if not path.exists():
                raise ValueError('还没有定点检查记录；首次运行后会生成报告。')
            dialog = QDialog(self)
            dialog.setWindowTitle('讲座发布时间观察（北京时间）')
            dialog.resize(1000, 650)
            layout = QVBoxLayout(dialog)
            view = QPlainTextEdit()
            view.setReadOnly(True)
            view.setPlainText(path.read_text(encoding='utf-8'))
            layout.addWidget(view)
            layout.addWidget(button('打开记录目录', lambda: self.open_path(path.parent)))
            dialog.exec()
        except Exception as exc:
            self.error(str(exc))

    def clear_booking_pause(self):
        try:
            if any(x['module'] in ('lecture', 'lecture-clock') for x in self.jobs.active.values()):
                raise ValueError('请先停用定点计划并停止讲座任务，再核对学校记录。')
            path = self.lecture_data_dir() / 'observations.json'
            state = read_json(path, {})
            if state.get('bookingPending'):
                state['bookingPending'] = False
                write_json(path, state)
            self.statusBar().showMessage('报名暂停已解除。重新保存定点计划后继续；观察历史已保留。')
        except Exception as exc:
            self.error(str(exc))

    def run_lecture(self, preview, scheduled):
        try:
            days = [(index + 1) % 7 for index, c in enumerate(self.days) if c.isChecked()]
            if not days:
                raise ValueError('请至少选择一天。')
            payload = self.account('sep') | {'preview': preview, 'scheduled': scheduled, 'days': days,
                      'from': '00:00', 'to': '23:59',
                      'interval': 30, 'rounds': 1}
            title = '人文讲座 · ' + ('候选预览' if preview else '定时预约' if scheduled else '报名一轮')
            self.start_job('lecture', title, NODE, [ROOT / 'adapters/lecture.mjs'], payload)
        except Exception as exc:
            self.error(str(exc))

    def build_mooc(self):
        layout = self.page('国科大在线', '使用浏览器登录，支持 SEP 跳转或平台自己的登录方式，登录状态保存在本机独立浏览器目录。')
        group = QGroupBox('视频与文档自动任务')
        content = QVBoxLayout(group)
        content.addWidget(label('1. 启动后，在打开的 Edge 中登录国科大在线。\n2. 进入“个人空间 → 课程 → 章节”，打开任意章节。\n3. 识别到已适配页面后自动处理视频和 PDF；结果会显示在任务日志。'))
        self.mooc_url = QLineEdit('https://mooc.ucas.edu.cn/portal')
        self.mooc_url.setPlaceholderText('也可粘贴该课程任意章节的完整 URL')
        content.addWidget(self.mooc_url)
        content.addWidget(button('启动视频 / 文档任务', self.run_mooc, True))
        layout.addWidget(group)
        layout.addWidget(label('当前适配范围：2026 春季页面结构的硕士英语慕课。测验、考试和作业未自动化；其他课程需确认页面兼容。\n若仍有未完成任务，日志会列出，不会显示“整门课程已通过”。', 'banner'))
        layout.addWidget(label('学校手册说明 PC 与 App 学习数据互通，但不可同时使用。运行电脑任务时，请退出手机上的同一课程。', 'muted'))
        layout.addLayout(row(button('打开国科大在线', lambda: QDesktopServices.openUrl(QUrl('https://mooc.ucas.edu.cn/portal'))), button('打开学校使用手册', lambda: QDesktopServices.openUrl(QUrl('https://foreign.ucas.edu.cn/docs/2025-02/e5c8ee6db8424f718909a11c6307c699.pdf')))))
        layout.addStretch()

    def run_mooc(self):
        try:
            self.start_job('mooc', '国科大在线 · 视频 / 文档', NODE, [ROOT / 'adapters/mooc.mjs'], {'url': self.mooc_url.text().strip()})
        except Exception as exc:
            self.error(str(exc))

    def build_planner(self):
        self.planner_layout = self.page('选课规划', '按类别浏览课程，比较教学安排，保存备选。内置 2026 年秋季课表快照；规划结果不会自动提交 SEP。')
        self.planner_status = label('首次打开时加载课表…', 'muted')
        self.planner_layout.addWidget(self.planner_status)
        self.planner_layout.addLayout(row(button('从轻新课堂同步已选课程', lambda: self.sync_enrollment('iclass')),
            button('从 SEP 同步已选课程', lambda: self.sync_enrollment('sep')),
            button('仅把勾选课程导入抢课', self.transfer_courses, True)))
        self.enrollment_status = label('在“规划清单 / 已选状态”中勾选要抢的课程。同步只查询，不选课、不退课。', 'muted')
        self.planner_layout.addWidget(self.enrollment_status)

    def load_planner(self):
        if self.planner:
            return
        try:
            sys.path.insert(0, str(VENDOR / 'UCAS-Course-Selector/src'))
            import coursesystem.paths as paths
            directory = DATA / 'planner'
            directory.mkdir(exist_ok=True)
            paths.data_dir = lambda: directory
            from coursesystem.importer import parse_xlsx, write_db
            from coursesystem.db import CourseDatabase
            from .planner import IntegratedPlanner
            database = directory / 'courses.db'
            if not database.exists():
                parsed = parse_xlsx(VENDOR / 'UCAS-Course-Selector/data/2026年秋季学期课表.xlsx')
                write_db(parsed, database)
            from coursesystem.state import load_state
            saved = load_state()
            saved_db = saved.get('db_path')
            if saved_db:
                candidate = Path(saved_db)
                if not candidate.is_absolute():
                    candidate = directory / candidate
                elif candidate.parent.name == 'planner' and candidate.parent.parent.name == 'data':
                    # Migrate old in-app absolute paths after moving/unzipping the app.
                    relocated = directory / candidate.name
                    if relocated.is_file():
                        candidate = relocated
                if candidate.is_file():
                    database = candidate
            self.planner = IntegratedPlanner(CourseDatabase(database), self.enrollment, directory)
            if not saved.get('ui'):
                campus_index = self.planner.campus_combo.findData('H')
                if campus_index >= 0:
                    self.planner.campus_combo.setCurrentIndex(campus_index)
            self.planner.setWindowFlags(Qt.Widget)
            self.planner.setStyleSheet('')
            splitter = self.planner.splitter
            left, middle, right = [splitter.widget(i) for i in range(3)]
            for panel in (left, middle, right):
                panel.setParent(None)
                panel.setMinimumWidth(0)
            tabs = QTabWidget()
            tabs.addTab(left, '课程库')
            tabs.addTab(right, '规划清单 / 已选状态')
            tabs.addTab(middle, '周课表')
            tabs.addTab(self.planner.alternatives_page, '备选')
            self.planner_tabs = tabs
            splitter.insertWidget(0, tabs)
            header = self.planner.week_view.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Fixed)
            self.planner.week_view.table.setColumnWidth(0, 105)
            self.planner_layout.addWidget(self.planner, 1)
            enable_copy(self.planner)
            count = len(self.planner.db.get_all_courses())
            self.planner_status.setText(f'已载入 {count} 门课程。请在校区筛选中选择“雁栖湖”；以学校最新课表为准。')
            snapshot = self.enrollment.current()
            if snapshot:
                self.enrollment_status.setText(f'上次同步 {snapshot.get("fetched_at", "")} · {len(snapshot.get("courses", []))} 门 · {snapshot.get("semester", "")}; 已选状态以该次查询为准。')
        except Exception as exc:
            self.planner_status.setText('加载失败：' + str(exc))
            self.error(str(exc))

    def transfer_courses(self):
        if not self.planner:
            self.load_planner()
        if self.planner:
            codes = self.planner.checked_pending_codes()
            if not codes:
                self.planner_tabs.setCurrentIndex(1)
                self.error('请在“规划清单 / 已选状态”中勾选要抢的课程。已选上的课程不会重复导入。')
                return
            self.course_codes.setPlainText('\n'.join(codes))
            self.nav.setCurrentRow(5)

    def sync_enrollment(self, source):
        if not self.planner:
            self.load_planner()
        if not self.planner:
            return
        try:
            account = self.account(source)
            version = self.account_version(source)
            self.enrollment_status.setText('正在只读查询已选课程…')
            if source == 'iclass':
                self.background(lambda: IClass(**account).my_courses(),
                    lambda result: self.enrollment_received(result, account['username'], source, version),
                    lambda error: self.enrollment_error(error))
            else:
                job = self.jobs.start('account-sep', 'SEP 已选课程同步 · 只读', PYTHON,
                    [ROOT / 'adapters/account_worker.py'], account | {'action': 'courses'})
                self.account_jobs[job] = {'version': version, 'account': account['username'], 'action': 'courses'}
        except Exception as exc:
            self.enrollment_error(str(exc))

    def enrollment_error(self, error):
        self.enrollment_status.setText('同步未完成，已保留上次结果。')
        self.error(error)

    def enrollment_received(self, snapshot, username, source, version):
        if self.account_version(source) != version:
            self.enrollment_status.setText('查询期间账号已修改，本次结果未应用，请重新同步。')
            return
        try:
            self.enrollment.save(snapshot, username)
            count, unresolved = self.planner.apply_enrollment()
            self.planner_tabs.setCurrentIndex(1)
            self.enrollment_status.setText(f'已同步 {len(snapshot["courses"])} 门，加入规划 {count} 门；未匹配 {len(unresolved)} 门。查询时间：{snapshot["fetched_at"]}')
            if unresolved:
                self.error('以下课程未能唯一匹配，未随意加入其他同名课程：\n' + '\n'.join(f'{x["code"]} {x["name"]}：{x["reason"]}' for x in unresolved))
        except Exception as exc:
            self.enrollment_error(str(exc))

    def build_selection(self):
        layout = self.page('自动选课', '使用个人信息页保存的 SEP 账号自动登录；验证码或邮箱验证需要在浏览器中完成。')
        layout.addWidget(self.profile_link('SEP 自动选课'))
        layout.addWidget(button('从规划中导入勾选课程', self.transfer_courses))
        layout.addWidget(label('目标课程编码（每行一门；请复制完整课程编码）'))
        self.course_codes = QPlainTextEdit()
        self.course_codes.setPlaceholderText('可从“选课规划”一键带入，或粘贴 SEP 中的完整课程编码。')
        self.course_codes.setMaximumHeight(84)
        layout.addWidget(self.course_codes)
        self.selection_summary = label('填入编号后显示对应课程；可横向滚动查看全部字段，双击打开详情。', 'muted')
        layout.addWidget(self.selection_summary)
        self.selection_table = QTableWidget(0, 9)
        self.selection_table.setHorizontalHeaderLabels(['课程名称', '学时', '学分', '学院', '主讲教师', '一级学科 / 专业学位类别', '课程类别', '完整课程编号', '核对状态'])
        self.selection_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.selection_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.selection_table.setAlternatingRowColors(True)
        self.selection_table.verticalHeader().setVisible(False)
        self.selection_table.verticalHeader().setDefaultSectionSize(42)
        for column, width in enumerate([210, 58, 58, 170, 125, 220, 120, 210, 210]):
            self.selection_table.setColumnWidth(column, width)
        self.selection_table.cellDoubleClicked.connect(self.selection_details)
        layout.addWidget(self.selection_table, 1)
        self.selection_refresh = QTimer(self)
        self.selection_refresh.setSingleShot(True)
        self.selection_refresh.setInterval(200)
        self.selection_refresh.timeout.connect(self.refresh_selection_courses)
        self.course_codes.textChanged.connect(self.selection_refresh.start)
        self.select_timed = QCheckBox('在指定时间开始')
        self.select_time = QDateTimeEdit(QDateTime.currentDateTime().addSecs(300))
        self.select_time.setDisplayFormat('yyyy-MM-dd HH:mm:ss')
        self.select_time.setCalendarPopup(True)
        self.select_repeat = QCheckBox('课程满员时轮询余量')
        self.select_interval = QSpinBox()
        self.select_interval.setRange(30, 3600)
        self.select_interval.setValue(60)
        self.select_interval.setSuffix(' 秒')
        self.select_rounds = QSpinBox()
        self.select_rounds.setRange(1, 240)
        self.select_rounds.setValue(30)
        layout.addLayout(row(self.select_timed, self.select_time))
        layout.addLayout(row(self.select_repeat, label('间隔'), self.select_interval, label('最多'), self.select_rounds, label('轮')))
        layout.addWidget(label('有空位时识别验证码并提交；成功以课程进入预选列表为准。触发限流、提交结果不明或其他拒绝时会停止相应任务。', 'banner'))
        layout.addLayout(row(button('仅检查目标课程，不提交', lambda: self.run_selection(True)), button('开始自动选课', lambda: self.run_selection(False), True)))
        layout.addWidget(label('结束后请核对 SEP 的预选列表，并完成学校要求的选课单审核。', 'muted'))

    def refresh_selection_courses(self):
        codes = list(dict.fromkeys(self.course_codes.toPlainText().split()))
        self.selection_table.setRowCount(len(codes))
        if not codes:
            self.selection_summary.setText('尚未添加目标课程。可从规划勾选导入，或粘贴完整编号。')
            return
        if not self.planner:
            self.load_planner()
        from .catalog import colors
        from PySide6.QtGui import QColor
        catalog = self.planner.catalog if self.planner else None
        matched = 0
        for row_index, code in enumerate(codes):
            course = catalog.resolve(code) if catalog else None
            if course:
                info = catalog.info(course)
                values = [info[k] for k in ('name', 'hours', 'credits', 'department', 'teacher', 'discipline', 'category')]
                values += [code, self.enrollment.status(course)[0]]
                matched += 1
                bg, fg = colors(info['category'])
            else:
                values = ['未唯一匹配，请核对完整编号'] + ['未提供'] * 6 + [code, '当前课程库未匹配']
                bg, fg = '#fff3cc', '#81600d'
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, course.id if course else None)
                item.setToolTip(str(value) + '\n本地课表快照；双击查看教学安排。')
                if column in (0, 6):
                    item.setBackground(QColor(bg))
                    item.setForeground(QColor(fg))
                self.selection_table.setItem(row_index, column, item)
        self.selection_summary.setText(f'待抢 {len(codes)} 门 · 已匹配 {matched} 门 · 未匹配 {len(codes) - matched} 门。信息来自本地课表快照，余量以 SEP 实时检查为准。')

    def selection_details(self, row_index, column):
        item = self.selection_table.item(row_index, 0)
        if item and self.planner:
            self.planner.show_course(item.data(Qt.UserRole))

    def run_selection(self, preview):
        try:
            codes = list(dict.fromkeys(self.course_codes.toPlainText().split()))
            if not codes:
                raise ValueError('请先填写目标课程编码。')
            start_at = self.select_time.dateTime().toString('yyyy-MM-ddTHH:mm:ss') if self.select_timed.isChecked() else None
            payload = self.account('sep') | {'codes': codes, 'preview': preview, 'start_at': start_at,
                       'interval': self.select_interval.value(), 'rounds': self.select_rounds.value() if self.select_repeat.isChecked() and not preview else 1}
            if self.planner:
                payload['course_semesters'] = {code: '|'.join(sorted({s.semester for s in course.schedules}))
                    for code in codes if (course := self.planner.catalog.resolve(code))}
            self.start_job('selection', f'选课{"预览" if preview else "任务"} · {len(codes)} 门', PYTHON, [ROOT / 'adapters/selection_worker.py'], payload)
        except Exception as exc:
            self.error(str(exc))

    def build_jobs(self):
        layout = self.page('任务与日志', '“已结束”表示脚本正常退出，具体报名 / 签到 / 选课结果以日志和学校记录为准。')
        controls = row(button('刷新', self.refresh_jobs), button('停止选中任务', self.stop_selected), button('停止全部任务', self.stop_all_tasks), button('打开日志目录', lambda: self.open_path(LOGS)))
        layout.addLayout(controls)
        split = QSplitter(Qt.Vertical)
        self.job_table = table(['任务', '模块', '状态', '开始时间', '最后更新'])
        self.job_table.itemSelectionChanged.connect(self.show_selected_log)
        split.addWidget(self.job_table)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(3000)
        self.log_highlighter = LogHighlighter(self.log_view.document())
        split.addWidget(self.log_view)
        split.setSizes([270, 400])
        layout.addWidget(split, 1)

    def refresh_jobs(self):
        items = self.store.list()
        for item in items:
            if item['id'] in self.account_jobs and item['id'] not in self.jobs.active:
                meta = self.account_jobs.pop(item['id'])
                if not self._quitting:
                    self.checked_account('sep', meta['version'], False, '检测或同步未完成，请查看任务日志；没有把旧会话当成密码验证成功。')
                if meta['action'] == 'courses':
                    self.enrollment_status.setText('同步未完成，保留上次结果。')
        selected = self.current_log
        self.job_table.blockSignals(True)
        self.job_table.setRowCount(len(items))
        for index, item in enumerate(items):
            values = [item['title'], item['module'], STATUS.get(item['status'], item['status']), item['created'], item['updated']]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.UserRole, item['id'])
                color_item(cell, {'completed': 'success', 'failed': 'failed', 'attention': 'pending', 'running': 'running', 'stopping': 'pending'}.get(item['status'], 'stopped'))
                self.job_table.setItem(index, column, cell)
            if item['id'] == selected:
                self.job_table.selectRow(index)
        self.job_table.blockSignals(False)
        self.home_status.setText(f'5 个功能模块已接入   ·   {len(self.jobs.active)} 项任务运行中   ·   {len(items)} 条任务记录')
        self.refresh_dashboard()

    def select_job(self, job_id):
        self.refresh_jobs()
        for index in range(self.job_table.rowCount()):
            if self.job_table.item(index, 0).data(Qt.UserRole) == job_id:
                self.job_table.selectRow(index)
                self.show_selected_log()
                break

    def show_selected_log(self):
        index = self.job_table.currentRow()
        if index < 0:
            return
        self.current_log = self.job_table.item(index, 0).data(Qt.UserRole)
        path = LOGS / f'{self.current_log}.log'
        self.log_view.setPlainText(redact(path.read_text(encoding='utf-8')[-150000:], self.vault.secret_values()) if path.exists() else '等待任务输出…')

    def receive_output(self, job_id, text):
        for line in text.splitlines():
            if not line.startswith('{'):
                continue
            try:
                message = json.loads(line)
                self.refresh_receive_event(job_id, message)
                self.activity_event(job_id, message)
                meta = self.account_jobs.get(job_id)
                if meta and message.get('event') == 'account.check':
                    self.checked_account('sep', meta['version'], message.get('status') == 'valid', message.get('message', '检测未完成'))
                    if meta['action'] == 'courses' and message.get('status') != 'valid':
                        self.enrollment_status.setText('SEP 同步未完成，保留上次结果。')
                    self.account_jobs.pop(job_id, None)
                elif meta and message.get('event') == 'account.courses':
                    self.enrollment_received(message['snapshot'], meta['account'], 'sep', meta['version'])
                    self.account_jobs.pop(job_id, None)
                if message.get('event') == 'iclass.daily-plan' and isinstance(message.get('courses'), list):
                    if self.course_date.date().toString('yyyyMMdd') == message.get('date'):
                        self.populate_courses(message['courses'])
            except (ValueError, AttributeError):
                pass
        if job_id == self.current_log:
            self.log_view.moveCursor(QTextCursor.MoveOperation.End)
            self.log_view.insertPlainText(text)

    def stop_selected(self):
        if self.current_log:
            item = self.jobs.active.get(self.current_log, {})
            if item.get('module') in ('iclass-daily', 'lecture-clock'):
                self.disable_plan('course' if item['module'] == 'iclass-daily' else 'lecture')
                return
            self.jobs.stop(self.current_log)

    def build_settings(self):
        layout = self.page('设置与更新', '模块来源、固定版本和维护接口都保留在本地，便于后续升级。')
        if (ROOT / 'runtime/modules-downloads.json').is_file():
            group = QGroupBox('便携版组件')
            content = QVBoxLayout(group)
            content.addWidget(label('Python、Node 和基础功能已内置。讲座预约与抢课的外部模块由下方按钮直接从原作者仓库获取；完成后即可使用，无需命令行。', 'muted'))
            content.addWidget(button('一键启用讲座预约与抢课', self.install_portable_modules, True))
            layout.addWidget(group)
        self.module_table = table(['模块', '上游最后提交', '固定提交', '本地能力'])
        modules = read_json(ROOT / 'modules.json', [])
        self.module_table.setRowCount(len(modules))
        for index, module in enumerate(modules):
            for column, value in enumerate([module['name'], module['updated'], module['commit'][:10], module['capabilities']]):
                self.module_table.setItem(index, column, QTableWidgetItem(value))
        layout.addWidget(self.module_table, 1)
        layout.addLayout(row(button('检查上游新版本', self.update_check), button('下载更新到暂存目录', self.update_stage), button('维护与接口说明', lambda: self.open_path(ROOT / 'docs/维护与接口.md'))))
        self.update_status = label('检查更新只读取远端提交；暂存下载不会覆盖当前工作版本和账号数据。', 'muted')
        layout.addWidget(self.update_status)
        group = QGroupBox('本地 API 与手机状态面板')
        form = QVBoxLayout(group)
        self.api_status = label('API 启动中…')
        form.addWidget(self.api_status)
        self.lan = QCheckBox('允许同一局域网的手机查看任务状态（保存后重启生效）')
        self.lan.setChecked(self.settings.get('lan', False))
        form.addWidget(self.lan)
        form.addLayout(row(button('保存设置', self.save_settings), button('复制手机面板地址', self.copy_mobile), button('iOS 安装方式', lambda: self.open_path(ROOT / 'docs/iOS说明.md'))))
        form.addWidget(label('手机面板是只读网页，可在 Safari 中添加到主屏幕。Windows 自动任务必须继续运行。', 'muted'))
        layout.addWidget(group)

    def install_portable_modules(self):
        if any(item.get('module') == 'module-install' for item in self.jobs.active.values()):
            self.error('组件正在准备中，请在“任务与日志”查看进度。')
            return
        self.start_job('module-install', '下载并启用外部组件', PYTHON,
                       [ROOT / 'adapters/install_modules.py'], {'modules': ['lecture', 'selection']})

    def update_check(self):
        self.background(check_updates, lambda results: self.update_status.setText('\n'.join(f'{x["name"]}：' + (x.get('error') or ('有新提交 ' + x['latest'][:10] if x.get('update') else '与上游一致')) for x in results)))

    def update_stage(self):
        self.background(stage_updates, lambda paths: self.update_status.setText('已暂存：\n' + '\n'.join(paths) if paths else '未发现需要暂存的新版本，请先检查更新。'))

    def save_settings(self):
        self.settings['lan'] = self.lan.isChecked()
        write_json(DATA / 'settings.json', self.settings)
        self.statusBar().showMessage('设置已保存，重启应用后生效。')

    def copy_mobile(self):
        if not self.api:
            self.error('API 未启动。')
            return
        if self.api.server.server_address[0] != '0.0.0.0':
            self.error('请先启用局域网访问，保存并重启应用。')
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(('223.5.5.5', 80))
            address = sock.getsockname()[0]
        finally:
            sock.close()
        QApplication.clipboard().setText(f'http://{address}:8765/mobile/#{self.api.token}')
        self.statusBar().showMessage('手机地址已复制，其中包含访问密钥，请仅用于自己的设备。')

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        if index == 2: self.refresh_today_lectures()
        if index == 4 and not self.planner:
            QTimer.singleShot(0, self.load_planner)
        if index == 5:
            self.selection_refresh.start()

    def open_path(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def closeEvent(self, event):
        if not self._quitting and self.tray and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide_to_tray()
            return
        self._quitting = True
        self.shutdown()
        event.accept()
        QApplication.instance().quit()

    def shutdown(self):
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self._quitting = True
        if self.tray:
            self.tray.hide()
        self.clock.stop()
        self.automation.timer.stop()
        self.lecture_timer.stop()
        for popup in list(self._lecture_popups): popup.close()
        self.jobs.stop_all()
        if self.planner:
            self.planner._save_state()
            from coursesystem.state import save_state
            save_state(ui=self.planner._collect_ui_state())
        if self.api:
            self.api.close()
        # Queries are bounded by HTTP timeouts; avoid deleting a live QRunnable.
        self.pool.waitForDone(20000)


STYLE = '''
* { font-family: __UI_FONT_STACK__; font-size: 13px; }
QMainWindow, QWidget { background: #f5f7f5; color: #203c35; }
QWidget#sidebar, QWidget#sidebar QLabel { background: #173d35; color: #e7f2e8; }
QLabel#brand { font-size: 31px; font-weight: 800; letter-spacing: 3px; }
QLabel#sideText { color: #b6cfc1; font-size: 12px; line-height: 1.6; }
QListWidget#navigation { border: 0; background: #173d35; color: #d9e9df; outline: 0; }
QListWidget#navigation::item { padding: 13px 9px; margin-bottom: 5px; border-radius: 7px; }
QListWidget#navigation::item:selected { background: #315f50; color: white; }
QListWidget { background: white; border: 1px solid #d5dfd6; }
QTabWidget::pane { border: 1px solid #d5dfd6; }
QTabBar::tab { background: #eaf1eb; padding: 9px 14px; }
QTabBar::tab:selected { background: white; color: #286449; }
QLabel#title { font-size: 25px; font-weight: 700; color: #163f34; }
QLabel#muted { color: #65796e; font-size: 12px; }
QLabel#banner { background: #e6f0e7; color: #2d5a41; border: 1px solid #cddfcf; padding: 13px; border-radius: 9px; }
QGroupBox { border: 1px solid #d5dfd6; border-radius: 11px; margin-top: 12px; padding: 20px 14px 14px; background: #fff; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 5px; color: #27543e; }
QGroupBox QLabel, QGroupBox QCheckBox { background: transparent; font-weight: 400; }
QCheckBox { spacing: 9px; min-height: 26px; }
QCheckBox::indicator, QAbstractItemView::indicator, QGroupBox::indicator, QMenu::indicator {
    width: 20px; height: 20px; border: 2px solid #607c6b; border-radius: 4px; background: #ffffff;
}
QCheckBox::indicator:hover, QAbstractItemView::indicator:hover { border-color: #174e35; background: #e7f2ea; }
QCheckBox::indicator:checked, QAbstractItemView::indicator:checked, QGroupBox::indicator:checked, QMenu::indicator:checked {
    background: #246347; border-color: #174e35; image: url("__CHECK_ICON__");
}
QCheckBox::indicator:disabled, QAbstractItemView::indicator:disabled { border-color: #a2afa7; background: #dde5df; }
QCheckBox::indicator:checked:disabled, QAbstractItemView::indicator:checked:disabled { background: #819f8b; image: url("__CHECK_ICON__"); }
QPushButton { background: #fff; color: #285741; border: 1px solid #c4d8c8; border-radius: 7px; padding: 9px 13px; min-height: 19px; }
QPushButton:hover { background: #e6f0e7; border-color: #8cb599; }
QPushButton#primary { background: #286449; color: white; border-color: #286449; }
QPushButton#primary:hover { background: #347856; }
QLineEdit, QPlainTextEdit, QSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit, QComboBox { background: white; border: 1px solid #ccd9cf; border-radius: 6px; padding: 7px; selection-background-color: #36775a; }
QTableWidget { background: white; alternate-background-color: #f1f6f1; border: 1px solid #d7e2d7; border-radius: 6px; gridline-color: #e9eee9; }
QHeaderView::section { background: #eaf1eb; color: #315b46; border: none; border-bottom: 1px solid #cedecf; padding: 8px; }
QTableWidget::item:selected { background: #d1e7d5; color: #153d28; }
QStatusBar { background: #eaf0ea; color: #536b5c; }
'''.replace('__CHECK_ICON__', (ROOT / 'assets/check.svg').as_posix())
