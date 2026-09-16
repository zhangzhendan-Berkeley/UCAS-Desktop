"""Thin extension of the upstream planner; preserves its database and conflict checks."""
from html import escape
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QTableWidgetItem, QLabel, QGroupBox, QMessageBox,
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTextBrowser, QListWidget,
    QListWidgetItem, QWidget, QHeaderView, QComboBox, QMenu)
from coursesystem.main_window import MainWindow
from coursesystem.conflict import is_in_week, parse_time_slots
from .core import read_json, write_json
from .enrollment import match_enrollment, same_semester
from .catalog import Catalog, colors, PALETTE


class IntegratedPlanner(MainWindow):
    def __init__(self, db, enrollment, directory):
        self.enrollment = enrollment
        self.directory = directory
        self.grab_path = directory / 'grab-courses.json'
        self.checked_codes = set(read_json(self.grab_path, []))
        self.alternatives_path = directory / 'alternatives.json'
        self.alternatives = read_json(self.alternatives_path, [])
        self.catalog = Catalog(db)
        super().__init__(db)
        group = self.selected_list.parentWidget()
        if isinstance(group, QGroupBox):
            group.setTitle('规划清单（含已选课程）')
        self.selected_list.itemChanged.connect(self.check_changed)
        self._enhance_ui()
        self.apply_enrollment()

    def _save_state(self):
        from coursesystem.state import save_state
        path = Path(self.db.db_path).resolve()
        try:
            saved_path = str(path.relative_to(self.directory.resolve()))
        except ValueError:
            saved_path = str(path)
        save_state(db_path=saved_path, selected_course_ids=list(self.selected))

    def _fill_table(self, courses):
        table = self.course_table
        table.setSortingEnabled(False)
        table.setColumnCount(10)
        table.setHorizontalHeaderLabels(['课程编号', '课程名称', '学分', '学时', '课程类别', '学院', '主讲教师', '一级学科 / 专业学位类别', '选课状态', '备选'])
        table.setRowCount(len(courses))
        for index, course in enumerate(courses):
            info = self.catalog.info(course)
            status, enrolled = self.enrollment.status(course)
            values = [course.code, course.name, course.credits, course.hours,
                      info['category'], info['department'], info['teacher'], info['discipline'], status,
                      '已备选' if self.is_alternative(course) else '']
            bg, fg = colors(info['category'])
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, course.id)
                item.setToolTip(f'{course.name}\n{course.code}\n{info["department"]} · {info["teacher"]}\n{info["category"]} · {status}\n双击查看详情')
                if column in (1, 4):
                    item.setBackground(QColor(bg))
                    item.setForeground(QColor(fg))
                if column == 8 and enrolled:
                    item.setForeground(QColor('#24744f'))
                table.setItem(index, column, item)
        table.setSortingEnabled(True)
        self.result_count_label.setText(f'找到 {len(courses)} 门课程 · 双击查看详情 · 加入规划前会检查时间冲突')

    def _load_courses(self):
        self.catalog = Catalog(self.db)
        super()._load_courses()
        if hasattr(self, 'type_filter'):
            self.refresh_types()
            self.refresh_alternatives()

    def _apply_filters(self):
        if not self.db.is_valid:
            self._show_empty_db_placeholder()
            return
        courses = self.db.search_courses(
            department=self.dept_combo.currentData(), level=self.level_combo.currentData(),
            campus=self.campus_combo.currentData(), unit=self.unit_combo.currentData(),
            menlei=self.menlei_combo.currentData(), category=self.category_combo.currentData(),
            field=self.field_combo.currentData(), attribute=self.attr_combo.currentData())
        terms = self.search_input.text().strip().casefold().split()
        category = self.type_filter.currentData() if hasattr(self, 'type_filter') else None
        courses = [c for c in courses if (not category or self.catalog.info(c)['category'] == category)
                   and all(t in self.catalog.search_text(c) for t in terms)]
        self._fill_table(courses)

    def _on_clear_search(self):
        if hasattr(self, 'type_filter'):
            self.type_filter.setCurrentIndex(0)
        super()._on_clear_search()

    def refresh_types(self):
        selected = self.type_filter.currentData()
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem('全部课程类别', None)
        for category in sorted({self.catalog.info(c)['category'] for c in self.catalog.courses}):
            self.type_filter.addItem(category, category)
        self.type_filter.setCurrentIndex(max(0, self.type_filter.findData(selected)))
        self.type_filter.blockSignals(False)

    def _enhance_ui(self):
        self.search_input.setPlaceholderText('搜索课程名称、完整编号、教师、学院或学科；空格分隔多个条件')
        self.course_table.doubleClicked.disconnect()
        self.course_table.doubleClicked.connect(lambda: self.show_course(self.current_course_id()))
        header = self.course_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        for column, width in enumerate([205, 220, 58, 58, 120, 165, 125, 205, 175, 80]):
            self.course_table.setColumnWidth(column, width)
        self.course_table.verticalHeader().setDefaultSectionSize(42)
        self.course_table.setAlternatingRowColors(True)
        self.course_table.setSelectionMode(self.course_table.SelectionMode.SingleSelection)
        self.type_filter = QComboBox()
        self.type_filter.setMinimumWidth(150)
        self.refresh_types()
        self.type_filter.currentIndexChanged.connect(self._apply_filters)
        search_layout = self.search_input.parentWidget().layout()
        quick = QHBoxLayout()
        quick.addWidget(QLabel('课程类别'))
        quick.addWidget(self.type_filter)
        quick.addStretch()
        quick.addWidget(QLabel('颜色按课程类别区分；详细筛选可选学院、校区和学科'))
        search_layout.insertLayout(0, quick)
        search_layout.removeWidget(self.search_input)
        previous_buttons = search_layout.takeAt(1).layout()
        previous_buttons.removeWidget(self.search_btn)
        previous_buttons.removeWidget(self.clear_btn)
        previous_buttons.deleteLater()
        search_row = QHBoxLayout()
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_btn)
        search_row.addWidget(self.clear_btn)
        search_layout.insertLayout(1, search_row)
        self.filter_toggle.setText('学院 / 校区 / 学科等筛选')
        self._filter_labels[self.category_combo].setText('一级学科')
        # Four equal filter columns use the available full-page width.
        grid = self.filter_panel.layout()
        for index, (combo, label) in enumerate(self._filter_labels.items()):
            grid.removeWidget(label)
            grid.removeWidget(combo)
            grid.addWidget(label, index // 4, index % 4 * 2)
            grid.addWidget(combo, index // 4, index % 4 * 2 + 1)
            grid.setColumnStretch(index % 4 * 2 + 1, 1)
        actions = QHBoxLayout()
        for title, callback in [('查看详情', lambda: self.show_course(self.current_course_id())),
                                ('加入规划', self._add_current_course),
                                ('加入备选', self.save_alternative),
                                ('导入课表', self._import)]:
            btn = QPushButton(title)
            btn.clicked.connect(callback)
            actions.addWidget(btn)
        actions.addStretch()
        self.course_table.parentWidget().layout().addLayout(actions)
        # Keep checkboxes exclusively for grabbing; details never remove a plan.
        self.selected_list.doubleClicked.disconnect()
        self.selected_list.doubleClicked.connect(lambda: self.show_course(
            self.selected_list.currentItem().data(Qt.UserRole) if self.selected_list.currentItem() else None))
        self.selected_list.setSpacing(5)
        details_btn = QPushButton('查看选中课程详情')
        details_btn.clicked.connect(lambda: self.show_course(
            self.selected_list.currentItem().data(Qt.UserRole) if self.selected_list.currentItem() else None))
        self.selected_list.parentWidget().layout().addWidget(details_btn)
        self.alternatives_page = QWidget()
        layout = QVBoxLayout(self.alternatives_page)
        hint = QLabel('备选保存候选课程，不计入学分、不占用周课表，也不会自动加入抢课。双击查看详情。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.alternatives_list = QListWidget()
        self.alternatives_list.setSpacing(5)
        layout.addWidget(self.alternatives_list, 1)
        actions = QHBoxLayout()
        for title, callback in [('加入规划', self.promote_alternative), ('移除备选', self.remove_alternative)]:
            btn = QPushButton(title)
            btn.clicked.connect(callback)
            actions.addWidget(btn)
        actions.addStretch()
        layout.addLayout(actions)
        self.alternatives_list.itemDoubleClicked.connect(lambda item: self.show_course(item.data(Qt.UserRole)))
        self.refresh_alternatives()
        self.week_view.week_spin.valueChanged.connect(self.paint_week)
        self.week_view.table.cellDoubleClicked.connect(self.week_details)
        self.week_view.table.verticalHeader().setMinimumSectionSize(44)
        for label in self.week_view.findChildren(QLabel):
            if '正常课程' in label.text():
                label.setText('红色：时间冲突 · 双击课表查看详情')
        legend = QLabel('　'.join(f'<span style="color:{fg}">● {escape(name)}</span>' for name, (_, fg) in PALETTE.items()))
        legend.setWordWrap(True)
        self.week_view.layout().addWidget(legend)

    def current_course_id(self):
        item = self.course_table.item(self.course_table.currentRow(), 0)
        return item.data(Qt.UserRole) if item else None

    def is_alternative(self, course):
        return any(x['code'] == course.code and x['name'] == course.name for x in self.alternatives)

    def save_alternative(self):
        course = self.catalog.by_id.get(self.current_course_id())
        if course:
            self.add_alternative(course)

    def add_alternative(self, course):
        if not self.is_alternative(course):
            self.alternatives.append({'code': course.code, 'name': course.name})
            write_json(self.alternatives_path, self.alternatives)
        self.refresh_alternatives()
        self._apply_filters()

    def refresh_alternatives(self):
        self.alternatives_list.clear()
        for index, saved in enumerate(self.alternatives):
            course = self.catalog.resolve(saved['code'])
            if course and course.name != saved['name']:
                course = None
            text = f'{saved["name"]}\n{saved["code"]}'
            if course:
                info = self.catalog.info(course)
                text += f'\n{info["category"]} · {info["credits"]} 学分 · {info["teacher"]} · {info["department"]}'
            else:
                text += '\n当前课程库未唯一匹配；已保留备选记录'
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, course.id if course else None)
            item.setData(Qt.UserRole + 1, index)
            if course:
                bg, fg = colors(info['category'])
                item.setBackground(QColor(bg))
                item.setForeground(QColor(fg))
            self.alternatives_list.addItem(item)

    def remove_alternative(self):
        item = self.alternatives_list.currentItem()
        if item:
            self.alternatives.pop(item.data(Qt.UserRole + 1))
            write_json(self.alternatives_path, self.alternatives)
            self.refresh_alternatives()
            self._apply_filters()

    def promote_alternative(self):
        item = self.alternatives_list.currentItem()
        if item:
            self.add_course_id(item.data(Qt.UserRole))

    def _add_current_course(self):
        self.add_course_id(self.current_course_id())

    def add_course_id(self, identifier):
        if identifier is None:
            return
        if identifier in self.selected:
            QMessageBox.information(self, '已在规划中', '这门课已在规划清单中。')
            return
        found = self.db.get_courses_with_schedules([identifier])
        if not found:
            return
        course = found[0]
        conflicts = self._conflicts_with_selected(course)
        if conflicts and QMessageBox.question(self, '时间冲突',
                '与以下规划课程冲突：' + '、'.join(c.name for c in conflicts) + '\n仍要加入规划吗？') != QMessageBox.Yes:
            return
        self.selected[identifier] = course
        self._refresh_views()

    def show_course(self, identifier):
        courses = self.db.get_courses_with_schedules([identifier]) if identifier is not None else []
        if not courses:
            return
        course = courses[0]
        info = self.catalog.info(course)
        dialog = QDialog(self)
        dialog.setWindowTitle('课程详情 · ' + course.name)
        dialog.resize(780, 630)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        rows = [('课程名称', info['name']), ('完整编号', info['code']), ('学分 / 学时', f'{info["credits"]} / {info["hours"]}'),
                ('开课学院', info['department']), ('主讲教师', info['teacher']), ('课程类别', info['category']),
                ('一级学科 / 专业学位类别', info['discipline']), ('选课状态', self.enrollment.status(course)[0])]
        html = '<h2>' + escape(course.name) + '</h2><table cellpadding="7">'
        html += ''.join(f'<tr><td><b>{escape(k)}</b></td><td>{escape(v)}</td></tr>' for k, v in rows) + '</table><h3>教学安排</h3>'
        html += (''.join(f'<p>{escape(s.semester)} · 周{"一二三四五六日"[s.day_of_week-1] if 1 <= s.day_of_week <= 7 else s.day_of_week} · 第{escape(s.time_slots)}节 · {escape(s.weeks)} · {escape(s.location)}</p>' for s in course.schedules) or '<p>未提供排课</p>')
        html += '<p style="color:#68746c">来源：当前本地课表快照；一级学科 / 专业学位类别按课程编码映射。未提供的字段不作推测。余量与最新安排以 SEP 为准。</p>'
        browser.setHtml(html)
        layout.addWidget(browser)
        actions = QHBoxLayout()
        for title, callback in [('加入规划', lambda: self.add_course_id(identifier)),
                                ('加入备选', lambda: self.add_alternative(course)), ('关闭', dialog.accept)]:
            btn = QPushButton(title)
            btn.clicked.connect(callback)
            actions.addWidget(btn)
        layout.addLayout(actions)
        dialog.exec()

    def paint_week(self, *_):
        self.week_view.table.clearSpans()
        self.week_cells = {}
        week = self.week_view.current_week()
        for course in self.selected.values():
            for sched in course.schedules:
                if not 1 <= sched.day_of_week <= 7 or not is_in_week(sched.weeks, week):
                    continue
                for slot in parse_time_slots(sched.time_slots):
                    if 1 <= slot <= 13:
                        self.week_cells.setdefault((slot - 1, sched.day_of_week), {})[course.id] = course
        for cell, courses in self.week_cells.items():
            item = self.week_view.table.item(*cell)
            if not item:
                continue
            if len(courses) == 1:
                course = next(iter(courses.values()))
                info = self.catalog.info(course)
                bg, fg = colors(info['category'])
                item.setBackground(QColor(bg))
                item.setForeground(QColor(fg))
            item.setToolTip('\n\n'.join(f'{c.name}\n{c.code}\n{self.catalog.info(c)["category"]} · {self.catalog.info(c)["teacher"]}\n双击查看详情' for c in courses.values()))
        # Render consecutive periods as one readable block, preserving conflicts.
        for day in range(1, 8):
            row = 0
            while row < 13:
                item = self.week_view.table.item(row, day)
                ids = set(self.week_cells.get((row, day), {}))
                end = row + 1
                if item and ids:
                    while end < 13 and set(self.week_cells.get((end, day), {})) == ids:
                        other = self.week_view.table.item(end, day)
                        if not other or other.text() != item.text():
                            break
                        end += 1
                    if end - row > 1:
                        self.week_view.table.setSpan(row, day, end - row, 1)
                row = end

    def week_details(self, row, column):
        courses = self.week_cells.get((row, column), {})
        if len(courses) == 1:
            self.show_course(next(iter(courses)))
        elif courses:
            menu = QMenu(self)
            for course in courses.values():
                action = menu.addAction(course.name)
                action.triggered.connect(lambda checked=False, cid=course.id: self.show_course(cid))
            menu.exec(self.week_view.table.viewport().mapToGlobal(self.week_view.table.visualItemRect(self.week_view.table.item(row, column)).center()))

    def _refresh_views(self):
        self.selected_list.blockSignals(True)
        try:
            super()._refresh_views()
            for label in self.stats.findChildren(QLabel):
                label.setText(label.text().replace('已选学分', '规划学分').replace('已选课程', '规划课程'))
            for index in range(self.selected_list.count()):
                item = self.selected_list.item(index)
                course = self.selected.get(item.data(Qt.UserRole))
                if not course:
                    continue
                status, enrolled = self.enrollment.status(course)
                info = self.catalog.info(course)
                item.setText(f'[{status}] {course.name}\n{course.code}\n{info["category"]} · {info["credits"]} 学分 / {info["hours"]} 学时 · {info["teacher"]} · {info["department"]}')
                bg, fg = colors(info['category'])
                item.setBackground(QColor(bg))
                item.setForeground(QColor(fg))
                if enrolled:
                    self.checked_codes.discard(course.code)
                    item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
                    item.setForeground(QColor('#24744f'))
                    item.setToolTip('已选课程保留在周课表中，不导入抢课。')
                else:
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked if course.code in self.checked_codes else Qt.Unchecked)
                    item.setToolTip('勾选后，点击“仅把勾选课程导入抢课”。双击查看详情；移除按钮只影响本地规划。')
        finally:
            self.selected_list.blockSignals(False)
        write_json(self.grab_path, sorted(self.checked_codes))
        self.paint_week()

    def _clear_all(self):
        if self.selected and QMessageBox.question(self, '清空本地规划', '只清空本地规划，不会在学校系统退课。确定继续？') == QMessageBox.Yes:
            self.selected.clear()
            self.checked_codes.clear()
            self._refresh_views()

    def check_changed(self, item):
        course = self.selected.get(item.data(Qt.UserRole))
        if not course or self.enrollment.status(course)[1]:
            return
        if item.checkState() == Qt.Checked:
            self.checked_codes.add(course.code)
        else:
            self.checked_codes.discard(course.code)
        write_json(self.grab_path, sorted(self.checked_codes))

    def checked_pending_codes(self):
        return list(dict.fromkeys(c.code for c in self.selected.values()
                                  if c.code in self.checked_codes and not self.enrollment.status(c)[1]))

    def apply_enrollment(self):
        snapshot = self.enrollment.current()
        matches, unresolved = match_enrollment(snapshot.get('courses', []), self.db.get_all_courses())
        for course in self.db.get_courses_with_schedules(list(matches)):
            if same_semester(course, snapshot.get('semester', '')):
                self.selected[course.id] = course
            else:
                unresolved.append(matches[course.id] | {'reason': '与本地课表学期不同'})
        self._refresh_views()
        self._apply_filters()
        return len(matches) - sum(x.get('reason') == '与本地课表学期不同' for x in unresolved), unresolved
