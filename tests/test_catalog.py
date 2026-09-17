import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ucasdesk.catalog import Catalog, colors


class CatalogTests(unittest.TestCase):
    def make_catalog(self, rows, optional=True):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'courses.db'
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute('CREATE TABLE courses (id INTEGER, department TEXT, teacher TEXT, attribute TEXT)' if optional else 'CREATE TABLE courses (id INTEGER)')
            for c in rows:
                if optional:
                    conn.execute('INSERT INTO courses VALUES (?, ?, ?, ?)', (c.id, '测试学院', '张老师', '学科核心课'))
                else:
                    conn.execute('INSERT INTO courses VALUES (?)', (c.id,))
        return Catalog(SimpleNamespace(is_valid=True, db_path=str(path), get_all_courses=lambda: rows))

    @staticmethod
    def course(identifier=1, code='180086081200P1001H-2'):
        return SimpleNamespace(id=identifier, code=code, name='计算机课程', hours='40', credits='2')

    def test_exact_section_code_and_ambiguous_code(self):
        catalog = self.make_catalog([self.course()])
        self.assertEqual(catalog.resolve(self.course().code).id, 1)
        self.assertIsNone(catalog.resolve(self.course().code.removesuffix('-2')))
        catalog = self.make_catalog([self.course(), self.course(2)])
        self.assertIsNone(catalog.resolve(self.course().code))

    def test_metadata_and_unknown_fields(self):
        with patch.dict('sys.modules', {'coursesystem.disciplines': SimpleNamespace(CATEGORIES={'0812': '计算机科学与技术'})}):
            catalog = self.make_catalog([self.course()])
            info = catalog.info(self.course())
            self.assertEqual(info['teacher'], '张老师')
            self.assertEqual(info['discipline'], '计算机科学与技术（0812）')
            self.assertIn('测试学院', catalog.search_text(self.course()))
            legacy = self.make_catalog([self.course()], optional=False)
            self.assertEqual(legacy.info(self.course())['teacher'], '未提供')
            self.assertEqual(legacy.info(self.course())['category'], '未分类')

    def test_stable_category_colors_and_unknown_fallback(self):
        self.assertNotEqual(colors('学科核心课'), colors('专业课'))
        self.assertEqual(colors('未知类型'), colors('未分类'))


if __name__ == '__main__':
    unittest.main()
