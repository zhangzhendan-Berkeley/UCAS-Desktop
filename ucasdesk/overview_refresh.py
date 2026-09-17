"""Read-only overview refresh results. Individual failures never erase good caches."""
from datetime import datetime

PARTS = {'local': '本机任务与规划', 'today': '今日课程', 'enrollment': '学校已选课程',
    'humanity': '人文讲座列表', 'science': '科研讲座列表',
    'humanity-attendance': '人文有效听讲', 'science-attendance': '科研有效听讲'}
LECTURE_PARTS = ('humanity', 'science', 'humanity-attendance', 'science-attendance')


class RefreshBatch:
    def __init__(self):
        self.parts = {key: ('pending', '等待查询') for key in PARTS}
        self.lecture_job = None
        self.versions = {}
        self.started = datetime.now().strftime('%H:%M:%S')

    @property
    def finished(self):
        return all(state != 'pending' for state, _ in self.parts.values())

    def result(self, key, ok, detail):
        if key in self.parts and self.parts[key][0] == 'pending':
            self.parts[key] = ('ok' if ok else 'failed', detail)

    def summary(self):
        count = sum(state != 'pending' for state, _ in self.parts.values())
        failed = sum(state == 'failed' for state, _ in self.parts.values())
        title = ('刷新完成' if not failed else '刷新结束，部分项目未更新') if self.finished else '正在刷新'
        lines = [f'{title} · {count}/{len(PARTS)} 项 · 本轮 {self.started}']
        names = {'ok': '已更新', 'failed': '未更新', 'pending': '等待中'}
        lines.extend(f'{PARTS[key]}：{names[state]} · {detail}' for key, (state, detail) in self.parts.items())
        return '\n'.join(lines)


def read_iclass_overview(account, date, client_factory=None):
    from .iclass import IClass
    client = (client_factory or IClass)(**account)
    results = {}
    try:
        client.login()
    except Exception as exc:
        return {key: {'ok': False, 'error': str(exc)} for key in ('today', 'enrollment')}
    for key, function in (('today', lambda: client.query(date)), ('enrollment', client.my_courses)):
        try: results[key] = {'ok': True, 'value': function()}
        except Exception as exc: results[key] = {'ok': False, 'error': str(exc)}
    return results
