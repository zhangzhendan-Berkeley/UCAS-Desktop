import assert from 'node:assert/strict';
import {chromium} from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import {browserLaunchOptions} from '../adapters/browser_channel.mjs';
import {readUpcomingSchedule} from '../adapters/lecture_pagination.mjs';
const browser=await chromium.launch({...browserLaunchOptions(),headless:true});
try {
 for(const path of ['lecture','humanityLecture']) {
  const context=await browser.newContext(), requests=[];
  await context.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());
   assert.equal(url.hostname,'xkcts.ucas.ac.cn');assert.equal(url.pathname,'/subject/'+path);
   const page=Number(new URLSearchParams(request.postData()||'').get('pageNum')||1);
   requests.push(page);assert(page<=3,'Must stop at past boundary before page four');
   const date=['2026-09-21','2026-09-19','2026-09-18'][page-1];
   await route.fulfill({contentType:'text/html; charset=utf-8',body:`<form method="post" action="/subject/${path}" id="pager"><input name="pageNum" value="${page}"></form>
    <table><tr><th>讲座名称</th><th>讲座地点</th><th>讲座时间</th></tr><tr><td>fixture ${page}</td><td>雁栖湖</td><td>${date} 09:00-11:00</td></tr></table>
    <div class="pagination"><div>共100项, 当前页${page}/8</div><a href="#" onclick="document.querySelector('[name=pageNum]').value=${page+1};document.querySelector('#pager').submit();return false">下一页</a></div>`});
  });
  const page=await context.newPage();await page.goto('https://xkcts.ucas.ac.cn:8443/subject/'+path);
  const result=await readUpcomingSchedule(page,null,{today:'2026-09-19'});
  assert.deepEqual(requests,[1,2,3]);assert.equal(result.rows.length,2);assert.equal(result.pages,3);
  await page.setContent('<table><tr><th>讲座名称</th><th>讲座时间</th></tr><tr><td>fixture</td><td>2026-09-19 09:00-11:00</td></tr></table><div class="pagination">当前页1/2<a href="#">下一页</a></div>');
  await assert.rejects(readUpcomingSchedule(page,null,{today:'2026-09-19',pageTimeoutMs:600}),/超时/);
  await context.close();
 }
 console.log('Humanity/science POST pagination, today cutoff and stuck-page detection: PASS');
}finally{await browser.close();}
