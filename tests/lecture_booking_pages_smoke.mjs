// All school URLs are intercepted; no real login, registration or network traffic.
import assert from 'node:assert/strict';
import {chromium} from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import {browserLaunchOptions} from '../adapters/browser_channel.mjs';
import {bookingTraversal} from '../adapters/lecture_booking_pages.mjs';
import {lectureIdentity} from '../adapters/lecture_history.mjs';
import {decideLectures} from '../vendor/ucas-humanity-lecture-bot/dist/src/filter.js';
import {registerLecture} from '../vendor/ucas-humanity-lecture-bot/dist/src/register.js';

const browser=await chromium.launch({...browserLaunchOptions(),headless:true});
const logger={info(){},debug(){}};
const fixture=(title,date)=>({title,startTimeText:date+' 18:30-20:30',location:'主会场：雁栖湖 - 教一楼'});
const rows=[fixture('旧讲座重新放号','2030-10-12'),fixture('新讲座排在旧讲座后','2030-10-10'),fixture('整页已见边界','2030-10-08'),fixture('科研延后开放','2030-10-06'),fixture('往期','2020-01-01')];
const pageRows=[[rows[0],rows[1]],[rows[2]],[rows[3]],[rows[4]]];
const booked=new Set(), requests=[];
try {
  const context=await browser.newContext();
  await context.exposeBinding('recordFixtureBooking',(_source,title)=>booked.add(title));
  await context.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.hostname!=='xkcts.ucas.ac.cn') return route.abort();
    const n=Number(url.searchParams.get('page')||1);requests.push(n);
    const body=pageRows[n-1].map(row=>`<tr><td>${row.title}</td><td>${row.startTimeText}</td><td>${row.location}</td><td>${booked.has(row.title)?'已预约':`<button onclick="recordFixtureBooking('${row.title}');this.textContent='已预约';alert('报名成功！')">报名</button>`}</td></tr>`).join('');
    await route.fulfill({contentType:'text/html; charset=utf-8',body:`<table><tr><th>讲座名称</th><th>讲座时间</th><th>讲座地点</th><th>操作</th></tr>${body}</table><div class="pagination">当前页 ${n} / 4 ${n<4?`<a href="?page=${n+1}">下一页</a>`:''}</div>`});
  });
  const page=await context.newPage();
  const config={humanityLectureUrl:'https://xkcts.ucas.ac.cn:8443/subject/humanityLecture'};
  const known=new Set([rows[0],rows[2]].map(lectureIdentity));
  await page.goto(config.humanityLectureUrl);
  const human=bookingTraversal(config,logger,known);
  const snapshot=await human.readLectureSnapshot(page);
  assert.deepEqual(requests,[1,2]);
  assert.deepEqual(snapshot.lectures.map(x=>x.title),rows.slice(0,3).map(x=>x.title));
  const state={terminalLectures:{[snapshot.lectures[0].id]:{state:'full'},[snapshot.lectures[2].id]:{state:'booked'}}};
  const windows=Array.from({length:7},(_,weekday)=>({weekday,ranges:[{startMinutes:0,endMinutes:1439}]}));
  const candidates=decideLectures(snapshot.lectures,state,new Set(),false,windows).filter(x=>x.action==='candidate');
  assert.equal(candidates.length,2);
  for(const {lecture} of candidates){
    await human.beforeRegister(page,lecture);
    assert.equal((await registerLecture(page,lecture,logger)).outcome,'registered');
  }
  assert.deepEqual([...booked],[rows[0].title,rows[1].title]);
  assert(!requests.includes(3),'Humanity must stop paging at the fully known page');
  // Science ignores the humanity boundary and reaches a later-opening lecture.
  requests.length=0;
  const scienceConfig={humanityLectureUrl:'https://xkcts.ucas.ac.cn:8443/subject/lecture',scienceMode:true};
  const science=bookingTraversal(scienceConfig,logger,known);
  await page.goto(scienceConfig.humanityLectureUrl);
  const all=await science.readLectureSnapshot(page);
  assert.deepEqual(requests,[1,2,3,4]);
  const target=all.lectures.find(x=>x.title===rows[3].title);
  assert(target);
  await science.beforeRegister(page,target);
  assert.equal(new URL(page.url()).searchParams.get('page'),'3');
  assert.equal((await registerLecture(page,target,logger)).outcome,'registered');
  console.log('Incremental humanity, mixed old/new rows, reopened seats, multi-booking and science pagination: PASS');
} finally {await browser.close();}
