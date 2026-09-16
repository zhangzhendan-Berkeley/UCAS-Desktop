from __future__ import annotations
from datetime import datetime
import json
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
from .iclass import IClass, course_id, match_lecture_course
from .api import LocalAPI

STATUS = {'running': '运行中', 'stopping': '停止中', 'completed': '已结束', 'failed': '失败 / 有未完成项', 'stopped': '已停止', 'interrupted': '已中断'}


def load_fonts():
    for font in ('msyh.ttc', 'msyhbd.ttc', 'segoeui.ttf'):
        path = Path('C:/Windows/Fonts') / font
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    QApplication.setFont(QFont('Microsoft YaHei', 10))


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


class Window(QMainWindow):
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
        self.pool = QThreadPool.globalInstance()
        self.workers = []
        self.courses = []
        self.account_fields = {}
        self.settings = read_json(DATA / 'settings.json', {})
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
        self.nav.addItems(['概览', '课程与讲座签到', '人文讲座预约', '国科大在线', '选课规划', '自动选课', '任务与日志', '设置与更新'])
        side.addWidget(self.nav)
        self.runtime_hint = label('本地运行 · v0.1.0\n关闭窗口后托盘运行\n右键托盘可退出程序', 'sideText')
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
        self.nav.currentRowChanged.connect(self.navigate)
        self.nav.setCurrentRow(0)
        self.jobs.changed.connect(self.refresh_jobs)
        self.jobs.output.connect(self.receive_output)
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
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(28, 25, 28, 22)
        layout.setSpacing(16)
        layout.addWidget(label(title, 'title'))
        layout.addWidget(label(subtitle, 'muted'))
        self.pages.addWidget(widget)
        return layout

    def error(self, text):
        QMessageBox.warning(self, '需要处理', redact(text, self.vault.secret_values()))

    def background(self, function, callback):
        self.statusBar().showMessage('正在处理，请稍候…')
        worker = Work(function)
        self.workers.append(worker)
        worker.signals.done.connect(callback)
        worker.signals.error.connect(self.error)
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
        remember = QCheckBox('记住账号密码（使用当前 Windows 账户加密）')
        remember.setChecked(bool(existing['password']))
        form.addRow('账号', user)
        form.addRow('密码', password)
        form.addRow(remember)
        self.account_fields[key] = (user, password, remember)
        return group

    def account(self, key):
        user, password, remember = self.account_fields[key]
        if not user.text().strip() or not password.text():
            raise ValueError('请填写此模块的账号和密码。')
        self.vault.set(key, user.text(), password.text(), remember.isChecked())
        return self.vault.get(key).copy()

    def build_home(self):
        layout = self.page('把校园事务放在一起', '已按雁栖湖校区配置。选课规划可直接使用，学校账号相关功能需首次登录验证。')
        self.home_status = label('正在加载模块…', 'banner')
        layout.addWidget(self.home_status)
        grid = QGridLayout()
        cards = [
            ('课程与讲座签到', '查询当天课表，选择课程定时签到。讲座可使用同协议二维码或排课 ID。', 1),
            ('人文讲座预约', '按可参加的星期和时段筛选，支持预览、报名及定时巡检。', 2),
            ('国科大在线', '自动处理已适配的英语慕课视频、文档。测验与考试需另行完成。', 3),
            ('选课规划', '内置 2026 秋季课表；按雁栖湖筛选，检查周次冲突并导出计划。', 4),
            ('自动选课', '手动登录 SEP 后批量提交目标课程，支持定时启动与余量轮询。', 5),
            ('任务与日志', '查看每项任务的实际结果，停止自动任务，保留运行记录。', 6),
        ]
        for index, (title, description, page) in enumerate(cards):
            card = QGroupBox(title)
            content = QVBoxLayout(card)
            content.addWidget(label(description, 'muted'))
            content.addWidget(button('打开模块 →', lambda checked=False, p=page: self.nav.setCurrentRow(p)))
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        layout.addWidget(label('验证边界：程序可运行 ≠ 学校已确认操作成功。查看任务日志中的返回结果，并在学校系统核对记录。', 'muted'))
        layout.addLayout(row(button('打开使用说明', lambda: self.open_path(ROOT / '使用指南.md')), button('查看来源与验证记录', lambda: self.open_path(ROOT / 'docs/项目筛选与验证.md'))))
        layout.addStretch()

    def build_iclass(self):
        layout = self.page('课程与讲座签到', '轻新课堂。自动任务仅处理你选中的排课；需要电脑保持联网且不休眠。')
        layout.addWidget(self.account_form('iclass', '轻新课堂账号', '学号'))
        self.course_date = QDateEdit(QDate.currentDate())
        self.course_date.setCalendarPopup(True)
        self.course_date.setDisplayFormat('yyyy-MM-dd')
        self.before = QSpinBox()
        self.before.setRange(0, 30)
        self.before.setValue(5)
        self.before.setSuffix(' 分钟')
        layout.addLayout(row(label('日期'), self.course_date, button('查询课表', self.query_courses, True), label('开课前'), self.before,
                             button('为勾选课程建立自动签到任务', self.schedule_courses)))
        self.course_table = table(['选择', '课程 / 讲座', '教师', '开始', '结束', '签到状态', '排课 ID'])
        layout.addWidget(self.course_table, 1)
        manual = QGroupBox('讲座 / 手动排课 ID：仅支持轻新课堂 courseSchedId 二维码')
        form = QVBoxLayout(manual)
        self.science_rows = []
        self.selected_science = None
        self.science_status = label('科研讲座时间表：尚未查询', 'muted')
        self.science_choose = button('选择讲座并填入时间', self.choose_science_lecture)
        self.science_choose.setEnabled(False)
        self.science_match = button('从轻新课堂自动匹配场次', self.match_science_lecture)
        self.science_match.setEnabled(False)
        form.addLayout(row(button('查询科研讲座时间表', self.query_science_schedule), self.science_choose, self.science_match))
        form.addWidget(self.science_status)
        self.lecture_id = QLineEdit()
        self.lecture_id.setPlaceholderText('粘贴二维码解析出的完整链接，或 7 位排课 ID')
        form.addLayout(row(self.lecture_id, button('读取二维码图片', self.decode_qr), button('立即签到', self.sign_manual, True)))
        self.lecture_start = QDateTimeEdit(QDateTime.currentDateTime())
        self.lecture_end = QDateTimeEdit(QDateTime.currentDateTime().addSecs(7200))
        for box in (self.lecture_start, self.lecture_end):
            box.setDisplayFormat('yyyy-MM-dd HH:mm')
            box.setCalendarPopup(True)
        form.addLayout(row(label('讲座开始'), self.lecture_start, label('结束'), self.lecture_end,
                           button('建立讲座定时签到任务', self.schedule_lecture)))
        form.addWidget(label('如果讲座未出现在课表，需提供该场次的二维码 / 排课 ID 及时间。刷卡考勤和其他二维码协议尚不支持。', 'muted'))
        layout.addWidget(manual)

    def query_science_schedule(self):
        try:
            payload = self.account('sep') | {'action': 'science-schedule', 'preview': True}
            self.start_job('lecture', '科研讲座时间表 · 只读查询', NODE, [ROOT / 'adapters/lecture.mjs'], payload)
        except Exception as exc:
            self.error('请先在“人文讲座预约”填写 SEP 账号。' + str(exc))

    def choose_science_lecture(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('科研讲座时间表 · 选择后填入签到时间')
        dialog.resize(1040, 530)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label('来自选课系统当前页面。请确认讲座与二维码是同一场；选择时间不会自动创建或提交签到任务。', 'muted'))
        entries = table(['讲座名称', '时间', '地点'])
        entries.setRowCount(len(self.science_rows))
        for index, item in enumerate(self.science_rows):
            for column, key in enumerate(('title', 'time', 'location')):
                entries.setItem(index, column, QTableWidgetItem(item.get(key, '')))
        layout.addWidget(entries)

        def use_selected():
            index = entries.currentRow()
            if index < 0:
                return
            item = self.science_rows[index]
            start = QDateTime.fromString(item.get('start', ''), 'yyyy-MM-dd HH:mm:ss')
            end = QDateTime.fromString(item.get('end', ''), 'yyyy-MM-dd HH:mm:ss')
            if not start.isValid() or not end.isValid() or end <= start:
                self.error('该场时间不完整或无法识别，请在学校页面核实后手动填写。')
                return
            self.lecture_start.setDateTime(start)
            self.lecture_end.setDateTime(end)
            self.lecture_id.clear()
            self.selected_science = item
            self.science_match.setEnabled(True)
            self.science_status.setText('时间已填，可匹配轻新课堂场次或补充二维码：' + item['title'])
            dialog.accept()

        layout.addLayout(row(button('填入选中场次时间', use_selected, True), button('取消', dialog.reject)))
        dialog.exec()

    def match_science_lecture(self):
        if not self.selected_science:
            return
        try:
            lecture = dict(self.selected_science)
            account = self.account('iclass')
            date = lecture['start'][:10].replace('-', '')

            def received(courses):
                if self.selected_science != lecture:
                    return
                self.course_date.setDate(QDate.fromString(date, 'yyyyMMdd'))
                self.populate_courses(courses)
                matched = match_lecture_course(lecture, courses)
                if matched:
                    self.lecture_id.setText(matched['id'])
                    self.science_status.setText('已匹配本人课表中的唯一同名、同起止时间场次。请确认后建立定时签到任务。')
                else:
                    self.lecture_id.clear()
                    self.science_status.setText('本人轻新课堂课表中没有唯一匹配项，仍需现场二维码；不会用讲座系统编号推算。')

            self.background(lambda: IClass(**account).query(date), received)
        except Exception as exc:
            self.error(str(exc))

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
                self.course_table.setItem(index, column, QTableWidgetItem(text))
        self.statusBar().showMessage(f'查询到 {len(courses)} 节课程 / 排课。')

    def start_job(self, module, title, program, args, payload):
        if module in ('lecture', 'selection', 'mooc'):
            entry = next(m for m in read_json(ROOT / 'modules.json', []) if m['id'] == module)
            if not (ROOT / entry['path']).is_dir():
                command = 'python scripts/setup.py' + (' --with-external-modules' if entry.get('external_opt_in') else '')
                raise ValueError(f'此模块尚未安装。请按 README 执行：{command}')
            if module == 'mooc' and not (ROOT / 'adapters/mooc_helpers.mjs').is_file():
                raise ValueError('慕课适配器尚未生成，请重新运行 python scripts/setup.py。')
        job_id = self.jobs.start(module, title, program, args, payload)
        self.nav.setCurrentRow(6)
        self.select_job(job_id)

    def schedule_courses(self):
        try:
            courses = [course for index, course in enumerate(self.courses) if self.course_table.item(index, 0).checkState() == Qt.Checked]
            if not courses:
                raise ValueError('请先查询课表并勾选需要签到的课程。')
            payload = self.account('iclass') | {'mode': 'scheduled', 'courses': courses, 'minutes_before': self.before.value()}
            self.start_job('iclass', f'课程自动签到 · {len(courses)} 节', PYTHON, [ROOT / 'adapters/iclass_worker.py'], payload)
        except Exception as exc:
            self.error(str(exc))

    def sign_manual(self):
        try:
            identifier = course_id(self.lecture_id.text())
            payload = self.account('iclass') | {'mode': 'single', 'identifier': identifier}
            self.start_job('iclass-manual', f'轻新课堂签到 · {identifier}', PYTHON, [ROOT / 'adapters/iclass_worker.py'], payload)
        except Exception as exc:
            self.error(str(exc))

    def schedule_lecture(self):
        try:
            identifier = course_id(self.lecture_id.text())
            start = self.lecture_start.dateTime()
            end = self.lecture_end.dateTime()
            if end <= start or end <= QDateTime.currentDateTime():
                raise ValueError('结束时间应晚于开始时间和当前时间。')
            course = {'id': identifier, 'courseName': '讲座 ' + identifier, 'signStatus': '0',
                      'classBeginTime': start.toString('yyyy-MM-dd HH:mm:ss'), 'classEndTime': end.toString('yyyy-MM-dd HH:mm:ss')}
            payload = self.account('iclass') | {'mode': 'scheduled', 'courses': [course], 'minutes_before': 0, 'manual': True}
            self.start_job('lecture-sign', f'讲座定时签到 · {identifier}', PYTHON, [ROOT / 'adapters/iclass_worker.py'], payload)
        except Exception as exc:
            self.error(str(exc))

    def decode_qr(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择二维码图片', '', '图片 (*.png *.jpg *.jpeg *.bmp)')
        if not path:
            return
        try:
            import cv2
            import numpy as np
            data = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if data is None:
                raise ValueError('无法读取图片。')
            text, points, _ = cv2.QRCodeDetector().detectAndDecode(data)
            if not text:
                raise ValueError('未识别到二维码，请使用清晰、完整的图片。')
            course_id(text)
            self.lecture_id.setText(text)
        except Exception as exc:
            self.error(str(exc))

    def build_lecture(self):
        layout = self.page('人文讲座预约', '使用 SEP 的人文讲座报名入口。先查看候选结果，再按自己的空闲时间建立报名任务。')
        layout.addWidget(self.account_form('sep', 'SEP 信息门户账号', 'SEP 登录邮箱 / 账号'))
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
        self.lecture_from = QTimeEdit(QTime(18, 0))
        self.lecture_to = QTimeEdit(QTime(22, 0))
        self.lecture_interval = QSpinBox()
        self.lecture_interval.setRange(5, 180)
        self.lecture_interval.setValue(30)
        self.lecture_interval.setSuffix(' 分钟')
        self.lecture_rounds = QSpinBox()
        self.lecture_rounds.setRange(1, 144)
        self.lecture_rounds.setValue(12)
        form.addLayout(row(label('讲座开始时段'), self.lecture_from, label('至'), self.lecture_to))
        form.addLayout(row(label('巡检间隔'), self.lecture_interval, label('最多巡检'), self.lecture_rounds, label('次')))
        form.addWidget(label('首次登录时会打开浏览器；出现新设备或邮箱验证时，在浏览器内完成。达到学校页面显示的预约配额后停止。', 'muted'))
        layout.addWidget(group)
        layout.addLayout(row(button('只检查候选讲座', lambda: self.run_lecture(True, False)), button('报名一轮', lambda: self.run_lecture(False, False), True), button('开始定时巡检与报名', lambda: self.run_lecture(False, True))))
        layout.addWidget(label('预约成功不等于已签到。签到在“课程与讲座签到”中单独建立任务。', 'banner'))
        layout.addStretch()

    def run_lecture(self, preview, scheduled):
        try:
            days = [(index + 1) % 7 for index, c in enumerate(self.days) if c.isChecked()]
            if not days or self.lecture_to.time() <= self.lecture_from.time():
                raise ValueError('请至少选一天，并设置有效的起止时段。')
            payload = self.account('sep') | {'preview': preview, 'scheduled': scheduled, 'days': days,
                      'from': self.lecture_from.time().toString('HH:mm'), 'to': self.lecture_to.time().toString('HH:mm'),
                      'interval': self.lecture_interval.value(), 'rounds': self.lecture_rounds.value()}
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
        self.planner_layout = self.page('选课规划', '内置上游 2026 年秋季课表快照。规划结果不会自动提交 SEP；可以将选中的课程编码发送到“自动选课”。')
        self.planner_status = label('首次打开时加载课表…', 'muted')
        self.planner_layout.addWidget(self.planner_status)
        self.planner_layout.addWidget(button('把规划中已选课程发送到自动选课', self.transfer_courses))

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
            from coursesystem.main_window import MainWindow
            database = directory / 'courses.db'
            if not database.exists():
                parsed = parse_xlsx(VENDOR / 'UCAS-Course-Selector/data/2026年秋季学期课表.xlsx')
                write_db(parsed, database)
            from coursesystem.state import load_state
            saved = load_state()
            saved_db = saved.get('db_path')
            if saved_db and Path(saved_db).is_file():
                database = Path(saved_db)
            self.planner = MainWindow(CourseDatabase(database))
            if not saved.get('ui'):
                campus_index = self.planner.campus_combo.findData('H')
                if campus_index >= 0:
                    self.planner.campus_combo.setCurrentIndex(campus_index)
            self.planner.setWindowFlags(Qt.Widget)
            self.planner.setStyleSheet('')
            splitter = self.planner.splitter
            left, middle, right = [splitter.widget(i) for i in range(3)]
            left.setParent(None)
            right.setParent(None)
            left.setMinimumWidth(0)
            right.setMinimumWidth(0)
            middle.setMinimumWidth(420)
            tabs = QTabWidget()
            tabs.setMinimumWidth(310)
            tabs.addTab(left, '课程库')
            tabs.addTab(right, '已选课程 / 学分')
            splitter.insertWidget(0, tabs)
            splitter.setSizes([350, 730])
            self.planner.course_table.setColumnWidth(0, 150)
            self.planner.course_table.setColumnWidth(2, 40)
            self.planner.course_table.setColumnWidth(3, 40)
            header = self.planner.week_view.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Fixed)
            self.planner.week_view.table.setColumnWidth(0, 105)
            self.planner_layout.addWidget(self.planner, 1)
            count = len(self.planner.db.get_all_courses())
            self.planner_status.setText(f'已载入 {count} 门课程。请在校区筛选中选择“雁栖湖”；以学校最新课表为准。')
        except Exception as exc:
            self.planner_status.setText('加载失败：' + str(exc))
            self.error(str(exc))

    def transfer_courses(self):
        if not self.planner:
            self.load_planner()
        if self.planner:
            codes = [course.code for course in self.planner.selected.values()]
            if not codes:
                self.error('请先在选课规划中双击选择课程。')
                return
            self.course_codes.setPlainText('\n'.join(codes))
            self.nav.setCurrentRow(5)

    def build_selection(self):
        layout = self.page('自动选课', '接入新版 xkgo 选课页面。启动后会打开独立 Edge，请手动登录 SEP 并进入选课主页。')
        layout.addWidget(label('目标课程编码（每行一门；请复制完整课程编码）'))
        self.course_codes = QPlainTextEdit()
        self.course_codes.setPlaceholderText('可从“选课规划”一键带入，或粘贴 SEP 中的完整课程编码。')
        layout.addWidget(self.course_codes, 1)
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

    def run_selection(self, preview):
        try:
            codes = self.course_codes.toPlainText().split()
            if not codes:
                raise ValueError('请先填写目标课程编码。')
            start_at = self.select_time.dateTime().toString('yyyy-MM-ddTHH:mm:ss') if self.select_timed.isChecked() else None
            payload = {'codes': codes, 'preview': preview, 'start_at': start_at,
                       'interval': self.select_interval.value(), 'rounds': self.select_rounds.value() if self.select_repeat.isChecked() and not preview else 1}
            self.start_job('selection', f'选课{"预览" if preview else "任务"} · {len(codes)} 门', PYTHON, [ROOT / 'adapters/selection_worker.py'], payload)
        except Exception as exc:
            self.error(str(exc))

    def build_jobs(self):
        layout = self.page('任务与日志', '“已结束”表示脚本正常退出，具体报名 / 签到 / 选课结果以日志和学校记录为准。')
        controls = row(button('刷新', self.refresh_jobs), button('停止选中任务', self.stop_selected), button('停止全部任务', self.jobs.stop_all), button('打开日志目录', lambda: self.open_path(LOGS)))
        layout.addLayout(controls)
        split = QSplitter(Qt.Vertical)
        self.job_table = table(['任务', '模块', '状态', '开始时间', '最后更新'])
        self.job_table.itemSelectionChanged.connect(self.show_selected_log)
        split.addWidget(self.job_table)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(3000)
        split.addWidget(self.log_view)
        split.setSizes([270, 400])
        layout.addWidget(split, 1)

    def refresh_jobs(self):
        items = self.store.list()
        selected = self.current_log
        self.job_table.blockSignals(True)
        self.job_table.setRowCount(len(items))
        for index, item in enumerate(items):
            values = [item['title'], item['module'], STATUS.get(item['status'], item['status']), item['created'], item['updated']]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.UserRole, item['id'])
                self.job_table.setItem(index, column, cell)
            if item['id'] == selected:
                self.job_table.selectRow(index)
        self.job_table.blockSignals(False)
        self.home_status.setText(f'5 个功能模块已接入   ·   {len(self.jobs.active)} 项任务运行中   ·   {len(items)} 条任务记录')

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
                if message.get('event') == 'lecture.science-schedule' and isinstance(message.get('rows'), list):
                    self.science_rows = message['rows']
                    self.science_choose.setEnabled(bool(self.science_rows))
                    self.science_status.setText(f'已查询 {len(self.science_rows)} 场；点击选择并填入时间')
            except (ValueError, AttributeError):
                pass
        if job_id == self.current_log:
            self.log_view.moveCursor(QTextCursor.MoveOperation.End)
            self.log_view.insertPlainText(text)

    def stop_selected(self):
        if self.current_log:
            self.jobs.stop(self.current_log)

    def build_settings(self):
        layout = self.page('设置与更新', '模块来源、固定版本和维护接口都保留在本地，便于后续升级。')
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
        if index == 4 and not self.planner:
            QTimer.singleShot(0, self.load_planner)

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
* { font-family: "Microsoft YaHei", "Segoe UI"; font-size: 13px; }
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
QPushButton { background: #fff; color: #285741; border: 1px solid #c4d8c8; border-radius: 7px; padding: 9px 13px; min-height: 19px; }
QPushButton:hover { background: #e6f0e7; border-color: #8cb599; }
QPushButton#primary { background: #286449; color: white; border-color: #286449; }
QPushButton#primary:hover { background: #347856; }
QLineEdit, QPlainTextEdit, QSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit, QComboBox { background: white; border: 1px solid #ccd9cf; border-radius: 6px; padding: 7px; selection-background-color: #36775a; }
QTableWidget { background: white; alternate-background-color: #f1f6f1; border: 1px solid #d7e2d7; border-radius: 6px; gridline-color: #e9eee9; }
QHeaderView::section { background: #eaf1eb; color: #315b46; border: none; border-bottom: 1px solid #cedecf; padding: 8px; }
QTableWidget::item:selected { background: #d1e7d5; color: #153d28; }
QStatusBar { background: #eaf0ea; color: #536b5c; }
'''
