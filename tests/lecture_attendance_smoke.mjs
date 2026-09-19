import assert from 'node:assert/strict';
import {chromium} from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import {browserLaunchOptions} from '../adapters/browser_channel.mjs';
import {readAttendance,attendanceHours} from '../adapters/lecture_records.mjs';
assert.equal(attendanceHours({total:3,valid:2},[{valid:true,hours:'3'},{valid:false,hours:'2'},{valid:true,hours:'2'}]),5);
assert.throws(()=>attendanceHours({total:3,valid:2},[{valid:true,hours:'3'}]));
assert.throws(()=>attendanceHours({total:1,valid:1},[{valid:true,hours:''}]));
assert.throws(()=>attendanceHours({total:1,valid:1},[{valid:null,hours:'2'}]));
const browser=await chromium.launch({...browserLaunchOptions(),headless:true});
try {
 for(const kind of ['student','humanityStudent']) {
  const context=await browser.newContext();let visits=[];
  await context.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());assert.equal(url.hostname,'xkcts.ucas.ac.cn');assert.equal(url.pathname,'/subject/'+kind);
   const p=Number(new URLSearchParams(request.postData()||'').get('pageNum')||1);visits.push(p);
   const valid=kind==='student';
   await route.fulfill({contentType:'text/html; charset=utf-8',body:`累计听讲座 2 次，其中有效 ${valid?2:0} 次
    <form method="post"><input name="pageNum" value="${p}" id="num"></form>
    <table><tr><th>讲座名称</th><th>学时</th><th>是否有效</th></tr>
    <tr><td>fixture ${p}</td><td>${p===1?3:2}</td><td><input type="checkbox" disabled ${valid?'checked':''}></td></tr></table>
    <div class="pagination">当前页${p}/2${p===1?`<a href="#" onclick="document.querySelector('#num').value=2;document.querySelector('form').submit();return false">下一页</a>`:''}</div>`});
  });
  const page=await context.newPage();await page.goto('https://xkcts.ucas.ac.cn:8443/subject/'+kind);
  const result=await readAttendance(page);assert.equal(result.hours,kind==='student'?5:0);assert.deepEqual(visits,[1,2]);
  await page.setContent('累计听讲座 2 次，其中有效 2 次<table><tr><th>学时</th><th>是否有效</th></tr><tr><td>3</td><td><input type="checkbox" checked></td></tr></table>');
  const partial=await readAttendance(page);assert.equal(partial.valid,2);assert.equal(partial.hours,null);
  await context.close();
 }
 console.log('Official checkbox validity, all-page hours, zero and incomplete records: PASS');
} finally {await browser.close();}
