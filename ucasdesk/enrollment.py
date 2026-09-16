"""Own-course snapshots; exact catalog matches only. No school writes."""
import hashlib
import re
from .core import read_json, write_json


def account_hash(username):
    return hashlib.sha256(username.strip().encode()).hexdigest()


def semester_key(value):
    match = re.search(r'(20\d{2}).*?(春|秋)', value or '')
    return ''.join(match.groups()) if match else ''


def match_enrollment(rows, catalog):
    matches, unresolved = {}, []
    for row in rows:
        choices = [c for c in catalog if c.code == row['code'] and c.name.strip() == row['name'].strip()]
        if len(choices) == 1:
            matches[choices[0].id] = row
        else:
            unresolved.append(row | {'reason': '编码/名称未唯一匹配到本地课程库'})
    return matches, unresolved


def same_semester(course, semester):
    expected = semester_key(semester)
    local = {semester_key(s.semester) for s in course.schedules if semester_key(s.semester)}
    return not expected or not local or expected in local


class Enrollment:
    def __init__(self, directory, account_provider):
        self.path = directory / 'enrollment.json'
        self.account_provider = account_provider
        self.snapshot = read_json(self.path, {})

    def current(self):
        source = self.snapshot.get('source')
        if source not in ('iclass', 'sep'):
            return {}
        username = self.account_provider(source).get('username', '')
        return self.snapshot if username and self.snapshot.get('account_hash') == account_hash(username) else {}

    def save(self, snapshot, username):
        if snapshot.get('source') not in ('iclass', 'sep') or not snapshot.get('complete') or not isinstance(snapshot.get('courses'), list):
            raise ValueError('查询未完成，保留上次已选课程记录。')
        if any(not row.get('code') or not row.get('name') for row in snapshot['courses']):
            raise ValueError('部分课程缺少编码或名称，未替换已选课程记录。')
        candidate = snapshot | {'account_hash': account_hash(username)}
        write_json(self.path, candidate)
        self.snapshot = candidate

    def status(self, course):
        snapshot = self.current()
        if not snapshot:
            return '未核实 / 计划选', False
        if not same_semester(course, snapshot.get('semester', '')):
            return '未核实（学期不同）', False
        exact = any(row['code'] == course.code and row['name'].strip() == course.name.strip() for row in snapshot['courses'])
        if exact:
            return ('已选上（轻新课堂）' if snapshot['source'] == 'iclass' else '已选上（SEP 预选）'), True
        return '未选上（本次未查到）', False
