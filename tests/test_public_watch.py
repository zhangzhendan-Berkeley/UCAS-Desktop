import unittest
from unittest.mock import Mock
from ucasdesk.public_watch import Watch, parse_counts, query_counts

CODE = '180081050100P1001H'
HTML = '<table><tr><th>课程编码</th><th>限选人数</th><th>已选人数</th></tr><tr><td>'+CODE+'</td><td>40</td><td>30</td></tr></table>'

class PublicWatchTests(unittest.TestCase):
    def test_parser_requires_exact_unique_code_and_integer_counts(self):
        self.assertEqual(parse_counts(HTML, CODE), (30, 40))
        for html in (HTML.replace(CODE, CODE+'X'), HTML.replace('30</td>', '-</td>'), HTML+HTML, '<html>login</html>'):
            with self.assertRaises(ValueError): parse_counts(html, CODE)

    def test_request_has_only_public_parameters_and_no_redirects(self):
        session = Mock(); session.post.return_value = Mock(status_code=200, text=HTML)
        self.assertEqual(query_counts(session, 'user-term', CODE), (30, 40))
        kwargs = session.post.call_args.kwargs
        self.assertEqual(kwargs['data'], {'termId': 'user-term', 'courseCode': CODE})
        self.assertFalse(kwargs['allow_redirects'])

    def test_failure_preserves_baseline_no_false_zero(self):
        watch = Watch([CODE]); watch.observe(CODE, 40, 40, 1)
        with self.assertRaises(ValueError): parse_counts('', CODE)
        self.assertEqual(watch.baselines[CODE].count, 40)
        watch.observe(CODE, 40, 40, 3); self.assertIsNone(watch.take())
        watch.observe(CODE, 39, 40, 4); self.assertEqual(watch.take(), CODE)

    def test_merge_and_unknown_never_resubmit(self):
        watch = Watch([CODE]); watch.observe(CODE, 40, 40, 0)
        watch.observe(CODE, 39, 40, 1); watch.observe(CODE, 38, 40, 2)
        self.assertEqual(watch.take(), CODE)
        watch.observe(CODE, 37, 40, 3); self.assertIsNone(watch.take())
        watch.finish(CODE, 'unknown'); watch.observe(CODE, 36, 40, 9999)
        self.assertIsNone(watch.take())

    def test_initial_fallback_and_unavailable_are_not_success(self):
        watch = Watch([CODE], initial=True, fallback=3600)
        watch.observe(CODE, 30, 40, 0); self.assertEqual(watch.take(), CODE)
        watch.finish(CODE, 'unavailable'); self.assertNotIn(CODE, watch.blocked)
        watch.observe(CODE, 30, 40, 3599); self.assertIsNone(watch.take())
        watch.observe(CODE, 30, 40, 3600); self.assertEqual(watch.take(), CODE)
        watch.finish(CODE, 'success'); watch.observe(CODE, 29, 40, 8000)
        self.assertIsNone(watch.take())

    def test_other_courses_continue_during_login_and_restart_drops_signals(self):
        watch = Watch([CODE, 'OTHER'], initial=True)
        watch.observe(CODE, 30, 40, 0); self.assertEqual(watch.take(), CODE)
        watch.observe('OTHER', 20, 40, 1)
        self.assertIn('OTHER', watch.pending); self.assertIsNone(watch.take())
        watch.finish(CODE, 'unknown'); self.assertEqual(watch.take(), 'OTHER')
        self.assertIsNone(Watch([CODE, 'OTHER']).take())
