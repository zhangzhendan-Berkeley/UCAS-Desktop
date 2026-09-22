import { backgroundArgs } from '../vendor/ucas-humanity-lecture-bot/dist/src/background.js';
import { browserLaunchOptions } from './browser_channel.mjs';
import { chromium } from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import { existsSync } from 'node:fs';
import { ensureAuthenticated } from '../vendor/ucas-humanity-lecture-bot/dist/src/login.js';
import { paginationState } from './lecture_pagination.mjs';

export function parseAttendance(text) {
  const normalized = text.replace(/\s+/g, ' ');
  const found = [...normalized.matchAll(/累计听讲座\s*(\d+)\s*次[，,]?\s*其中有效\s*(\d+)\s*次/g)];
  if (found.length !== 1) throw new Error('未唯一识别学校听讲统计，保留上次结果；没有把空页面当成零次。');
  const total = Number(found[0][1]), valid = Number(found[0][2]);
  if (valid > total) throw new Error('学校听讲统计不一致，保留上次结果。');
  return { total, valid };
}

export function attendanceHours(stats, rows) {
  if(rows.length!==stats.total || rows.some(r=>typeof r.valid!=='boolean') || rows.filter(r=>r.valid).length!==stats.valid)
    throw new Error('听讲明细与学校统计不一致，暂不能计算有效学时。');
  const valid=rows.filter(r=>r.valid);
  if(valid.some(r=>!/^\d+(?:\.\d+)?$/.test(r.hours))) throw new Error('有效学时无法识别。');
  return Math.round(valid.reduce((sum,r)=>sum+Number(r.hours),0)*100)/100;
}

export async function readAttendance(page) {
  const initial=new URL(page.url());
  if(initial.hostname!=='xkcts.ucas.ac.cn' || !['/subject/student','/subject/humanityStudent'].includes(initial.pathname)) throw new Error('当前不是学校听讲记录页。');
  const stats=parseAttendance(await page.locator('body').innerText());
  const readRows=()=>page.locator('table').evaluateAll(tables=>{
    const table=tables.find(t=>[...t.querySelectorAll('th')].some(h=>h.textContent.trim()==='是否有效'));
    if(!table)throw new Error('未找到听讲明细表');
    const headers=[...table.querySelectorAll('th')].map(e=>e.textContent.trim());
    const validIndex=headers.indexOf('是否有效'), hoursIndex=headers.indexOf('学时');
    if(hoursIndex<0)throw new Error('学校明细没有学时字段');
    return [...table.querySelectorAll('tr')].map(tr=>[...tr.querySelectorAll('td')]).filter(c=>c.length===headers.length).map(c=>{
      const check=c[validIndex].querySelector('input[type=checkbox]');
      const text=c[validIndex].textContent.trim();
      return {key:JSON.stringify(c.slice(0,validIndex).map(e=>e.textContent.trim())),hours:c[hoursIndex].textContent.trim(),
        valid:check ? check.checked : ['是','有效'].includes(text) ? true : ['否','无效'].includes(text) ? false : null};
    });
  });
  try {
    const rows=[],seen=new Set();let pages=0;
    for(;pages<100;pages++) {
      const location=new URL(page.url());
      if(location.origin!==initial.origin || location.pathname!==initial.pathname)throw new Error('听讲记录翻页离开列表');
      const current=await readRows();
      for(const row of current){if(seen.has(row.key))throw new Error('听讲明细重复');seen.add(row.key);rows.push(row);}
      const paging=await paginationState(page);
      if(paging.missingNext)throw new Error('未找到听讲记录下一页');
      if(!paging.hasNext)return {...stats,hours:attendanceHours(stats,rows),hoursSource:'学校有效听讲明细学时之和',pages:pages+1};
      const next=page.locator('[data-ucas-next-page="1"]'), href=await next.getAttribute('href');
      if(href && !href.startsWith('#') && !href.startsWith('javascript:')) {
        const target=new URL(href,page.url());
        if(target.origin!==initial.origin || target.pathname!==initial.pathname)throw new Error('下一页离开听讲记录');
      }
      await next.click();
      const deadline=Date.now()+15000;let changed=false;
      while(Date.now()<deadline){
        await page.waitForTimeout(200);
        const url=new URL(page.url());
        if(url.origin!==initial.origin || url.pathname!==initial.pathname)throw new Error('听讲会话失效');
        try{if(JSON.stringify(await readRows())!==JSON.stringify(current)){changed=true;break;}}catch{}
      }
      if(!changed)throw new Error('听讲记录翻页超时');
    }
    throw new Error('听讲记录超过翻页上限');
  } catch {
    // Counts are official; a partial table must never produce a smaller hours total.
    return {...stats,hours:null,hoursWarning:'学时明细未完整读取或无法识别，请刷新后核对学校记录。'};
  }
}

export async function queryAttendance(config, logger) {
  const browser = await chromium.launch({ ...browserLaunchOptions(), args: backgroundArgs, headless: false });
  try {
    const state = process.env.UCAS_STORAGE_STATE;
    const context = await browser.newContext({ storageState: state && existsSync(state) ? state : undefined });
    const page = await context.newPage();
    // Establish the ordinary humanities session first; record pages have different headers.
    await ensureAuthenticated(page, config, logger);
    const records = {};
    for (const [kind, path] of [['humanity', 'humanityStudent'], ['science', 'student']]) {
      const url = 'https://xkcts.ucas.ac.cn:8443/subject/' + path;
      await page.goto(url, { waitUntil: 'domcontentloaded', referer: page.url() });
      await page.locator('table th').first().waitFor({ timeout: 10000 });
      if (new URL(page.url()).pathname !== '/subject/' + path) throw new Error('讲座记录会话失效，请重新登录。');
      records[kind] = { ...await readAttendance(page), url };
    }
    if (state) await context.storageState({ path: state });
    console.log(JSON.stringify({ event: 'lecture.attendance', records }));
    console.log('已读取学校有效听讲次数；未提交报名或签到。');
  } finally { await browser.close(); }
}
