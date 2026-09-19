"""Offline SEP DOM regression for the installed browser. All HTTP(S) browser requests are blocked."""
import os
import sys
from pathlib import Path
from urllib.parse import quote
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucasdesk.sep import login_sep, read_enrolled, InvalidCredentials, SEP, COURSES
from ucasdesk.core import browser_driver, browser_options, child_env, driver_service

for key in ('NO_PROXY', 'no_proxy'):
    os.environ[key] = child_env()[key]

options = browser_options()
options.add_argument('--headless=new')
log_path = Path(__file__).resolve().parents[1] / 'logs/previews/sep-webdriver.log'
log_path.parent.mkdir(parents=True, exist_ok=True)
service = driver_service(log_path, service_args=['--verbose'])
try:
    driver = browser_driver(options, service)
except Exception:
    if log_path.exists():
        print(log_path.read_text(encoding='utf-8', errors='replace')[-9000:])
    raise
driver.set_page_load_timeout(20)
driver.execute_cdp_cmd('Network.enable', {})
driver.execute_cdp_cmd('Network.setBlockedURLs', {'urls': ['http://*', 'https://*']})


class Fixture:
    def __init__(self, invalid=False): self.invalid = invalid
    def __getattr__(self, name): return getattr(driver, name)
    @property
    def current_url(self): return driver.execute_script('return window.fixtureRoute')
    def get(self, url):
        assert url == SEP, 'No external navigation in this test'
        script = "document.getElementById('loginError').textContent='账号或密码错误'" if self.invalid else "window.fixtureRoute='https://sep.ucas.ac.cn/sepCard/card'"
        driver.get('data:text/html;charset=utf-8,' + quote(f"""<script>window.fixtureRoute='https://sep.ucas.ac.cn/';window.submits=0</script>
        <input id='userName1'><input id='pwd1' type='password'><div id='loginError'></div>
        <button id='sb1' onclick="window.submits++;{script}">登录</button>"""))


try:
    fixture = Fixture()
    login_sep(fixture, {'username': 'fixture-user', 'password': 'fixture-secret'})
    assert driver.execute_script('return window.submits') == 1
    assert driver.find_element('id', 'pwd1').get_attribute('value') == 'fixture-secret'
    try:
        login_sep(Fixture(True), {'username': 'fixture-user', 'password': 'wrong-fixture'})
        raise AssertionError('Wrong password must not pass')
    except InvalidCredentials:
        assert driver.execute_script('return window.submits') == 1
    class CaptchaFixture(Fixture):
        def get(self, url):
            assert url == SEP
            driver.get('data:text/html;charset=utf-8,' + quote('''<script>
              window.fixtureRoute='https://sep.ucas.ac.cn/';window.submits=0;
              setTimeout(()=>{window.fixtureRoute='https://sep.ucas.ac.cn/sepCard/card'},1500);
              </script><input id="userName1"><input id="pwd1" type="password"><input id="certCode1">
              <div id="loginError">认证失败，验证码不正确</div>
              <button id="sb1" onclick="window.submits++">登录</button>'''))
    login_sep(CaptchaFixture(), {'username':'fixture-user','password':'fixture-secret'})
    assert driver.execute_script('return window.submits') == 0, 'Do not submit empty CAPTCHA or reject password on CAPTCHA error'
    driver.get('data:text/html;charset=utf-8,' + quote(f"""<script>window.fixtureRoute={COURSES!r}</script>
      <table><thead><tr><th>课程编码</th><th>课程名称</th></tr></thead>
      <tbody><tr><td>180086081200P1001H</td><td>离线课程</td></tr></tbody></table>"""))
    snapshot = read_enrolled(fixture)
    assert snapshot['courses'] == [{'code': '180086081200P1001H', 'name': '离线课程'}]
    assert snapshot['complete']
    print('SEP fresh login, wrong-password rejection and read-only enrolled DOM: PASS')
finally:
    driver.quit()
