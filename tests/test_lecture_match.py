import unittest
from ucasdesk.iclass import match_lecture_course
from ucasdesk.core import redact


class LectureMatching(unittest.TestCase):
    def setUp(self):
        self.lecture = {'title': '科学讲座：测试', 'start': '2026-10-16 19:00:00', 'end': '2026-10-16 20:30:00'}
        self.course = {'courseName': '科学讲座: 测试', 'classBeginTime': self.lecture['start'],
                       'classEndTime': self.lecture['end'], 'id': '1234567'}

    def test_unique_full_match(self):
        self.assertEqual(match_lecture_course(self.lecture, [self.course]), self.course)

    def test_rejects_ambiguous_and_partial_matches(self):
        self.assertIsNone(match_lecture_course(self.lecture, [self.course, dict(self.course, id='7654321')]))
        for replacement in [{'courseName': '其他讲座'}, {'classBeginTime': '2026-10-17 19:00:00'},
                            {'classEndTime': '2026-10-16 21:00:00'}, {'id': '8843'}]:
            self.assertIsNone(match_lecture_course(self.lecture, [dict(self.course, **replacement)]))

    def test_portal_diagnostics_do_not_expose_profile_or_tickets(self):
        text = 'url=https://sep.ucas.ac.cn/portal/site/226/' + 'a' * 64 + '?ticket=example\nerror body=PRIVATE-PROFILE\nnext event'
        result = redact(text)
        self.assertNotIn('PRIVATE-PROFILE', result)
        self.assertNotIn('a' * 64, result)
        self.assertNotIn('example', result)
        self.assertIn('next event', result)


if __name__ == '__main__':
    unittest.main()
