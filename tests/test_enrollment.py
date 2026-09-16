import tempfile
import unittest
from pathlib import Path
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from ucasdesk.enrollment import Enrollment, match_enrollment, same_semester
from ucasdesk.iclass import IClass
from ucasdesk.sep import parse_course_tables, logged_in, read_enrolled


def course(identifier=1, code='180086081200P1001H-2', name='测试课', semester='2026年秋季学期'):
    return SimpleNamespace(id=identifier, code=code, name=name, schedules=[SimpleNamespace(semester=semester)])


class EnrollmentTests(unittest.TestCase):
    def test_exact_code_and_name_no_suffix_or_name_guessing(self):
        catalog = [course(), course(2, '180086081200P1001H', '测试课')]
        matches, unresolved = match_enrollment([{'code': '180086081200P1001H-2', 'name': '测试课'}], catalog)
        self.assertEqual(list(matches), [1])
        matches, unresolved = match_enrollment([{'code': '180086081200P1001H-3', 'name': '测试课'}], catalog)
        self.assertFalse(matches)
        self.assertEqual(len(unresolved), 1)
        self.assertFalse(same_semester(course(), '2027年春季'))

    def test_snapshot_survives_restart_and_account_change_invalidates_status(self):
        account = {'username': 'one'}
        with tempfile.TemporaryDirectory() as tmp:
            enroll = Enrollment(Path(tmp), lambda _: account)
            self.assertFalse(enroll.status(course())[1])
            snapshot = {'source': 'iclass', 'complete': True, 'semester': '2026年秋季',
                        'courses': [{'code': course().code, 'name': '测试课'}]}
            enroll.save(snapshot, 'one')
            self.assertTrue(Enrollment(Path(tmp), lambda _: account).status(course())[1])
            with self.assertRaises(ValueError): enroll.save(snapshot | {'complete': False}, 'one')
            self.assertTrue(enroll.status(course())[1])
            account['username'] = 'two'
            self.assertFalse(enroll.status(course())[1])
            self.assertNotIn('one', enroll.path.read_text(encoding='utf-8'))

    def test_iclass_dates_override_stale_semester_label(self):
        client = IClass('fixture', 'secret')
        row = {'courseNum': course().code, 'courseName': '测试课', 'beginDate': '20260831',
               'endDate': '20270131', 'semesterName': '2014-2015第一学期', 'isMyCourse': 0}
        with patch.object(client, 'login'), patch.object(client, '_request', return_value={
                'STATUS': '0', 'result': [row, row | {'beginDate': '20250831', 'endDate': '20260131'}]}) as request:
            client.user_id, client.session_id = 'fixture-id', 'session'
            result = client.my_courses(date(2026, 9, 16))
        self.assertEqual(len(result['courses']), 1)
        self.assertEqual(result['semester'], '2026年秋季')
        self.assertEqual(request.call_args.args[1], '/my/get_my_course.action')

    def test_missing_dates_not_silently_included(self):
        client = IClass('fixture', 'secret')
        with patch.object(client, 'login'), patch.object(client, '_request', return_value={
                'STATUS': '0', 'result': [{'courseNum': course().code, 'courseName': '测试课'}]}):
            with self.assertRaises(RuntimeError): client.my_courses(date(2026, 9, 16))

    def test_sep_headers_empty_and_malformed_pages(self):
        tables = [{'headers': ['课程编码', '课程名称', '学分'], 'rows': [[course().code, '测试课', '3']]}]
        self.assertEqual(parse_course_tables(tables), [{'code': course().code, 'name': '测试课'}])
        self.assertEqual(parse_course_tables([{'headers': ['课程编码', '课程名称'], 'rows': [['暂无数据']]}]), [])
        with self.assertRaises(ValueError): parse_course_tables([{'headers': ['用户名'], 'rows': []}])
        with self.assertRaises(ValueError): parse_course_tables([{'headers': ['课程编码', '课程名称'], 'rows': [['123', '课程']]}])

    def test_course_catalog_never_becomes_enrolled_list(self):
        driver = SimpleNamespace(current_url='https://xkgo.ucas.ac.cn:3000/courseManage/selectCourse')
        with self.assertRaises(RuntimeError): read_enrolled(driver)
        self.assertTrue(logged_in('https://sep.ucas.ac.cn/sepCard/card'))
        self.assertFalse(logged_in('https://example.org/sepCard/card'))


if __name__ == '__main__': unittest.main()
