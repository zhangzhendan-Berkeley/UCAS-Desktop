import unittest
from ucasdesk.lecture_visibility import visible_lecture

class VisibilityTests(unittest.TestCase):
    def test_both_categories_require_campus_and_registration_evidence(self):
        for kind in ('science', 'humanity'):
            for state in ('registered', 'not-required'):
                self.assertTrue(visible_lecture(kind, dict(location='雁栖湖 教一楼', registrationStatus=state)))
                self.assertFalse(visible_lecture(kind, dict(location='玉泉路', registrationStatus=state)))
                self.assertFalse(visible_lecture(kind, dict(location='雁栖湖/玉泉路', registrationStatus=state)))
            self.assertFalse(visible_lecture(kind, dict(location='雁栖湖')))
            self.assertFalse(visible_lecture(kind, dict(location='雁栖湖', registrationStatus='unknown-or-unregistered')))

if __name__ == '__main__': unittest.main()
