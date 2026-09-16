"""Thin extension of the upstream planner; preserves its database and conflict checks."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidgetItem, QLabel, QGroupBox, QMessageBox
from coursesystem.main_window import MainWindow
from .core import read_json, write_json
from .enrollment import match_enrollment, same_semester


class IntegratedPlanner(MainWindow):
    def __init__(self, db, enrollment, directory):
        self.enrollment = enrollment
        self.grab_path = directory / 'grab-courses.json'
        self.checked_codes = set(read_json(self.grab_path, []))
        super().__init__(db)
        group = self.selected_list.parentWidget()
        if isinstance(group, QGroupBox):
            group.setTitle('规划清单（含已选课程）')
        self.selected_list.itemChanged.connect(self.check_changed)
        self.apply_enrollment()

    def _fill_table(self, courses):
        super()._fill_table(courses)
        self.course_table.setColumnCount(5)
        self.course_table.setHorizontalHeaderLabels(['课程代码', '课程名称', '学分', '学时', '选课状态'])
        for index, course in enumerate(courses):
            text, enrolled = self.enrollment.status(course)
            item = QTableWidgetItem(text)
            item.setForeground(QColor('#24744f' if enrolled else '#7b6542'))
            self.course_table.setItem(index, 4, item)

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
                item.setText(f'[{status}] {course.name}\n{course.code}')
                if enrolled:
                    self.checked_codes.discard(course.code)
                    item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
                    item.setForeground(QColor('#24744f'))
                    item.setToolTip('已选课程保留在周课表中，不导入抢课。')
                else:
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked if course.code in self.checked_codes else Qt.Unchecked)
                    item.setToolTip('勾选后，点击“仅把勾选课程导入抢课”。双击仅从本地规划移除，不会退课。')
        finally:
            self.selected_list.blockSignals(False)
        write_json(self.grab_path, sorted(self.checked_codes))

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
