"""Local catalog metadata shared by planning and enrollment previews."""
import sqlite3
from contextlib import closing

# Stable category colors, shared by the catalog, shortlist and week calendar.
PALETTE = {
    '学科核心课': ('#e7edff', '#344ea0'),
    '专业核心课': ('#eee6ff', '#6b3ba0'),
    '专业课': ('#def3ef', '#196b60'),
    '公共必修课': ('#ffe9d8', '#945019'),
    '公共选修课': ('#fff3cc', '#81600d'),
    '研讨课': ('#fde5ef', '#98456a'),
    '实践课': ('#e5f2d8', '#466e28'),
    '实验课': ('#dff2fb', '#266882'),
    '科学前沿讲座': ('#ede8e2', '#705a40'),
    '未分类': ('#edf0f3', '#556070'),
}


def colors(category):
    return PALETTE.get(category, PALETTE['未分类'])


class Catalog:
    def __init__(self, db):
        self.db = db
        self.details = {}
        self.courses = db.get_all_courses()
        self.by_id = {c.id: c for c in self.courses}
        self.by_code = {}
        for course in self.courses:
            self.by_code.setdefault(course.code, []).append(course)
        if not db.is_valid:
            return
        with closing(sqlite3.connect(db.db_path)) as connection:
            connection.row_factory = sqlite3.Row
            for row in connection.execute('SELECT * FROM courses'):
                self.details[row['id']] = dict(row)

    def info(self, course):
        from coursesystem.disciplines import CATEGORIES
        raw = self.details.get(course.id, {})
        discipline = course.code[6:10] if len(course.code) >= 18 else ''
        mapped = CATEGORIES.get(discipline)
        return {
            'code': course.code, 'name': course.name,
            'hours': str(course.hours or '未提供'), 'credits': str(course.credits or '未提供'),
            'department': raw.get('department') or '未提供',
            'teacher': raw.get('teacher') or '未提供',
            'discipline': f'{mapped}（{discipline}）' if mapped else '未提供',
            'category': raw.get('attribute') or '未分类',
        }

    def resolve(self, code):
        matches = self.by_code.get(code, [])
        return matches[0] if len(matches) == 1 else None

    def search_text(self, course):
        return ' '.join(self.info(course).values()).casefold()
