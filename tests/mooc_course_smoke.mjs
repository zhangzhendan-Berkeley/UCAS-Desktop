import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {browserLaunchOptions} from '../adapters/browser_channel.mjs';
import {CHAPTERS,findCourse,courseScope,chapterInfo,openChapter,waitForCourse} from '../adapters/mooc_course.mjs';
const require=createRequire(new URL('../vendor/mooc-english/package.json',import.meta.url));
const {chromium}=require('playwright');
const browser=await chromium.launch({...browserLaunchOptions(),headless:true});
try {
 for(const modern of [false,true])for(const embedded of [false,true]) {
  const context=await browser.newContext();await context.route('**/*',r=>r.abort());
  const page=await context.newPage();
  const row=(id,title,remaining)=>modern?`<div class="posCatalog_select" id="cur${id}"><span class="posCatalog_name" onclick="window.clicked='${id}'">${title}</span><input class="jobUnfinishCount" value="${remaining}"></div>`:`<div class="ncells"><h4 id="${id}"><span onclick="window.clicked='${id}'">${title}</span></h4><input class="jobUnfinishCount" value="${remaining}"></div>`;
  const html='<div id="coursetree">'+row('1','Unit introduction',3)+row('2','Quiz 1',1)+row('3','Finished',0)+'</div><iframe id="iframe"></iframe>';
  if(embedded){await page.setContent('<iframe id="learning"></iframe>');await page.frames()[1].setContent(html);}else await page.setContent(html);
  const found=await findCourse(context);assert(found);assert.equal(found.frame!==page.mainFrame(),embedded);
  const selected=courseScope(found);const cells=selected.locator(CHAPTERS);assert.equal(await cells.count(),3);
  const info=await chapterInfo(cells.first(),0);assert.equal(info.remaining,3);assert.equal(info.manual,false);
  await openChapter(info);assert.equal(await found.frame.evaluate(()=>window.clicked),'1');
  assert.equal((await chapterInfo(cells.nth(1),1)).manual,true);assert.equal((await chapterInfo(cells.nth(2),2)).remaining,0);
  assert.equal(selected.request,page.request);assert(selected.frames().includes(found.frame));
  const handler=()=>{};selected.on('response',handler);selected.off('response',handler);
  await context.close();
 }
 const context=await browser.newContext();await context.route('**/*',r=>r.abort());await context.newPage();
 await assert.rejects(waitForCourse(context,{timeout:30,interval:10,report:()=>{}}),/未识别/);
 await context.close();
 console.log('MOOC legacy/new chapter DOM, embedded frames, task counts, navigation and diagnostics: PASS');
}finally{await browser.close();}
