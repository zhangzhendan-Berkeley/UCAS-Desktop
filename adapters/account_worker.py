import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from ucasdesk.core import LOGS, DATA
from ucasdesk.enrollment import account_hash
from ucasdesk.sep import login_sep, read_enrolled, InvalidCredentials


def main(payload):
    driver = None
    try:
        options = webdriver.EdgeOptions()
        options.add_argument('--no-first-run')
        options.page_load_strategy = 'eager'
        if payload['action'] == 'courses':
            profile = DATA / 'browser-enrollment' / account_hash(payload['username'])[:16]
            options.add_argument('--user-data-dir=' + str(profile))
        service = Service(log_output=str(LOGS / 'account-driver.log'))
        service.creation_flags = 0x08000000
        # Password checks are fresh; course sync may reuse its own account-isolated session.
        driver = webdriver.Edge(options=options, service=service)
        driver.set_page_load_timeout(30)
        login_sep(driver, payload, open_courses=payload['action'] == 'courses')
        if payload['action'] == 'courses':
            print(json.dumps({'event': 'account.courses', 'snapshot': read_enrolled(driver)}, ensure_ascii=False), flush=True)
        else:
            print(json.dumps({'event': 'account.check', 'account': 'sep', 'status': 'valid', 'message': 'SEP 新登录验证成功。'}, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        known = isinstance(exc, (InvalidCredentials, RuntimeError, ValueError))
        message = str(exc) if known else 'SEP 检测未完成：浏览器、网络或页面结构异常，请查看浏览器提示后重试。'
        print(json.dumps({'event': 'account.check', 'account': 'sep',
                          'status': 'invalid' if isinstance(exc, InvalidCredentials) else 'error', 'message': message}, ensure_ascii=False), flush=True)
        return 1
    finally:
        if driver: driver.quit()


if __name__ == '__main__':
    sys.exit(main(json.load(sys.stdin)))
