"""Validate session-expiry evidence against actual DOM; all site requests are blocked."""
from pathlib import Path
import os
import sys
from urllib.parse import quote
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucasdesk.core import browser_options, browser_driver, driver_service, child_env
from ucasdesk.selection_safety import login_required

for key in ('NO_PROXY','no_proxy'): os.environ[key]=child_env()[key]
options=browser_options();options.add_argument('--headless=new')
driver=browser_driver(options,driver_service(Path(__file__).resolve().parents[1]/'logs/selection-session-test.log'))
driver.execute_cdp_cmd('Network.enable',{})
driver.execute_cdp_cmd('Network.setBlockedURLs',{'urls':['http://*','https://*']})

class Fixture:
    current_url='https://xkgo.ucas.ac.cn:3000/courseManage/main'
    def execute_script(self,*args):return driver.execute_script(*args)

fixture=Fixture()
try:
    cases=[
        ('<input id="userName1"><input id="pwd1" type="password">',True),
        ('<input id="userName1" type="hidden"><input id="pwd1" type="hidden">',False),
        ('<p>遇到问题时请重新登录</p><input id="courseCode">',False),
        ('<div class="alert-error">会话已过期，请重新登录</div>',True),
        ('<div id="messageBoxError" style="display:none">请重新登录</div>',False),
        ('<div class="alert-danger">课程已满</div>',False),
    ]
    for html,expected in cases:
        driver.get('data:text/html;charset=utf-8,'+quote(html))
        assert login_required(fixture)==expected,(html,expected)
    fixture.current_url='https://example.org/login'
    driver.get('data:text/html,<input id="userName1"><input id="pwd1">')
    assert not login_required(fixture)
    print('Selection expiry DOM: visible official login only, hidden/help text ignored: PASS')
finally:
    driver.quit()
