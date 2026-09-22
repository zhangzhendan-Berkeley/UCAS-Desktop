import unittest
from ucasdesk.lecture_visibility import visible_lecture, calendar_lecture

class VisibilityTests(unittest.TestCase):
    def test_both_categories_require_campus_and_registration_evidence(self):
        for kind in ('science', 'humanity'):
            for state in ('registered', 'not-required'):
                self.assertTrue(visible_lecture(kind, dict(location='雁栖湖 教一楼', registrationStatus=state)))
                self.assertFalse(visible_lecture(kind, dict(location='玉泉路', registrationStatus=state)))
                self.assertFalse(visible_lecture(kind, dict(location='雁栖湖/玉泉路', registrationStatus=state)))
            self.assertFalse(visible_lecture(kind, dict(location='雁栖湖')))
            self.assertFalse(visible_lecture(kind, dict(location='雁栖湖', registrationStatus='unknown-or-unregistered')))

    def test_science_undergraduate_department_is_hidden(self):
        for status in ('registered', 'not-required', 'unknown-or-unregistered'):
            row = dict(title='人工智能', location='雁栖湖', department=' 本科部 ', registrationStatus=status)
            self.assertFalse(visible_lecture('science', row))
            self.assertFalse(calendar_lecture('science', row))
        self.assertTrue(visible_lecture('science', row | {'department': '计算机学院', 'registrationStatus': 'registered'}))

    def test_calendar_requires_registered_and_excludes_undergraduate(self):
        for kind in ('humanity', 'science'):
            row = dict(title='人工智能', location='雁栖湖', registrationStatus='registered')
            self.assertTrue(calendar_lecture(kind, row))
            self.assertTrue(calendar_lecture(kind, row | {'registrationStatus': 'not-required'}))
            for status in ('unknown-or-unregistered', ''):
                self.assertFalse(calendar_lecture(kind, row | {'registrationStatus': status}))
            if kind == 'science':
                self.assertFalse(calendar_lecture(kind, row | {'department': '本科部'}))

if __name__ == '__main__': unittest.main()
