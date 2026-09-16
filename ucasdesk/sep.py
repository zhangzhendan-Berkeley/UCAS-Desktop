"""Shared SEP login and read-only enrollment extraction for Selenium adapters."""
import re
import time
from urllib.parse import urlsplit, urljoin
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

SEP = 'https://sep.ucas.ac.cn/'
COURSES = 'https://xkgo.ucas.ac.cn:3000/courseManage/main'


class InvalidCredentials(RuntimeError):
    pass


def logged_in(url):
    p = urlsplit(url)
    return p.hostname == 'sep.ucas.ac.cn' and p.path.rstrip('/') in ('/sepCard/card', '/appStore', '/appStore/appIndex')


def login_sep(driver, account, open_courses=False, timeout=180):
    driver.get(SEP)
    wait = WebDriverWait(driver, 20)
    if not logged_in(driver.current_url):
        user = wait.until(EC.visibility_of_element_located((By.ID, 'userName1')))
        user.clear(); user.send_keys(account['username'])
        password = driver.find_element(By.ID, 'pwd1')
        password.clear(); password.send_keys(account['password'])
        driver.find_element(By.ID, 'sb1').click()
        print('已填入个人信息页中的 SEP 账号；如出现验证码/邮箱验证，请在浏览器完成。', flush=True)
        deadline = time.monotonic() + timeout
        while not logged_in(driver.current_url):
            # Inspect only explicit error widgets. Never log portal body/profile data.
            messages = driver.execute_script("""return [...document.querySelectorAll('#loginError,#messageBoxError,.alert-danger,.alert-error,.error')]
                .filter(e=>e.getClientRects().length).map(e=>e.textContent).join(' ');""")
            if re.search(r'(用户名|账号|用户|密码).{0,12}(错误|不正确|不存在)|认证失败|无效的(用户|密码)', messages or ''):
                raise InvalidCredentials('SEP 提示账号或密码不正确，请在个人信息页修改。')
            if time.monotonic() > deadline:
                raise RuntimeError('SEP 登录未完成，可能需要验证码或邮箱验证；未判定密码正确。')
            time.sleep(1)
    if not open_courses:
        return
    links = wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, 'a[href*="/portal/site/524/2412"]') or
                       d.find_elements(By.LINK_TEXT, '选课系统') or d.find_elements(By.LINK_TEXT, '选课'))
    href = urljoin(driver.current_url, links[0].get_attribute('href'))
    if urlsplit(href).hostname != 'sep.ucas.ac.cn':
        raise RuntimeError('选课入口不是 SEP 官方跳转，已停止。')
    if href.startswith('http:'):
        href = 'https:' + href[5:]
    # Clicking preserves the portal Referer and signed SSO flow.
    driver.execute_script("arguments[0].href=arguments[1];arguments[0].click();", links[0], href)
    def course_window(d):
        for handle in d.window_handles:
            d.switch_to.window(handle)
            p = urlsplit(d.current_url)
            if p.hostname == 'xkgo.ucas.ac.cn' and p.path.rstrip('/') == '/courseManage/main':
                return True
        return False
    wait.until(course_window)


def parse_course_tables(tables):
    """Accept enrolled-course tables only, with explicit code and name headings."""
    courses = {}
    recognized = False
    explicitly_empty = False
    for table in tables:
        headers = [re.sub(r'\s+', '', h) for h in table['headers']]
        code_index = next((i for i, h in enumerate(headers) if h in ('课程编码', '课程代码', '课程编号')), None)
        name_index = next((i for i, h in enumerate(headers) if h in ('课程名称', '课程名')), None)
        if code_index is None or name_index is None:
            continue
        recognized = True
        for cells in table['rows']:
            if len(cells) <= max(code_index, name_index):
                if any(re.search('暂无|没有|无记录|无数据', x) for x in cells):
                    explicitly_empty = True
                    continue
                if not any(cells): continue
                raise ValueError('已选课程表存在无法解析的数据行，未替换同步结果。')
            code, name = cells[code_index].strip(), cells[name_index].strip()
            if not re.fullmatch(r'[A-Za-z0-9-]{8,30}', code) or not name:
                raise ValueError('已选课程表编码或名称无法识别，未替换同步结果。')
            if code in courses and courses[code]['name'] != name:
                raise ValueError('同一课程编码对应多个名称，停止自动匹配。')
            courses[code] = {'code': code, 'name': name}
    if not recognized:
        raise ValueError('页面中未识别到已选课程表，未把空结果当成退课。')
    if not courses and not explicitly_empty:
        raise ValueError('页面尚未显示课程或明确的空列表提示，未替换已选状态。')
    return list(courses.values())


def read_enrolled(driver):
    p = urlsplit(driver.current_url)
    if p.hostname != 'xkgo.ucas.ac.cn' or p.path.rstrip('/') != '/courseManage/main':
        raise RuntimeError('当前不是选课主页，禁止把可选课程库当成已选课程。')
    WebDriverWait(driver, 15).until(lambda d: d.find_elements(By.CSS_SELECTOR, 'table'))
    data = driver.execute_script("""return {
      tables:[...document.querySelectorAll('table')].map(t=>({
        headers:[...t.querySelectorAll('thead th')].length ? [...t.querySelectorAll('thead th')].map(c=>c.textContent.trim()) : [...(t.rows[0]?.cells||[])].map(c=>c.textContent.trim()),
        rows:[...t.rows].slice(1).map(r=>[...r.cells].map(c=>c.textContent.trim()))})),
      hasMore:[...document.querySelectorAll('.pagination a,.pagination button')].some(e=>/下一页|下页|next/i.test(e.textContent) && !e.closest('.disabled') && !e.disabled),
      semester:document.querySelector('select[name*=term] option:checked,select[name*=semester] option:checked')?.textContent || ''
    };""")
    if data['hasMore']:
        raise RuntimeError('已选课程列表存在分页，当前未完整读取；请改用轻新课堂同步。')
    return {'source': 'sep', 'complete': True, 'courses': parse_course_tables(data['tables']),
            'semester': data['semester'], 'fetched_at': datetime.now().isoformat(timespec='seconds')}
