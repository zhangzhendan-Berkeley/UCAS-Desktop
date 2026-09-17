import contextlib
from datetime import datetime
import io
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor/UCAS-COURSE-SELECTION-SCRIPT'))
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from ucasdesk.core import DATA
from ucasdesk.sep import login_sep
from ucasdesk.enrollment import account_hash
import main as upstream
from course_flow import run_course_selection, RateLimitedError, assert_not_rate_limited, open_query_page, query_course, target_checkbox, RequestPacer


class Tee(io.StringIO):
    def write(self, value):
        sys.__stdout__.write(value)
        sys.__stdout__.flush()
        return super().write(value)


def run(config):
    codes = list(dict.fromkeys(config['codes']))
    if not codes or any(not re.fullmatch(r'[A-Za-z0-9-]{8,30}', c) for c in codes):
        raise ValueError('课程编码格式不正确，请从 SEP 复制完整编码。')
    options = webdriver.EdgeOptions()
    if not config.get('username') or not config.get('password'):
        raise ValueError('请先在个人信息页保存 SEP 账号。')
    options.add_argument('--user-data-dir=' + str(DATA / 'browser-selection' / account_hash(config['username'])[:16]))
    options.add_argument('--no-first-run')
    options.page_load_strategy = 'eager'
    service = Service(log_output=str(ROOT / 'logs/edgedriver.log'))
    service.creation_flags = 0x08000000
    print('正在启动 Edge。首次使用可能需要下载匹配的驱动。', flush=True)
    driver = webdriver.Edge(options=options, service=service)
    try:
        driver.set_page_load_timeout(30)
        login_sep(driver, config, open_courses=True, timeout=600)
        if config.get('start_at'):
            start_at = datetime.fromisoformat(config['start_at'])
            print(f'登录完成，等待执行时间 {start_at}。', flush=True)
            while datetime.now() < start_at:
                time.sleep(1)
        interval = max(30, int(config.get('interval', 60)))
        rounds = max(1, min(240, int(config.get('rounds', 1))))
        pending = list(codes)
        failed = []
        for cycle in range(rounds):
            print(f'检查轮次 {cycle + 1}/{rounds}', flush=True)
            for code in list(pending):
                assert_not_rate_limited(driver)
                if upstream.course_already_selected(driver, code):
                    print(f'{code}：已在预选列表，不重复提交。', flush=True)
                    pending.remove(code)
                    continue
                if config.get('preview'):
                    pacer = RequestPacer(1)
                    open_query_page(driver, pacer)
                    query_course(driver, code, pacer)
                    box = target_checkbox(driver, code)
                    print(f'{code}：' + ('可选' if box and box.is_enabled() else '未找到、已满或不可选') + '（仅预览，未提交）', flush=True)
                    pending.remove(code)
                else:
                    capture = Tee()
                    with contextlib.redirect_stdout(capture):
                        success = run_course_selection(driver, code, poll_interval=1)
                    output = capture.getvalue()
                    if success:
                        print(json.dumps({'event': 'selection.success', 'id': code, 'title': code,
                            'semester': config.get('course_semesters', {}).get(code, '')}, ensure_ascii=False), flush=True)
                        pending.remove(code)
                    elif '已满' not in output:
                        print(f'{code}：非满员失败或结果未知，不再重试。', flush=True)
                        failed.append(code)
                        pending.remove(code)
                upstream.return_to_course_home(driver, driver.current_window_handle, interval=1)
                time.sleep(3)
            if not pending:
                break
            if cycle + 1 < rounds:
                print(f'尚有 {len(pending)} 门未选到，{interval} 秒后再检查。', flush=True)
                time.sleep(interval)
        print(f'结束：剩余未选到 {pending}；其他失败 {failed}。请在 SEP 核对预选列表并完成所需审核。', flush=True)
        return 1 if pending or failed else 0
    finally:
        driver.quit()


if __name__ == '__main__':
    try:
        sys.exit(run(json.load(sys.stdin)))
    except RateLimitedError as exc:
        print(f'已停止：{exc}', flush=True)
        sys.exit(3)
    except Exception as exc:
        print(f'选课任务停止：{type(exc).__name__}: {str(exc)[:400]}', flush=True)
        sys.exit(1)
