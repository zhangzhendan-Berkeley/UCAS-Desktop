"""Today's lecture cards and non-modal desktop reminders."""
import json
from .lecture_visibility import visible_lecture
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QFrame, QCheckBox, QSpinBox, QProgressBar, QDialog, QComboBox)
from .activity import scope
from .lecture_reminders import LectureReminders, now_beijing, start_time, lecture_key

KINDS = {'humanity': ('人文讲座', '#85572e', '#f0dfc7'),
         'science': ('科研讲座', '#41638a', '#d9e5f4')}


class LecturesMixin:
    def build_today_lectures(self, parent_layout=None):
        from .ui import label, button, row
        self.reminders = LectureReminders(self.activity.path.parent)
        self._lecture_signature = None
        self._lecture_account = None
        self._lecture_popups = []
        self._lecture_refresh_job = None
        self.jobs.ended.connect(self.lecture_information_finished)
        layout = parent_layout or self.page('今日讲座', '人文与科研 · 今日安排、听讲进度与到场提醒（北京时间）')
        layout.addLayout(row(button('刷新讲座与听讲记录', self.refresh_lecture_information, True),
                             button('立即同步明日到 macOS 日历', self.sync_calendar_now),
                             button('导出到日历（ICS）', self.export_calendar),
                             button('测试弹窗', self.test_lecture_popup)))
        self.lecture_progress = {}
        progress = QHBoxLayout()
        for kind, (name, accent, bg) in KINDS.items():
            card = QFrame(); card.setObjectName('lectureProgress')
            card.setStyleSheet(f'QFrame#lectureProgress {{background:{bg};border-radius:14px;}} QLabel {{background:transparent;color:{accent};}}')
            box = QVBoxLayout(card); box.setContentsMargins(20,16,20,16); box.setSpacing(8)
            heading = label(name); heading.setStyleSheet(f'font-size:18px;font-weight:700;color:{accent}')
            count, hours, note = label(''), label(''), label('', 'muted')
            bar = QProgressBar(); bar.setRange(0,200); bar.setTextVisible(False); bar.setFixedHeight(8)
            bar.setStyleSheet(f'QProgressBar {{border:0;background:white;border-radius:4px;}} QProgressBar::chunk {{background:{accent};border-radius:4px;}}')
            for w in (heading,count,hours,bar,note): box.addWidget(w)
            self.lecture_progress[kind] = (count,hours,bar,note)
            progress.addWidget(card,1)
        layout.addLayout(progress)
        self.lecture_remind_enabled = QCheckBox('开启讲座弹窗提醒')
        self.lecture_remind_minutes = QSpinBox(); self.lecture_remind_minutes.setRange(0,1440); self.lecture_remind_minutes.setSuffix(' 分钟')
        layout.addLayout(row(self.lecture_remind_enabled, label('默认提前'), self.lecture_remind_minutes))
        self.lecture_remind_enabled.toggled.connect(self.save_lecture_reminder_defaults)
        self.lecture_remind_minutes.valueChanged.connect(self.save_lecture_reminder_defaults)
        layout.addWidget(label('设置自动保存；每场可单独调整。关闭窗口进入托盘后仍可提醒，退出程序或电脑休眠时无法弹窗。提醒来自已同步列表，不代表已报名。', 'muted'))
        self.lecture_list_summary = label('', 'muted'); layout.addWidget(self.lecture_list_summary)
        self.lecture_scroll = QScrollArea(); self.lecture_scroll.setWidgetResizable(True); self.lecture_scroll.setFrameShape(QScrollArea.NoFrame)
        layout.addWidget(self.lecture_scroll,1)
        self.lecture_refresh_hint = label('', 'muted'); layout.addWidget(self.lecture_refresh_hint)
        self.lecture_timer = QTimer(self); self.lecture_timer.setInterval(5000)
        self.lecture_timer.timeout.connect(self.lecture_tick); self.lecture_timer.start()
        self.refresh_today_lectures()

    def export_calendar(self):
        try:
            from .calendar_export import export_ics
            from .activity import scope
            path, count = export_ics(self.activity, scope(self.vault, 'iclass'), scope(self.vault, 'sep'))
            self.statusBar().showMessage(f'已导出 {count} 个日历事件：{path}')
            self.open_path(path)
        except Exception as exc:
            self.error(str(exc))

    def sync_calendar_now(self):
        try:
            from .macos_calendar import sync_tomorrow
            from .activity import scope
            if getattr(self, '_calendar_tomorrow_running', False):
                return
            course_scope, sep_scope = scope(self.vault, 'iclass'), scope(self.vault, 'sep')
            self._calendar_tomorrow_running = True
            def finish(result=None, error=None):
                self._calendar_tomorrow_running = False
                if error: self.error(error)
                else: self.statusBar().showMessage(result[1])
            self.background(lambda: sync_tomorrow(self.activity, course_scope, sep_scope),
                            lambda result: finish(result=result), lambda error: finish(error=error))
        except Exception as exc:
            self.error(str(exc))

    def refresh_lecture_information(self):
        from .core import NODE, ROOT
        try:
            if any(j.get('module') in ('lecture','lecture-clock') for j in self.jobs.active.values()):
                self.error('讲座查询或预约任务仍在运行，请完成后再刷新。'); return
            self._lecture_refresh_job = self.start_job('lecture', '今日讲座与听讲进度 · 只读查询', NODE,
                           [ROOT/'adapters/lecture.mjs'], self.account('sep') | {'action':'dashboard-refresh','preview':True}, open_logs=False)
            self.lecture_refresh_hint.setText('正在同步讲座和听讲记录；如出现验证码，请在浏览器完成。查询过程见任务与日志。')
        except Exception as exc: self.error(str(exc))

    def lecture_information_finished(self, job_id, result):
        if job_id != self._lecture_refresh_job: return
        self._lecture_refresh_job = None
        self.refresh_today_lectures()
        if result.get('status') != 'completed':
            self.lecture_refresh_hint.setText('部分信息未更新，已保留旧数据；请到任务与日志查看原因，再重试刷新。')

    def save_lecture_reminder_defaults(self, *_):
        if self._lecture_account is None: return
        try:
            self.reminders.save(self._lecture_account, enabled=self.lecture_remind_enabled.isChecked(), minutes=self.lecture_remind_minutes.value())
            self._lecture_signature = None
            self.refresh_today_lectures()
        except Exception as exc:
            self.error(str(exc))
            self._lecture_account = None
            self.refresh_today_lectures()

    def refresh_today_lectures(self):
        if not hasattr(self, 'reminders'): return
        from .ui import label
        now = now_beijing(); account = scope(self.vault,'sep')
        if self._lecture_account != account:
            self._lecture_account = account
            config = self.reminders.config(account)
            for widget,value in ((self.lecture_remind_enabled,config['enabled']),(self.lecture_remind_minutes,config['minutes'])):
                widget.blockSignals(True)
                if isinstance(widget,QCheckBox): widget.setChecked(value)
                else: widget.setValue(value)
                widget.blockSignals(False)
        attendance = self.activity.get_snapshot(account,'attendance')
        records = attendance.get('payload',{})
        for kind,(count,hours,bar,note) in self.lecture_progress.items():
            record = records.get(kind,{})
            count.setText(f'有效听讲  {record["valid"]} 次   /   累计记录 {record["total"]} 次' if 'valid' in record else '有效次数尚未同步')
            value = record.get('hours')
            known = isinstance(value,(int,float)) and not isinstance(value,bool) and value >= 0
            hours.setText(f'{value:g} / 20 学时 · ' + (f'还差 {max(0,20-value):g} 学时' if value<20 else '已达到 20 学时目标') if known else '有效学时未获取 · 暂不能计算剩余学时')
            bar.setValue(min(200,round(value*10)) if known else 0)
            note.setText(('学校说明：有效听讲 10 次满足要求。' if kind=='humanity' else '进度按你设定的 20 学时目标展示。') + '\n' + ('记录同步于 '+attendance['at'].replace('T',' ') if attendance else '点击上方刷新获取学校记录'))
        calendars = {kind:self.activity.get_snapshot(account,'calendar-'+kind) for kind in KINDS}
        rows=[]
        for kind,saved in calendars.items():
            for row in saved.get('payload',{}).get('rows',[]):
                start=start_time(row)
                if visible_lecture(kind,row) and start and start.date()==now.date(): rows.append((kind,row))
        rows.sort(key=lambda item:start_time(item[1]))
        # Keep text selection and keyboard focus across timer ticks.
        signature=json.dumps([account,calendars,self.reminders.config(account),now.strftime('%Y-%m-%d %H:%M')],sort_keys=True,ensure_ascii=False)
        if signature==self._lecture_signature: return
        self._lecture_signature=signature
        content=QWidget(); box=QVBoxLayout(content); box.setContentsMargins(0,0,12,8); box.setSpacing(12)
        if not rows:
            empty=label('今天暂无讲座安排' if all(calendars.values()) else '还没有今天的讲座列表\n点击上方刷新，获取人文与科研讲座安排')
            empty.setAlignment(Qt.AlignCenter); empty.setMinimumHeight(180); box.addWidget(empty)
        for kind,row in rows: box.addWidget(self.lecture_card(account,kind,row,now))
        box.addStretch()
        old=self.lecture_scroll.takeWidget()
        if old: old.deleteLater()
        self.lecture_scroll.setWidget(content)
        self.lecture_list_summary.setText(now.strftime('%m 月 %d 日') + f' · 共 {len(rows)} 场 · 按开始时间排列 · 人文/科研仅雁栖湖 · 仅已报名或无需报名场次')
        stamps=[KINDS[k][0]+' '+v['at'].replace('T',' ') for k,v in calendars.items() if v]
        if not self._lecture_refresh_job:
            self.lecture_refresh_hint.setText('最近同步：'+' / '.join(stamps) if stamps else '尚未同步；没有查询到数据不等于今天没有讲座。')

    def lecture_card(self,account,kind,item,now):
        from .ui import label, row
        name,accent,bg=KINDS[kind]
        card=QFrame(); card.setObjectName('lectureEntry')
        card.setStyleSheet(f'QFrame#lectureEntry {{background:white;border:1px solid {bg};border-left:5px solid {accent};border-radius:10px;}} QLabel,QCheckBox {{background:transparent;}}')
        box=QVBoxLayout(card);box.setContentsMargins(18,14,18,14);box.setSpacing(9)
        start=start_time(item); end=start_time({'start':item.get('end','')})
        status='已结束' if end and now>=end else '进行中' if now>=start else '即将开始'
        top=label(f'{name}   ·   {start:%H:%M}' + (f'—{end:%H:%M}' if end else '') + '   ·   '+status)
        top.setStyleSheet(f'color:{accent};font-weight:700;font-size:14px')
        title=label(item.get('title','未命名讲座'));title.setStyleSheet('font-size:18px;font-weight:600;color:#253d47')
        box.addWidget(top);box.addWidget(title);box.addWidget(label('地点  '+(item.get('location') or '学校未提供'),'muted'))
        enabled,minutes=self.reminders.options(account,kind,item)
        check=QCheckBox('提醒本场');check.setChecked(enabled)
        spin=QSpinBox();spin.setRange(0,1440);spin.setValue(minutes);spin.setSuffix(' 分钟')
        config=self.reminders.config(account); override=config['overrides'].get(lecture_key(kind,item),{})
        mode=QComboBox();mode.addItems(['跟随默认提前时间','单独设置提前时间']);mode.setCurrentIndex(int('minutes' in override))
        def update(*_):
            try:
                self.reminders.save_lecture(account,kind,item,check.isChecked(),spin.value() if mode.currentIndex() else None)
                spin.setEnabled(check.isChecked() and bool(mode.currentIndex()))
            except Exception as exc:self.error(str(exc))
        check.toggled.connect(update);spin.valueChanged.connect(update);mode.currentIndexChanged.connect(update)
        spin.setEnabled(enabled and bool(mode.currentIndex()))
        controls=QWidget();controls.setLayout(row(check,mode,spin));controls.setEnabled(config['enabled'] and now<=start)
        box.addWidget(controls)
        key=account+':'+lecture_key(kind,item)
        if key in self.reminders.data['sent']:box.addWidget(label('本场已发送提醒','muted'))
        return card

    def lecture_tick(self):
        if self._quitting:return
        try:
            self.refresh_today_lectures()
            account=scope(self.vault,'sep')
            calendars={k:self.activity.get_snapshot(account,'calendar-'+k).get('payload',{}).get('rows',[]) for k in KINDS}
            calendars={k:[r for r in rows if visible_lecture(k,r)] for k,rows in calendars.items()}
            due=self.reminders.due(account,calendars)
            if due:
                self.show_lecture_popup(due)
                self.reminders.mark_sent(account,due)
                self._lecture_signature=None
        except Exception:
            self.lecture_refresh_hint.setText('讲座提醒检查未完成，请检查本地数据或重新刷新。')

    def show_lecture_popup(self,items,test=False):
        from .ui import label,button,row
        popup=QDialog(self,Qt.Tool|Qt.WindowStaysOnTopHint)
        popup.setAttribute(Qt.WA_DeleteOnClose);popup.setWindowTitle('讲座提醒'+(' · 测试' if test else ''))
        popup.setMinimumWidth(440);popup.resize(500,300)
        box=QVBoxLayout(popup);box.setContentsMargins(22,20,22,20);box.setSpacing(14)
        heading=label('讲座即将开始' if not test else '提醒效果预览');heading.setStyleSheet('font-size:22px;font-weight:700');box.addWidget(heading)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.NoFrame)
        content=QWidget();body=QVBoxLayout(content)
        for kind,item in items:
            start=start_time(item)
            body.addWidget(label(f'{KINDS[kind][0]}  ·  {start:%m-%d %H:%M}\n{item.get("title","")}\n{item.get("location") or "地点未提供"}'))
        scroll.setWidget(content);box.addWidget(scroll)
        def open_list():self.nav.setCurrentRow(2);self.show_window();popup.close()
        box.addLayout(row(button('查看今日讲座',open_list,True),button('知道了',popup.close)))
        self._lecture_popups.append(popup)
        popup.destroyed.connect(lambda:self._lecture_popups.remove(popup) if popup in self._lecture_popups else None)
        area=self.screen().availableGeometry();popup.move(area.right()-popup.width()-24,area.bottom()-popup.height()-24)
        popup.show();QTimer.singleShot(60000,popup.close)

    def test_lecture_popup(self):
        self.show_lecture_popup([('science',{'title':'这是一条测试提醒，不会创建签到任务','start':now_beijing().isoformat(),'location':'正式提醒会显示讲座时间与地点'})],test=True)
