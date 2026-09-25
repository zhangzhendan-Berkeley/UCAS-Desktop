"""Bounded session recovery for read-only checks, never for an uncertain submission."""
from datetime import datetime, timedelta
import re
import time
from urllib.parse import urlsplit


class SessionExpired(RuntimeError):
    pass


def scheduled_start(value):
    if not value:
        return None
    result = datetime.fromisoformat(value)
    if result.tzinfo is not None:
        raise ValueError('执行时间请使用本机日期时间，不要附加时区偏移。')
    return result


def wait_until(target, clock=datetime.now, sleep=time.sleep):
    if target is None:
        return
    while True:
        remaining = (target - clock()).total_seconds()
        if remaining <= 0:
            return
        sleep(min(1, remaining))


def login_time(start):
    return start - timedelta(minutes=5) if start else None


def login_required(driver):
    """Only official hosts and visible login/error widgets are evidence of expiry."""
    if urlsplit(driver.current_url).hostname not in {'sep.ucas.ac.cn', 'xkgo.ucas.ac.cn'}:
        return False
    return driver.execute_script("""
        const visible = e => e && e.getClientRects().length &&
            getComputedStyle(e).visibility !== 'hidden';
        const user = document.querySelector('#userName1');
        const password = document.querySelector('#pwd1');
        if (visible(user) && visible(password)) return true;
        return [...document.querySelectorAll('#loginError,#messageBoxError,.alert-danger,.alert-error')]
            .some(e => visible(e) && /登录已过期|登录过期|登录超时|会话已过期|会话过期|请重新登录|尚未登录|未登录/.test(e.textContent));
    """) is True


class RecoveryBudget:
    def __init__(self, limit=2):
        self.remaining = limit

    def use(self):
        if self.remaining <= 0:
            raise SessionExpired('本任务已达到登录恢复上限，请检查登录状态后重新启动任务。')
        self.remaining -= 1


def prepare_course(driver, config, code, *, flow, already_selected, login, budget):
    """Return already-selected/available/unavailable; no submit operation is allowed here."""
    def check_session():
        flow.assert_not_rate_limited(driver)
        if login_required(driver):
            raise SessionExpired('提交前检测到登录失效。')

    for attempt in range(2):
        try:
            check_session()
            if already_selected(driver, code):
                return 'already-selected'
            pacer = flow.RequestPacer(1)
            flow.open_query_page(driver, pacer)
            check_session()
            flow.query_course(driver, code, pacer)
            check_session()
            box = flow.target_checkbox(driver, code)
            if not box:
                raise RuntimeError('没有完整匹配目标课程，未提交。')
            return 'available' if box.is_enabled() else 'unavailable'
        except flow.RateLimitedError:
            raise
        except Exception:
            # A network failure or unfamiliar page is not proof that re-login is needed.
            flow.assert_not_rate_limited(driver)
            if not login_required(driver):
                raise
            if attempt:
                raise SessionExpired('重新登录后仍无法查询目标课程，已停止；未提交。') from None
            budget.use()
            print('提交前发现登录失效，正在恢复同一浏览器会话并重新核对预选列表。', flush=True)
            login(driver, config, open_courses=True, timeout=600)


def confirmed_full(output, code):
    """Accept only the pinned upstream's terminal full/unavailable outcome, not a substring."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return False
    expected = rf'↷ 课程 {re.escape(code)} 已满(?:或不可选)?，结束本门任务'
    return re.fullmatch(expected, lines[-1]) is not None
