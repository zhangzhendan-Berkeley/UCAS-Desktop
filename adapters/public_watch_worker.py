"""Anonymous monitoring continues while one existing selection executor waits for login."""
import json
from pathlib import Path
import re
import sys
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
import requests
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ucasdesk.public_watch import Watch, query_counts


def run(config):
    codes = list(dict.fromkeys(config['codes']))
    term = str(config.get('term', '')).strip()
    if not term or not codes or any(not re.fullmatch(r'[A-Za-z0-9-]{8,30}', c) for c in codes):
        raise ValueError('请填写学期 termId 与完整课程编码')
    interval = max(30, int(config.get('interval', 60)))
    fallback = max(0, int(config.get('fallback', 3600)))
    if fallback: fallback = max(600, fallback)
    state = Watch(codes, bool(config.get('initial')), fallback)
    future = None; errors = 0
    print('实验性公开守课：未在开放选课系统实测。修改学期或课程前必须停止任务并重新启动。', flush=True)
    def execute(code):
        outcome = 'unknown'
        child_config = config | {'codes': [code], 'rounds': 1, 'start_at': None, 'report_outcome': True}
        with subprocess.Popen([sys.executable, str(ROOT / 'adapters/selection_worker.py')],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8') as child:
            child.stdin.write(json.dumps(child_config)); child.stdin.close()
            for line in child.stdout:
                print(line, end='', flush=True)
                try: event = json.loads(line)
                except ValueError: continue
                if isinstance(event, dict) and event.get('event') == 'selection.outcome' and event.get('id') == code:
                    outcome = event.get('outcome', 'unknown')
            status = child.wait()
        return outcome if status in (0, 1) else 'unknown'
    with requests.Session() as session, ThreadPoolExecutor(max_workers=1) as executor:
        while len(state.blocked) < len(codes):
            for code in codes:
                if code in state.blocked: continue
                # Never retain any public endpoint cookie as a login/session dependency.
                session.cookies.clear()
                try:
                    count, capacity = query_counts(session, term, code)
                    state.observe(code, count, capacity, time.monotonic()); errors = 0
                    print(f'{code}：公开已选 {count} / {capacity}（不代表本人可选）', flush=True)
                except Exception as exc:
                    errors = min(errors + 1, 5)
                    print(f'{code}：公开查询失败（{type(exc).__name__}），保留上次有效基线并退避。', flush=True)
                if future is not None and future.done():
                    active = state.running
                    try: outcome = future.result()
                    except Exception: outcome = 'unknown'
                    state.finish(active, outcome); future = None
                    print(f'{active}：核验结果 {outcome}', flush=True)
                next_code = state.take()
                if next_code:
                    if config.get('watch_execute'):
                        print(f'{next_code}：触发个人选课核验；若需验证码请处理浏览器，公开监控继续。', flush=True)
                        future = executor.submit(execute, next_code)
                    else:
                        print(f'{next_code}：仅监控信号，未登录、未提交。', flush=True)
                        state.finish(next_code, 'unavailable')
                time.sleep(min(1800, interval * 2 ** errors))
    return 0


if __name__ == '__main__':
    try: sys.exit(run(json.load(sys.stdin)))
    except Exception as exc:
        print(f'公开守课停止：{type(exc).__name__}: {exc}', flush=True); sys.exit(1)
