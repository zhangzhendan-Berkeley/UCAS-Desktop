"""Dashboard integration, strictly separated from school write operations."""
from datetime import datetime
import sqlite3
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QGridLayout, QHBoxLayout,
    QTableWidgetItem, QDialog, QScrollArea, QWidget, QCheckBox, QComboBox, QColorDialog, QHeaderView)
from .core import DATA, ROOT, NODE, read_json, write_json, redact
from .activity import scope, MILESTONES, NOTICE_DEFAULTS
from .presentation import color_item, enable_copy
from .mail import send_mail, validate_address
from .overview_refresh import RefreshBatch, LECTURE_PARTS, read_iclass_overview
from .dashboard_widgets import StatusCard, StatTile
from .catalog import colors, PALETTE


class DashboardMixin:
    def build_home(self):
        from .ui import label, button, row, table
        outer = self.page('校园日常，一目了然', datetime.now().strftime('%Y 年 %m 月 %d 日') + '  ·  雁栖湖  /  我的校园工作台')
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(18)
        self.home_status = label('', 'muted')
        self.refresh_all_button = button('一键刷新全部信息', self.refresh_all, True)
        toolbar = QHBoxLayout()
        toolbar.addWidget(self.home_status, 1)
        toolbar.addWidget(button('自定义概览', self.customize_home))
        toolbar.addWidget(self.refresh_all_button)
        layout.addLayout(toolbar)
        self.refresh_summary = label('学校信息按需同步，后台任务状态每 5 秒更新。', 'muted')
        self.refresh_details_button = button('查看刷新明细', self.toggle_refresh_details)
        self.refresh_details_button.setCheckable(True)
        progress = QHBoxLayout()
        progress.addWidget(self.refresh_summary, 1)
        progress.addWidget(self.refresh_details_button)
        layout.addLayout(progress)
        self.refresh_all_status = label('一次查询今日课程、已选课程、人文 / 科研讲座及有效听讲次数。', 'muted')
        self.refresh_all_status.hide()
        layout.addWidget(self.refresh_all_status)
        self.home_stats = QWidget()
        stat_layout = QHBoxLayout(self.home_stats)
        stat_layout.setContentsMargins(0, 0, 0, 0)
        stat_layout.setSpacing(14)
        self.stat_tiles = {}
        for key, title, unit, accent in [('days', '自动签到天数', '天', '#376851'), ('signs', '成功签到', '次', '#476797'),
                ('bookings', '讲座预约成功', '场', '#916032'), ('selections', '成功选课', '门', '#756295')]:
            tile = self.stat_tiles[key] = StatTile(title, unit, accent)
            stat_layout.addWidget(tile, 1)
        layout.addWidget(self.home_stats)
        self.achievement_notice = label('每一次完成，都值得被记录。', 'muted')
        layout.addWidget(self.achievement_notice)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(18)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.home_grid = grid
        self.home_card_widgets = {}
        self.home_default_colors = {}
        self.home_cards = {}
        cards = [('课程与讲座签到', 1, '#d5e8dd', '#315e49'), ('人文讲座', 2, '#f0dfc7', '#85572e'),
                 ('国科大在线', 3, '#dae3f3', '#48618e'), ('选课规划', 4, '#e1d9ee', '#695383'),
                 ('自动选课', 5, '#cfe5e8', '#2e6871'), ('科研讲座', 9, '#dfe6c9', '#586734'), ('任务与日志', 6, '#edd8df', '#855363')]
        for index, (title, page, bg, fg) in enumerate(cards):
            action = '查看今日讲座' if page == 9 else '管理' + title
            callback = self.show_today_lectures if page == 9 else lambda checked=False, p=page: self.nav.setCurrentRow(p)
            card = StatusCard(title, fg, action, callback)
            self.home_cards[page] = card
            self.home_card_widgets[page] = card
            self.home_default_colors[page] = bg
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)
        layout.addLayout(row(button('查看今天全部讲座', self.show_today_lectures), button('查看成就', self.show_achievements),
            button('打开使用说明', lambda: self.open_path(ROOT / '使用指南.md'))))
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
        self.week_legend = label('')
        self.week_legend.setTextFormat(Qt.RichText)
        self.week_legend.setText('　'.join(f'<span style="color:{fg}">● {name}</span>' for name, (_, fg) in PALETTE.items()) + '　<span style="color:#a43f40">● 时间冲突</span>')
        layout.addWidget(self.week_legend)
        self.home_week = table(['周一', '周二', '周三', '周四', '周五', '周六', '周日'])
        self.home_week.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.home_week.verticalHeader().setStyleSheet('QHeaderView::section {padding:4px; font-size:12px;}')
        self.home_week.setMinimumHeight(440)
        self.home_week.setMaximumHeight(600)
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
        self.home_status.setText(f'{len(active)} 项任务运行中  ·  关闭窗口后继续托盘运行')
        signing = bool(modules & {'iclass', 'iclass-daily', 'iclass-manual', 'lecture-sign'})
        self.home_cards[1].set_content('签到任务执行中' if signing else '当前没有签到任务',
            ['每日计划   08:00 自动查课并安排签到', '计划状态   ' + ('已启用' if self.automation.enabled('course') else '未启用')],
            '每节课在开课前 20 分钟内随机执行，具体时间见日志。', '运行中' if signing else '空闲')
        config = self.automation.config.get('lecture', {})
        mode = '自动报名' if config.get('book') else '仅观察，不报名'
        for page, kind in ((2, 'humanity'), (9, 'science')):
            saved, lectures = self.lecture_today_rows(kind)
            headline = f'今日 {len(lectures)} 场讲座' if saved else '今日安排待同步'
            details = [f'{r.get("time", "时间待定")}\n{r["title"]} · {r.get("location") or "地点未提供"}' for r in lectures]
            if not details: details = ['当前列表未见今日安排' if saved else '点击顶部“一键刷新全部信息”获取日程']
            if page == 2:
                details += [('巡检已启用 · ' + mode if config.get('enabled') else '定点巡检未启用'),
                    f'仅雁栖湖 · 开始时段 {config.get("from", "00:00")}–{config.get("to", "23:59")}']
            note = '最近同步  ' + saved['at'].replace('T', ' ') if saved else '列表及有效听讲记录均来自学校查询。'
            self.home_cards[page].set_content(headline, details, note, '今日安排')
        self.home_cards[3].set_content('视频 / 文档处理中' if 'mooc' in modules else '等待启动学习任务',
            ['任务进度与剩余项目可在日志中查看'], '处理结束后，请在学校平台核对课程完成情况。', '运行中' if 'mooc' in modules else '空闲')
        state = read_json(self.activity.path.parent / 'planner/app_state.json', {})
        planned = len(self.planner.selected) if self.planner else len(state.get('selected_course_ids', []))
        snapshot = self.enrollment.current()
        self.home_cards[4].set_content(f'{planned} 门课程已加入规划',
            [f'备选收藏   {len(read_json(self.activity.path.parent / "planner/alternatives.json", []))} 门',
            f'学校已选   {len(snapshot.get("courses", []))} 门（{snapshot.get("source", "")}）' if snapshot else '学校已选   尚未同步'],
            '规划周课表见下方；实际选课状态以学校为准。', '课程清单')
        self.home_cards[5].set_content('自动选课任务已启动' if 'selection' in modules else '尚未启动选课任务',
            ['正在登录、等待设定时间或检查余量' if 'selection' in modules else '在规划清单勾选目标，再导入自动选课'],
            '选课结果与失败原因会记录在任务日志中。', '运行中' if 'selection' in modules else '空闲')
        self.home_cards[6].set_content(f'{len(active)} 项任务正在运行',
            ['运行中 · 蓝色    已完成 · 绿色', '执行失败 · 红色    已停止 · 灰紫色'], '打开日志可查看进度、复制结果和排查错误。', '执行记录')
        iclass, sep = scope(self.vault, 'iclass'), scope(self.vault, 'sep')
        counts = self.activity.counts(iclass, sep)
        for key, tile in self.stat_tiles.items(): tile.set_value(counts[key])
        records = self.activity.get_snapshot(sep, 'attendance')
        if records:
            r = records['payload']
            self.attendance_status.setText('学校有效听讲：' + ' / '.join(
                f'{title} {r[kind]["valid"]} 次（{r[kind].get("fetched_at", records["at"]).replace("T", " ")}）' if kind in r else title + ' 尚未同步'
                for kind, title in [('humanity', '人文'), ('science', '科研')]))
        else:
            self.attendance_status.setText('学校有效听讲：尚未同步（不等于零次）')
        today = self.activity.get_snapshot(iclass, 'today')
        rows = today.get('payload', {}).get('courses', []) if today.get('payload', {}).get('date') == datetime.now().strftime('%Y%m%d') else []
        self.today_status.setText('今日课程 · ' + (f'共 {len(rows)} 节 · 查询时间 {today["at"].replace("T", " ")}' if today and today['payload'].get('date') == datetime.now().strftime('%Y%m%d') else '尚未查询，点击上方刷新'))
        self.today_table.setRowCount(len(rows))
        categories = self.home_course_categories(state)
        for index, course in enumerate(rows):
            signed = str(course.get('signStatus')) == '1'
            category = categories.get(course.get('courseName', ''), '未分类')
            bg, fg = colors(category)
            for col, value in enumerate([course.get('courseName', ''), course.get('teacherName', ''), course.get('classBeginTime', ''), course.get('classEndTime', ''), '已签到' if signed else '未签到']):
                item = QTableWidgetItem(str(value))
                item.setBackground(QColor(bg))
                item.setForeground(QColor(fg))
                item.setToolTip('课程类别：' + category + '\n' + str(value))
                if col == 4: color_item(item, 'success' if signed else 'pending')
                self.today_table.setItem(index, col, item)
        self.refresh_home_week(state)
        results = [r for identity in self.notice_scopes() if (r := self.activity.mail_status(identity))]
        result = max(results, key=lambda row: row[1]) if results else None
        names = {'sent': '服务器已接受发送', 'failed': '发送失败', 'unknown': '发送结果未确认，请核对收件箱', 'pending': '等待发送', 'sending': '发送中', 'disabled': '成功时通知未开启'}
        self.mail_status_label.setText('重要消息邮件提醒：' + ('已开启' if self.mail_enabled() else '未开启') +
            (f' · 最近：{names.get(result[0], result[0])} {result[1]} {result[2]}' if result else ''))
        self.apply_home_preferences()
        self.pump_mail()

    def refresh_all(self):
        if getattr(self, '_overview_refresh', None) and not self._overview_refresh.finished:
            return
        batch = self._overview_refresh = RefreshBatch()
        self.refresh_all_button.setEnabled(False)
        self.refresh_dashboard()
        batch.result('local', True, '任务状态、规划、成果与邮件状态已读取')
        self.update_refresh_progress(batch)
        try:
            account = self.account('iclass')
            version = self.account_version('iclass')
            date = datetime.now().strftime('%Y%m%d')
            identity = scope(self.vault, 'iclass')
            def received(results, account=account):
                if self._overview_refresh is not batch: return
                for part in ('today', 'enrollment'):
                    result = results.get(part, {})
                    try:
                        if self.account_version('iclass') != version:
                            raise ValueError('查询期间账号已更改，请重新刷新')
                        if not result.get('ok'): raise ValueError(result.get('error', '查询未完成'))
                        value = result['value']
                        if part == 'today':
                            self.activity.snapshot(identity, 'today', {'date': date, 'courses': value})
                            if self.course_date.date().toString('yyyyMMdd') == date: self.populate_courses(value)
                            detail = f'{len(value)} 节课'
                        else:
                            self.enrollment.save(value, account['username'])
                            if not self.planner: self.load_planner()
                            if self.planner: self.planner.apply_enrollment()
                            detail = f'{len(value["courses"])} 门（轻新课堂）'
                            self.enrollment_status.setText('一键刷新：已更新学校已选课程 · ' + detail)
                        batch.result(part, True, detail)
                    except Exception as exc:
                        batch.result(part, False, redact(str(exc), self.vault.secret_values()) + '；保留上次结果')
                self.update_refresh_progress(batch)
            def failed(error):
                for part in ('today', 'enrollment'): batch.result(part, False, redact(error, self.vault.secret_values()))
                self.update_refresh_progress(batch)
            self.background(lambda account=account: read_iclass_overview(account, date), received, failed)
        except Exception as exc:
            for part in ('today', 'enrollment'): batch.result(part, False, str(exc))
        try:
            account = self.account('sep')
            batch.versions['sep'] = self.account_version('sep')
            import time
            deadline = time.monotonic() + 120
            if hasattr(self, '_refresh_wait'):
                self._refresh_wait.stop()
                self._refresh_wait.deleteLater()
            self._refresh_wait = QTimer(self)
            self._refresh_wait.setInterval(1000)
            def start_when_free():
                if self._quitting or self._overview_refresh is not batch:
                    self._refresh_wait.stop()
                    return
                busy = any(item['module'] in ('lecture', 'lecture-clock') for item in self.jobs.active.values())
                if busy and time.monotonic() < deadline:
                    for part in LECTURE_PARTS: batch.parts[part] = ('pending', '等待当前讲座任务结束，不打断它')
                    self.update_refresh_progress(batch)
                    return
                self._refresh_wait.stop()
                try:
                    if busy: raise ValueError('讲座模块持续忙碌，稍后再刷新')
                    if self.account_version('sep') != batch.versions['sep']: raise ValueError('SEP 账号已修改，请重新刷新')
                    batch.account = scope(self.vault, 'sep')
                    batch.lecture_job = self.start_job('lecture', '一键刷新 · 讲座及听讲记录（只读）', NODE,
                        [ROOT / 'adapters/lecture.mjs'], account | {'action': 'dashboard-refresh', 'preview': True}, open_logs=False)
                except Exception as exc:
                    for part in LECTURE_PARTS: batch.result(part, False, redact(str(exc), self.vault.secret_values()))
                self.update_refresh_progress(batch)
            self._refresh_wait.timeout.connect(start_when_free)
            self._refresh_wait.start()
            start_when_free()
        except Exception as exc:
            for part in LECTURE_PARTS: batch.result(part, False, str(exc))
        self.update_refresh_progress(batch)

    def update_refresh_progress(self, batch):
        if self._overview_refresh is not batch: return
        self.refresh_all_status.setText(redact(batch.summary(), self.vault.secret_values()))
        self.refresh_summary.setText(batch.summary().splitlines()[0])
        self.refresh_all_button.setEnabled(batch.finished)
        self.refresh_all_button.setText('一键刷新全部信息' if batch.finished else '刷新中…')
        self.refresh_dashboard()

    def toggle_refresh_details(self, checked):
        self.refresh_all_status.setVisible(checked)
        self.refresh_details_button.setText('收起刷新明细' if checked else '查看刷新明细')

    def refresh_receive_event(self, job_id, event):
        batch = getattr(self, '_overview_refresh', None)
        if not batch or job_id != batch.lecture_job or event.get('event') != 'dashboard.part': return
        part = event.get('part')
        if part not in LECTURE_PARTS or batch.parts[part][0] != 'pending': return
        try:
            if self.account_version('sep') != batch.versions['sep']: raise ValueError('账号已更改，结果未应用')
            if not event.get('ok'): raise ValueError(event.get('error', '查询未完成'))
            value = event['value']
            if part in ('humanity', 'science'):
                if not isinstance(value.get('rows'), list): raise ValueError('讲座列表格式不正确')
                self.activity.snapshot(batch.account, 'calendar-' + part, value)
                detail = f'当前列表 {len(value["rows"])} 场'
                if part == 'science':
                    self.science_rows = value['rows']
                    self.science_choose.setEnabled(bool(self.science_rows))
                    self.science_status.setText('一键刷新：' + detail + '；可选择场次')
            else:
                if not isinstance(value.get('valid'), int) or value['valid'] < 0: raise ValueError('有效听讲次数无法识别')
                records = self.activity.get_snapshot(batch.account, 'attendance').get('payload', {})
                records[part.split('-')[0]] = value | {'fetched_at': datetime.now().isoformat(timespec='seconds')}
                self.activity.snapshot(batch.account, 'attendance', records)
                detail = f'有效 {value["valid"]} 次'
            batch.result(part, True, detail)
        except Exception as exc:
            batch.result(part, False, redact(str(exc), self.vault.secret_values()) + '；保留上次结果')
        self.update_refresh_progress(batch)

    def refresh_job_finished(self, job_id, meta):
        batch = getattr(self, '_overview_refresh', None)
        if not batch or batch.lecture_job != job_id: return
        for part in LECTURE_PARTS:
            batch.result(part, False, '查询未返回结果或已停止，保留上次结果；详见任务日志')
        self.update_refresh_progress(batch)

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
            card.configure_color(color)
            card.configure_detail(config.get('detail', 'detailed'))
        for key, widgets in {'stats': [self.home_stats, self.achievement_notice], 'today': [self.today_status, self.today_table],
                'week': [self.week_status, self.week_legend, self.home_week], 'attendance': [self.attendance_status], 'mail': [self.mail_status_label]}.items():
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
            for title, value in [('简洁 · 主要状态', 'compact'), ('标准 · 两项详情', 'normal'), ('详细 · 全部状态', 'detailed')]: detail.addItem(title, value)
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

    def home_course_categories(self, state):
        """Only assign a today's-course category when the local name is unambiguous."""
        if self.planner:
            records = [(c.name, self.planner.catalog.info(c)['category']) for c in self.planner.catalog.courses]
        else:
            path = self.activity.path.parent / 'planner' / PathName(state.get('db_path', 'courses.db'))
            records = []
            if path.is_file():
                try:
                    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
                    try: records = db.execute('SELECT course_name, attribute FROM courses').fetchall()
                    finally: db.close()
                except sqlite3.Error: pass
        categories = {}
        for name, category in records: categories.setdefault(name, set()).add(category or '未分类')
        return {name: next(iter(values)) for name, values in categories.items() if len(values) == 1}

    def refresh_home_week(self, state):
        # Use the loaded planner when present; otherwise a read-only snapshot of its own DB.
        week = self.planner.week_view.current_week() if self.planner else state.get('ui', {}).get('week', 1)
        self.week_status.setText(f'规划周课表 · 第 {week} 教学周（可在“选课规划 → 周课表”调整；今日课程以上方学校查询为准）')
        rows = []
        if self.planner:
            for course in self.planner.db.get_courses_with_schedules(list(self.planner.selected)):
                category = self.planner.catalog.info(course)['category']
                rows.extend((course.id, course.name, s.day_of_week, s.time_slots, s.location, s.weeks, category) for s in course.schedules)
        else:
            ids = state.get('selected_course_ids', [])
            path = self.activity.path.parent / 'planner' / PathName(state.get('db_path', 'courses.db'))
            if path.is_file() and ids:
                try:
                    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
                    try:
                        fields = {r[1] for r in db.execute('PRAGMA table_info(courses)')}
                        category = 'c.attribute' if 'attribute' in fields else "'未分类'"
                        rows = db.execute('SELECT c.id,c.course_name,s.day_of_week,s.time_slots,s.location,s.weeks,' + category + ' FROM courses c JOIN course_schedules s ON c.id=s.course_id WHERE c.id IN (' + ','.join('?' for _ in ids) + ')', ids).fetchall()
                    finally: db.close()
                except sqlite3.Error:
                    self.week_status.setText('规划课表暂时不可读取；请打开选课规划检查数据。')
        import sys
        vendor = str(ROOT / 'vendor/UCAS-Course-Selector/src')
        if vendor not in sys.path: sys.path.insert(0, vendor)
        from coursesystem.conflict import is_in_week, parse_time_slots
        from coursesystem.config import TIME_SLOTS
        cells = {}
        for identifier, name, day, slots, location, weeks, category in rows:
            if not 1 <= int(day) <= 7 or not is_in_week(weeks, week): continue
            for slot in parse_time_slots(slots):
                if slot in TIME_SLOTS:
                    cells.setdefault((slot-1, int(day)-1), {})[identifier] = (name, location, category or '未分类')
        self.home_week.clearSpans()
        self.home_week.clearContents()
        self.home_week.setRowCount(len(TIME_SLOTS))
        self.home_week.verticalHeader().setVisible(True)
        self.home_week.setVerticalHeaderLabels([f'第 {slot} 节\n{time}' for slot, time in TIME_SLOTS.items()])
        for row in range(len(TIME_SLOTS)): self.home_week.setRowHeight(row, 42)
        for (row, col), entries in cells.items():
            conflict = len(entries) > 1
            text = '\n\n'.join(f'{name}\n{location}\n{category}' for name, location, category in entries.values())
            if conflict: text = '时间冲突\n' + text
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            item.setToolTip(text)
            bg, fg = ('#f8d7da', '#721c24') if conflict else colors(next(iter(entries.values()))[2])
            item.setBackground(QColor(bg))
            item.setForeground(QColor(fg))
            self.home_week.setItem(row, col, item)
        # Match the planner's continuous-period blocks; keep every cell's text for copy.
        for col in range(7):
            row = 0
            while row < len(TIME_SLOTS):
                end = row + 1
                entries = cells.get((row, col))
                if entries:
                    while end < len(TIME_SLOTS) and cells.get((end, col)) == entries: end += 1
                    if end - row > 1: self.home_week.setSpan(row, col, end - row, 1)
                row = end

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
            state = 'sent' if success else ('failed' if '登录失败' in message or '请填写' in message or message.startswith('未发送') else 'unknown')
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
