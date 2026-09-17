"""Dashboard integration, strictly separated from school write operations."""
from datetime import datetime
import sqlite3
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QGridLayout, QHBoxLayout,
    QTableWidgetItem, QDialog, QScrollArea, QWidget, QCheckBox, QComboBox, QColorDialog)
from .core import DATA, ROOT, NODE, read_json, write_json, redact
from .activity import scope, MILESTONES, NOTICE_DEFAULTS
from .presentation import color_item, enable_copy
from .mail import send_mail, validate_address


class DashboardMixin:
    def build_home(self):
        from .ui import label, button, row, table
        outer = self.page('校园日常，一目了然', '后台计划、正在执行的任务与学校确认结果分别展示。关闭窗口后可在托盘继续运行。')
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 12, 0)
        self.home_status = label('', 'banner')
        layout.addWidget(self.home_status)
        self.achievement_notice = label('每一次完成，都值得被记录。', 'muted')
        layout.addWidget(self.achievement_notice)
        self.home_stats = label('尚无已确认的自动操作记录。')
        layout.addWidget(self.home_stats)
        grid = QGridLayout()
        self.home_grid = grid
        self.home_card_widgets = {}
        self.home_default_colors = {}
        self.home_cards = {}
        cards = [('课程与讲座签到', 1, '#e9f3ee', '#376851'), ('人文讲座 · 预约与今日安排', 2, '#faf0e2', '#936337'),
                 ('国科大在线', 3, '#ebeff9', '#556b99'), ('选课规划', 4, '#eeeaf6', '#756295'),
                 ('自动选课', 5, '#e5f2f4', '#367780'), ('科研讲座 · 今日安排', 9, '#edf1e2', '#6b7a41'), ('任务与日志', 6, '#f7eaed', '#936171')]
        for index, (title, page, bg, fg) in enumerate(cards):
            card = QGroupBox(title)
            card.setStyleSheet(f'QGroupBox {{background:{bg}; border:1px solid {bg}; border-top:3px solid {fg}; border-radius:10px; margin-top:12px; padding:14px 10px 8px;}} QGroupBox::title {{color:{fg}; subcontrol-origin:margin; left:12px;}} QLabel {{background:transparent;}}')
            content = QVBoxLayout(card)
            status = label('读取状态中…')
            content.addWidget(status)
            content.addWidget(button('查看详情 →', lambda checked=False, p=page: self.nav.setCurrentRow(1 if p == 9 else p)))
            self.home_cards[page] = status
            self.home_card_widgets[page] = card
            self.home_default_colors[page] = bg
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        layout.addLayout(row(button('自定义概览', self.customize_home), button('刷新今天的课程', self.refresh_today), button('同步学校听讲次数', self.sync_attendance),
            button('查看成就', self.show_achievements), button('打开使用说明', lambda: self.open_path(ROOT / '使用指南.md'))))
        layout.addLayout(row(button('刷新人文 / 科研讲座安排', self.sync_calendars), button('查看今天全部讲座', self.show_today_lectures)))
        self.attendance_status = label('学校有效听讲：尚未同步（不等于零次）', 'muted')
        layout.addWidget(self.attendance_status)
        self.today_status = label('今日课程 · 尚未查询轻新课堂', 'muted')
        layout.addWidget(self.today_status)
        self.today_table = table(['课程 / 讲座', '教师', '开始', '结束', '签到状态'])
        self.today_table.setMinimumHeight(150)
        self.today_table.setMaximumHeight(245)
        layout.addWidget(self.today_table)
        self.week_status = label('规划周课表 · 使用选课规划中选定的教学周，非自动推断当前教学周', 'muted')
        layout.addWidget(self.week_status)
        self.home_week = table(['周一', '周二', '周三', '周四', '周五', '周六', '周日'])
        self.home_week.setMinimumHeight(165)
        self.home_week.setMaximumHeight(240)
        layout.addWidget(self.home_week)
        self.mail_status_label = label('重要消息邮件提醒：未启用', 'muted')
        layout.addWidget(self.mail_status_label)
        layout.addWidget(label('累计成果从新版启用后记录；按账号去重。自动签到天数按实际成功日期计算，并非连续签到天数。学校听讲有效次数单独同步，预约或扫码成功不等于有效听讲。', 'muted'))
        scroll.setWidget(widget)
        outer.addWidget(scroll, 1)

    def refresh_dashboard(self):
        if not hasattr(self, 'home_cards'):
            return
        active = [x for x in self.jobs.active.values() if not x.get('stopping')]
        modules = {x['module'] for x in active}
        self.home_status.setText(f'{len(self.home_cards)} 个状态模块   ·   {len(active)} 项任务运行中   ·   状态每 5 秒刷新')
        self.home_cards[1].setText(('每日 08:00 计划：已启用' if self.automation.enabled('course') else '每日 08:00 计划：未启用') +
            ('\n签到任务正在运行 / 等待课程开始' if modules & {'iclass', 'iclass-daily', 'iclass-manual', 'lecture-sign'} else '\n目前没有执行中的签到任务'))
        config = self.automation.config.get('lecture', {})
        mode = '自动报名' if config.get('book') else '仅观察，不报名'
        self.home_cards[2].setText(('定点巡检已启用 · ' + mode if config.get('enabled') else '定点巡检未启用') +
            f'\n仅雁栖湖 · 开始时段 {config.get("from", "00:00")}–{config.get("to", "23:59")}' +
            ('\n本轮正在执行' if modules & {'lecture', 'lecture-clock'} else '\n' + self.automation.description('lecture')))
        self.home_cards[2].setText(self.lecture_today_text('humanity') + '\n' + self.home_cards[2].text())
        self.home_cards[9].setText(self.lecture_today_text('science'))
        self.home_cards[3].setText('视频 / 文档任务正在运行\n进度与实际结果见任务日志' if 'mooc' in modules else '慕课任务未运行\n可在国科大在线模块启动')
        state = read_json(self.activity.path.parent / 'planner/app_state.json', {})
        planned = len(self.planner.selected) if self.planner else len(state.get('selected_course_ids', []))
        snapshot = self.enrollment.current()
        self.home_cards[4].setText(f'规划清单 {planned} 门 · 备选 {len(read_json(self.activity.path.parent / "planner/alternatives.json", []))} 门\n' +
            (f'学校已选快照 {len(snapshot.get("courses", []))} 门（{snapshot.get("source", "")}）' if snapshot else '尚无当前账号的已选同步记录'))
        self.home_cards[5].setText('自动选课任务已启动\n正在登录、等待设定时间或检查余量' if 'selection' in modules else '自动选课任务未开启\n从规划清单勾选目标课程后启动')
        self.home_cards[6].setText(f'{len(active)} 项任务运行中\n蓝：运行 · 绿：完成 · 红：失败 · 灰紫：停止')
        iclass, sep = scope(self.vault, 'iclass'), scope(self.vault, 'sep')
        counts = self.activity.counts(iclass, sep)
        self.home_stats.setText(f'自动签到 {counts["days"]} 天   ·   成功签到 {counts["signs"]} 次   ·   讲座预约 {counts["bookings"]} 场   ·   成功选课 {counts["selections"]} 门')
        records = self.activity.get_snapshot(sep, 'attendance')
        if records:
            r = records['payload']
            self.attendance_status.setText(f'学校有效听讲：人文 {r["humanity"]["valid"]} 次 / 科研 {r["science"]["valid"]} 次   ·   查询时间 {records["at"].replace("T", " ")}')
        else:
            self.attendance_status.setText('学校有效听讲：尚未同步（不等于零次）')
        today = self.activity.get_snapshot(iclass, 'today')
        rows = today.get('payload', {}).get('courses', []) if today.get('payload', {}).get('date') == datetime.now().strftime('%Y%m%d') else []
        self.today_status.setText('今日课程 · ' + (f'共 {len(rows)} 节 · 查询时间 {today["at"].replace("T", " ")}' if today and today['payload'].get('date') == datetime.now().strftime('%Y%m%d') else '尚未查询，点击上方刷新'))
        self.today_table.setRowCount(len(rows))
        for index, course in enumerate(rows):
            signed = str(course.get('signStatus')) == '1'
            for col, value in enumerate([course.get('courseName', ''), course.get('teacherName', ''), course.get('classBeginTime', ''), course.get('classEndTime', ''), '已签到' if signed else '未签到']):
                item = QTableWidgetItem(str(value))
                if col in (0, 4): color_item(item, 'success' if signed else 'pending')
                self.today_table.setItem(index, col, item)
        self.refresh_home_week(state)
        results = [r for identity in self.notice_scopes() if (r := self.activity.mail_status(identity))]
        result = max(results, key=lambda row: row[1]) if results else None
        names = {'sent': '服务器已接受发送', 'failed': '发送失败', 'unknown': '发送结果未确认，请核对收件箱', 'pending': '等待发送', 'sending': '发送中', 'disabled': '成功时通知未开启'}
        self.mail_status_label.setText('重要消息邮件提醒：' + ('已开启' if self.mail_enabled() else '未开启') +
            (f' · 最近：{names.get(result[0], result[0])} {result[1]} {result[2]}' if result else ''))
        self.apply_home_preferences()
        self.pump_mail()

    def apply_home_preferences(self):
        preferences = self.settings.get('dashboard', {})
        position = 0
        for page, card in self.home_card_widgets.items():
            config = preferences.get(str(page), {})
            self.home_grid.removeWidget(card)
            visible = config.get('visible', True)
            card.setVisible(visible)
            if visible:
                self.home_grid.addWidget(card, position // 2, position % 2)
                position += 1
            color = QColor(config.get('color', self.home_default_colors[page]))
            if not color.isValid(): color = QColor(self.home_default_colors[page])
            # WCAG luminance to retain readable text even with a dark user color.
            values = [((c / 255 + .055) / 1.055) ** 2.4 if c / 255 > .04045 else c / 255 / 12.92 for c in (color.red(), color.green(), color.blue())]
            luminance = sum(a*b for a,b in zip(values, (.2126,.7152,.0722)))
            fg = '#172c29' if luminance > .3 else '#ffffff'
            card.setStyleSheet(f'QGroupBox {{background:{color.name()}; border:1px solid {color.darker(108).name()}; border-radius:10px; margin-top:12px; padding:14px 10px 8px;}} QGroupBox::title {{color:{fg}; subcontrol-origin:padding; left:12px;}} QLabel {{background:transparent; color:{fg};}}')
            status = self.home_cards[page]
            full = status.text()
            status.setToolTip(full)
            lines = {'compact': 1, 'normal': 3, 'detailed': 100}.get(config.get('detail', 'detailed'), 100)
            status.setText('\n'.join(full.splitlines()[:lines]))
        for key, widgets in {'stats': [self.home_stats, self.achievement_notice], 'today': [self.today_status, self.today_table],
                'week': [self.week_status, self.home_week], 'attendance': [self.attendance_status], 'mail': [self.mail_status_label]}.items():
            for widget in widgets: widget.setVisible(preferences.get('sections', {}).get(key, True))

    def customize_home(self):
        from .ui import label, button, row
        dialog = QDialog(self)
        dialog.setWindowTitle('自定义概览')
        layout = QVBoxLayout(dialog)
        layout.addWidget(label('选择模块、信息量和背景色。模块隐藏后任务照常运行，左侧菜单始终可用。'))
        controls = {}
        prefs = self.settings.get('dashboard', {})
        for page, card in self.home_card_widgets.items():
            config = prefs.get(str(page), {})
            visible = QCheckBox(card.title())
            visible.setChecked(config.get('visible', True))
            detail = QComboBox()
            for title, value in [('简洁 · 1 行', 'compact'), ('标准 · 3 行', 'normal'), ('详细 · 全部状态', 'detailed')]: detail.addItem(title, value)
            detail.setCurrentIndex(max(0, detail.findData(config.get('detail', 'detailed'))))
            color = button('选择颜色', lambda: None)
            color.setProperty('chosenColor', config.get('color', self.home_default_colors[page]))
            color.setText(color.property('chosenColor'))
            def choose(checked=False, target=color):
                selected = QColorDialog.getColor(QColor(target.property('chosenColor')), dialog, '卡片背景颜色')
                if selected.isValid():
                    target.setProperty('chosenColor', selected.name())
                    target.setText(selected.name())
            color.clicked.connect(choose)
            controls[str(page)] = visible, detail, color
            layout.addLayout(row(visible, detail, color))
        sections = {}
        section_row = QHBoxLayout()
        for key, title in [('stats', '累计成果'), ('today', '今日课程'), ('week', '规划课表'), ('attendance', '学校听讲次数'), ('mail', '邮件状态')]:
            check = QCheckBox(title)
            check.setChecked(prefs.get('sections', {}).get(key, True))
            sections[key] = check
            section_row.addWidget(check)
        layout.addLayout(section_row)
        def save(default=False):
            self.settings['dashboard'] = {} if default else {key: {'visible': visible.isChecked(), 'detail': detail.currentData(), 'color': color.property('chosenColor')} for key, (visible, detail, color) in controls.items()}
            if not default: self.settings['dashboard']['sections'] = {key: check.isChecked() for key, check in sections.items()}
            write_json(self.activity.path.parent / 'settings.json', self.settings)
            self.refresh_dashboard()
            dialog.accept()
        layout.addLayout(row(button('恢复默认布局', lambda: save(True)), button('取消', dialog.reject), button('保存布局', lambda: save(), True)))
        dialog.exec()

    def refresh_home_week(self, state):
        # Use the loaded planner when present; otherwise a read-only snapshot of its own DB.
        week = self.planner.week_view.current_week() if self.planner else state.get('ui', {}).get('week', 1)
        self.week_status.setText(f'规划周课表 · 第 {week} 教学周（可在“选课规划 → 周课表”调整；今日课程以上方学校查询为准）')
        rows = []
        if self.planner:
            for course in self.planner.db.get_courses_with_schedules(list(self.planner.selected)):
                rows.extend((course.name, s.day_of_week, s.time_slots, s.location, s.weeks) for s in course.schedules)
        else:
            ids = state.get('selected_course_ids', [])
            path = self.activity.path.parent / 'planner' / PathName(state.get('db_path', 'courses.db'))
            if path.is_file() and ids:
                try:
                    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
                    try:
                        rows = db.execute('SELECT c.course_name,s.day_of_week,s.time_slots,s.location,s.weeks FROM courses c JOIN course_schedules s ON c.id=s.course_id WHERE c.id IN (' + ','.join('?' for _ in ids) + ')', ids).fetchall()
                    finally: db.close()
                except sqlite3.Error:
                    self.week_status.setText('规划课表暂时不可读取；请打开选课规划检查数据。')
        import sys
        vendor = str(ROOT / 'vendor/UCAS-Course-Selector/src')
        if vendor not in sys.path: sys.path.insert(0, vendor)
        from coursesystem.conflict import is_in_week
        days = [[] for _ in range(7)]
        for name, day, slots, location, weeks in rows:
            if 1 <= int(day) <= 7 and is_in_week(weeks, week):
                days[int(day)-1].append(f'{name}\n第 {slots} 节 · {location}')
        self.home_week.setRowCount(1)
        for col, values in enumerate(days):
            item = QTableWidgetItem('\n\n'.join(values) or '无规划课程')
            item.setToolTip(item.text())
            self.home_week.setItem(0, col, item)
        self.home_week.resizeRowsToContents()

    def refresh_today(self):
        from .iclass import IClass
        try:
            account = self.account('iclass')
            identity = scope(self.vault, 'iclass')
            date = datetime.now().strftime('%Y%m%d')
            def done(courses):
                self.activity.snapshot(identity, 'today', {'date': date, 'courses': courses})
                self.refresh_dashboard()
            self.background(lambda: IClass(**account).query(date), done)
        except Exception as exc: self.error(str(exc))

    def sync_attendance(self):
        try:
            self.start_job('lecture', '学校有效听讲次数 · 只读同步', NODE,
                [ROOT / 'adapters/lecture.mjs'], self.account('sep') | {'action': 'attendance', 'preview': True})
        except Exception as exc: self.error(str(exc))

    def sync_calendars(self):
        try:
            self.start_job('lecture', '人文 / 科研讲座安排 · 只读查询', NODE,
                [ROOT / 'adapters/lecture.mjs'], self.account('sep') | {'action': 'calendars', 'preview': True})
        except Exception as exc: self.error(str(exc))

    def lecture_today_rows(self, kind):
        import re
        saved = self.activity.get_snapshot(scope(self.vault, 'sep'), 'calendar-' + kind)
        today = datetime.now().date()
        rows = []
        for item in saved.get('payload', {}).get('rows', []):
            match = re.search(r'(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2})', item.get('time') or '')
            if match and tuple(map(int, match.groups())) == (today.year, today.month, today.day): rows.append(item)
        return saved, sorted(rows, key=lambda r: r.get('time') or '')

    def lecture_today_text(self, kind):
        saved, rows = self.lecture_today_rows(kind)
        if not saved: return '今日安排：尚未查询\n点击“刷新人文 / 科研讲座安排”'
        stamp = saved['at'].replace('T', ' ')
        title = f'今日列表 {len(rows)} 场 · 更新 {stamp}'
        if not rows: return title + '\n当前查询列表未见今日安排（可刷新核对）'
        return title + '\n' + '\n'.join(f'{r.get("time", "时间未知")} · {r["title"]}\n{r.get("location") or "地点未提供"}' for r in rows)

    def show_today_lectures(self):
        from .ui import label, table
        dialog = QDialog(self)
        dialog.setWindowTitle('今日人文 / 科研讲座安排')
        dialog.resize(1050, 530)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label('保留所有校区并显示地点，方便核对；自动预约仍仅允许雁栖湖。列表来自最近一次查询，学校变更请刷新。'))
        view = table(['类型', '讲座', '时间', '地点', '最近查询'])
        all_rows = []
        for kind, title in [('humanity', '人文'), ('science', '科研')]:
            saved, rows = self.lecture_today_rows(kind)
            all_rows.extend([title, row['title'], row.get('time', ''), row.get('location') or '未提供', saved['at']] for row in rows)
        view.setRowCount(len(all_rows))
        for index, values in enumerate(all_rows):
            for col, value in enumerate(values): view.setItem(index, col, QTableWidgetItem(value))
        layout.addWidget(view)
        enable_copy(dialog)
        dialog.exec()

    def activity_event(self, job_id, event):
        job = self.jobs.active.get(job_id, {})
        account = job.get('account')
        if not account: return
        name = event.get('event')
        if name == 'lecture.calendar' and event.get('kind') in ('humanity', 'science') and isinstance(event.get('rows'), list) and job.get('module') in ('lecture', 'lecture-clock'):
            self.activity.snapshot(account, 'calendar-' + event['kind'], {'rows': event['rows'], 'scope': event.get('scope', 'current-page')})
        if name == 'lecture.science-schedule' and isinstance(event.get('rows'), list):
            self.activity.snapshot(account, 'calendar-science', {'rows': event['rows'], 'scope': 'current-page'})
        if name == 'lecture.attendance' and job.get('module') == 'lecture':
            records = event.get('records', {})
            if all(isinstance(records.get(k, {}).get('valid'), int) and records[k]['valid'] >= 0 for k in ('humanity', 'science')):
                self.activity.snapshot(account, 'attendance', records)
        if name == 'iclass.today' and job.get('module') == 'iclass-daily':
            self.activity.snapshot(account, 'today', {'date': event['date'], 'courses': event['courses']})
        if job.get('preview'):
            self.refresh_dashboard()
            return
        added = False
        if name == 'iclass.sign-success' and job.get('module') in ('iclass', 'iclass-daily', 'iclass-manual', 'lecture-sign'):
            added = self.activity.record(account, 'sign', event.get('id'), event.get('title', ''), event.get('automatic') is True,
                notify=self.notice_enabled('sign'))
            saved = self.activity.get_snapshot(account, 'today')
            if saved:
                for course in saved['payload'].get('courses', []):
                    if str(course.get('id')) == str(event.get('id')): course['signStatus'] = '1'
                self.activity.snapshot(account, 'today', saved['payload'])
            if account == scope(self.vault, 'iclass'):
                for index, course in enumerate(self.courses):
                    if str(course.get('id')) == str(event.get('id')):
                        course['signStatus'] = '1'
                        self.course_table.item(index, 5).setText('已签到')
                        for col in range(1, self.course_table.columnCount()): color_item(self.course_table.item(index, col), 'success')
        elif name == 'run.register.result' and event.get('outcome') == 'registered' and job.get('module') in ('lecture', 'lecture-clock'):
            identifier = event.get('lectureId')
            observation = read_json(self.activity.path.parent / 'lecture' / account[:16] / 'observations.json', {})
            matches = [row for row in observation.get('lectures', {}).values() if row.get('title') == event.get('title') and row.get('yanqi')]
            detail = {'detail': event.get('detail', '')}
            if len(matches) == 1:
                detail.update(time=matches[0].get('lectureTime'), location=matches[0].get('location'))
            added = self.activity.record(account, 'booking', identifier, event.get('title', ''), detail=detail,
                notify=self.notice_enabled('booking'))
        elif name == 'selection.success' and job.get('module') == 'selection':
            identifier = str(event.get('id', '')) + '|' + event.get('semester', '')
            added = self.activity.record(account, 'selection', identifier, event.get('title', ''), notify=self.notice_enabled('selection'))
        if added:
            new = self.activity.unlock(scope(self.vault, 'iclass'), scope(self.vault, 'sep'))
            if new: self.celebrate(new)
        self.refresh_dashboard()

    def celebrate(self, titles):
        text = '成就达成 · ' + ' / '.join(titles)
        self.achievement_notice.setText(text)
        if not self.settings.get('achievement_popups', True): return
        if self.tray and not self.isVisible():
            self.tray.showMessage('又完成了一个小目标', text, self.tray.MessageIcon.Information, 5000)
        elif self.isVisible():
            from .ui import label
            popup = QDialog(self)
            popup.setWindowTitle('成就达成')
            popup.setAttribute(Qt.WA_DeleteOnClose)
            box = QVBoxLayout(popup)
            box.addWidget(label(text))
            box.addWidget(label('学校已确认成功，继续按自己的节奏积累。'))
            popup.setMinimumWidth(370)
            popup.show()  # Nonmodal: never blocks an automation task.
            QTimer.singleShot(6000, popup.close)

    def show_achievements(self):
        from .ui import label, table
        dialog = QDialog(self)
        dialog.setWindowTitle('我的成就')
        dialog.resize(630, 500)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label('按当前账号记录，只累计本应用明确确认成功的操作。'))
        view = table(['成就', '进度', '状态'])
        counts = self.activity.counts(scope(self.vault, 'iclass'), scope(self.vault, 'sep'))
        view.setRowCount(len(MILESTONES))
        for index, (metric, threshold, title) in enumerate(MILESTONES):
            achieved = counts[metric] >= threshold
            for col, value in enumerate([title, f'{counts[metric]} / {threshold}', '已达成' if achieved else '继续积累']):
                item = QTableWidgetItem(value)
                color_item(item, 'success' if achieved else 'neutral')
                view.setItem(index, col, item)
        layout.addWidget(view)
        enable_copy(dialog)
        dialog.exec()

    def save_notification_settings(self):
        self.settings['mail_enabled'] = self.email_enabled.isChecked()
        self.settings['mail_events'] = {kind: check.isChecked() for kind, check in self.notice_checks.items()}
        self.settings['mail_recipient'] = self.mail_recipient.text().strip()
        self.settings['achievement_popups'] = self.achievements_enabled.isChecked()
        write_json(self.activity.path.parent / 'settings.json', self.settings)
        self.refresh_dashboard()

    def test_email(self, send=False):
        try:
            account = self.account('email')
            recipient = validate_address(self.mail_recipient.text()) if send else None
            version = self.account_version('email')
            self.profile_status['email'].setText('正在连接邮件服务器…')
            self.background(lambda: send_mail(account, test=send, recipient=recipient),
                lambda message: self.checked_account('email', version, True, message),
                lambda error: self.checked_account('email', version, False, error))
        except Exception as exc: self.error(str(exc))

    def retry_notification(self):
        with self.activity.connect() as db:
            identities = self.notice_scopes()
            row = db.execute("SELECT account,identifier FROM mail WHERE account IN (" + ','.join('?' for _ in identities) + ") AND state IN ('unknown','failed') ORDER BY at DESC LIMIT 1", identities).fetchone()
        if row:
            self.activity.mail_result(row[0], row[1], 'pending', '用户核对后重发')
            self.pump_mail()
        else: self.statusBar().showMessage('没有需要重发的失败或未确认通知。')

    def pump_mail(self):
        if getattr(self, '_mail_busy', False) or not self.mail_enabled() or self._quitting:
            return
        account = self.vault.get('email').copy()
        if not account.get('username') or not account.get('password'): return
        recipient = self.settings.get('mail_recipient', '').strip()
        if not recipient: return
        booking = None
        for identity in self.notice_scopes():
            booking = self.activity.next_mail(identity)
            if booking: break
        if not booking: return
        if not self.notice_enabled(booking.get('kind', 'booking')):
            self.activity.mail_result(identity, booking['identifier'], 'disabled', '已按用户当前设置忽略此类提醒')
            return
        self._mail_busy = True
        def done(message, success):
            state = 'sent' if success else ('failed' if '登录失败' in message or '请填写' in message else 'unknown')
            self.activity.mail_result(identity, booking['identifier'], state, redact(message, self.vault.secret_values()))
            self._mail_busy = False
            self.refresh_dashboard()
        self.background(lambda: send_mail(account, booking, recipient=recipient), lambda message: done(message, True), lambda error: done(error, False))

    def mail_enabled(self):
        return self.settings.get('mail_enabled', self.settings.get('booking_email', False))

    def notice_enabled(self, kind):
        return self.mail_enabled() and self.settings.get('mail_events', {}).get(kind, NOTICE_DEFAULTS.get(kind, False))

    def notice_scopes(self):
        return list(dict.fromkeys([scope(self.vault, 'sep'), scope(self.vault, 'iclass'), 'local']))

    def task_notification(self, job_id, meta):
        # Manual stops, previews and successful polling do not produce completion spam.
        if meta.get('preview') or meta.get('status') in ('stopped', 'interrupted'):
            return
        module = meta.get('module', '')
        kind = 'mooc_completed' if module == 'mooc' and meta.get('status') == 'completed' else 'task_failed' if meta.get('status') in ('failed', 'attention') else None
        if not kind or module.startswith('account-') or module == 'module-install': return
        identity = meta.get('account') or 'local'
        identifier = ('failure:' + module + ':' + datetime.now().date().isoformat()) if module in ('lecture-clock', 'iclass-daily') else 'job:' + job_id
        self.activity.queue_mail(identity, identifier, self.notice_enabled(kind), {
            'kind': kind, 'title': meta.get('title') or module,
            'at': datetime.now().isoformat(timespec='seconds'),
            'detail': {'message': f'任务编号：{job_id}；退出码：{meta.get("code")}。完整原因请查看本机日志。'}})
        self.refresh_dashboard()


def PathName(value):
    from pathlib import Path
    return Path(value).name
