import {createHash} from 'node:crypto';
import {existsSync, mkdirSync, readFileSync, writeFileSync, renameSync} from 'node:fs';
import {join, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import {loadConfig} from '../vendor/ucas-humanity-lecture-bot/dist/src/config.js';
import {Logger} from '../vendor/ucas-humanity-lecture-bot/dist/src/log.js';
import {ensureAuthenticated} from '../vendor/ucas-humanity-lecture-bot/dist/src/login.js';
import {backgroundArgs, backgroundSep, revealSep} from '../vendor/ucas-humanity-lecture-bot/dist/src/background.js';
import {browserLaunchOptions} from './browser_channel.mjs';
import {mountEvaluation} from './evaluation_page.mjs';

let browser;
try {
  let input=''; for await (const chunk of process.stdin) input+=chunk;
  const p=JSON.parse(input);
  if (!['teacher','course'].includes(p.kind)) throw new Error('请选择教师评估或课程评估。');
  const root=dirname(dirname(fileURLToPath(import.meta.url)));
  const id=createHash('sha256').update(p.username).digest('hex').slice(0,16);
  const dir=join(root,'data','evaluation',id); mkdirSync(dir,{recursive:true});
  const state=join(dir,'browser-state.json'), templatesPath=join(dir,'templates.json');
  const oldState=join(root,'data','lecture',id,'browser-state.json');
  process.env.UCAS_USERNAME=p.username; process.env.UCAS_PASSWORD=p.password;
  process.env.UCAS_STORAGE_STATE=state;
  const configPath=join(dir,'config.json');
  writeFileSync(configPath,JSON.stringify({runtime:{mode:'single',dryRun:true,headless:false},captcha:{enabled:false}}));
  const config=loadConfig(['--config',configPath]);
  browser=await chromium.launch({...browserLaunchOptions(),args:backgroundArgs,headless:false});
  const context=await browser.newContext({storageState:existsSync(state)?state:existsSync(oldState)?oldState:undefined});
  const page=await context.newPage(); await backgroundSep(page,false);
  await ensureAuthenticated(page,config,new Logger('info'));
  await context.storageState({path:state});
  const findEntry=async kind=>{
    const links=await page.locator('a[href]').evaluateAll(els=>els.map(e=>({text:e.textContent.trim(),href:e.href})));
    return links.find(l=>{try {const u=new URL(l.href);return u.origin==='https://xkcts.ucas.ac.cn:8443' && u.pathname.startsWith('/evaluate/'+kind+'/');}catch{return false;}});
  };
  // The SEP menu labels the evaluation entry with the semester, not “课程评估”.
  // Discover its actual URL; never hard-code the current term id or use Program10.
  let target=await findEntry(p.kind);
  if(!target && p.kind==='teacher') {
    const courses=await findEntry('course');
    if(courses) {await page.goto(courses.href,{waitUntil:'domcontentloaded'});target=await findEntry('teacher');}
  }
  if (!target) throw new Error('当前学校页面未找到对应评估入口，可能尚未开放或页面已改版；没有填写或提交评价。');
  let templates=existsSync(templatesPath)?JSON.parse(readFileSync(templatesPath,'utf8')):{};
  await context.exposeBinding('ucasSaveEvaluation',async ({frame},data)=>{
    const u=new URL(frame.url());
    if(u.origin!=='https://xkcts.ucas.ac.cn:8443' || !['teacher','course'].includes(data.kind) || !u.pathname.toLowerCase().startsWith('/evaluate/evaluate'+data.kind+'/')) throw new Error('Invalid evaluation page');
    if(!data.answers || typeof data.answers!=='object' || JSON.stringify(data.answers).length>100000) throw new Error('Invalid answers');
    templates={...templates,...data.answers};
    writeFileSync(templatesPath+'.tmp',JSON.stringify(templates,null,2)); renameSync(templatesPath+'.tmp',templatesPath);
    console.log('评教模板已保存在本机；未记录验证码或提交评价。');
  });
  const attach=async frame=>{
    if(p.audit || frame!==frame.page().mainFrame()) return;
    try {await frame.waitForLoadState('domcontentloaded'); await frame.evaluate(mountEvaluation,{templates,batch:p.batch===true});}
    catch(e){if(!frame.page().isClosed() && !String(e.message).includes('context was destroyed')) console.log('评教辅助面板暂未加载，可刷新页面重试。');}
  };
  await page.goto(target.href,{waitUntil:'domcontentloaded'});
  if(new URL(page.url()).origin!=='https://xkcts.ucas.ac.cn:8443' || !new URL(page.url()).pathname.startsWith('/evaluate/'+p.kind)) throw new Error('评估入口未进入预期列表；请重试登录。');
  const count=await page.locator('a,button,input[type=button]').evaluateAll(els=>els.filter(e=>(e.value||e.textContent).trim()==='评估').length);
  console.log(JSON.stringify({event:'evaluation.list',kind:p.kind,pendingOnPage:count}));
  if(p.audit) console.log('只读检查完成；没有打开问卷或提交评价。');
  else {
    // Inspect the list before batch navigation can open the first questionnaire.
    context.on('page',child=>child.on('framenavigated',attach));
    page.on('framenavigated',attach);
    await attach(page.mainFrame()); await revealSep(page);
    console.log('评教窗口已打开。首次填好问卷后点击“记住本页答案”；以后自动填入匹配题目。请核对并手动完成验证码和学校保存按钮。关闭所有评教窗口即可结束任务。');
    await new Promise(resolve=>{context.on('close',resolve); context.on('page',child=>child.on('close',()=>{if(!context.pages().length) resolve();})); page.on('close',()=>{if(!context.pages().length) resolve();});});
  }
} catch(e) {
  console.error('评教助手未完成：'+String(e.message).replace(/(password|token|ticket|sessionid)=\S+/gi,'$1=[REDACTED]')); process.exitCode=1;
} finally {await browser?.close();}
