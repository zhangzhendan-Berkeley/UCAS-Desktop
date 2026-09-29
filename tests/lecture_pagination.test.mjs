import test from 'node:test';
import assert from 'node:assert/strict';
import {collectSchedule,beijingDate} from '../adapters/lecture_pagination.mjs';
const row=(date,title=date)=>({title,time:date+' 09:00-11:00',start:date+' 09:00:00',location:'fixture'});
const today='2026-09-19';
function source(pages){let index=0;return {read:async()=>({rows:pages[index],hasNext:index<pages.length-1}),advance:async()=>{index++;},index:()=>index};}
test('reaches today on page two and stops only on a previous date, deduplicating page overlap',async()=>{
 const s=source([[row('2026-09-21')],[row('2026-09-21'),row(today)],[row(today),row('2026-09-18')],[row('2026-09-17')]]);
 const r=await collectSchedule(s.read,s.advance,{today});
 assert.equal(r.pages,3);assert.equal(s.index(),2);assert.equal(r.stopReason,'before-today');assert.deepEqual(r.rows.map(x=>x.title),['2026-09-21',today]);
});
test('last page and no upcoming lectures are complete results',async()=>{
 for(const pages of [[[],],[ [row('2026-09-18')] ],[[row(today)]]]) {
  const s=source(pages);const r=await collectSchedule(s.read,s.advance,{today});assert.equal(r.complete,true);
 }
});
test('out-of-order data scans remaining pages instead of stopping at past rows',async()=>{
 const s=source([[row('2026-09-18'),row('2026-09-21')],[row(today)]]);
 const r=await collectSchedule(s.read,s.advance,{today});assert.equal(r.pages,2);assert.equal(r.rows.length,2);
});
test('unknown dates, repeated pages and page limits fail instead of claiming complete',async()=>{
 let s=source([[{title:'unknown',time:'待定'}]]);await assert.rejects(collectSchedule(s.read,s.advance,{today}),/日期/);
 s=source([[row(today)],[row(today)]]);await assert.rejects(collectSchedule(s.read,s.advance,{today}),/重复/);
 s=source([[row(today)],[row('2026-09-18')]]);await assert.rejects(collectSchedule(s.read,s.advance,{today,maxPages:1}),/上限/);
});
test('cutoff is Beijing midnight even if machine uses UTC',()=>{
 assert.equal(beijingDate(new Date('2026-09-18T16:01:00Z')),today);
});


test('known row before a new row does not truncate the page; fully known next page stops', async()=>{
 const old=row('2026-09-25','old'), fresh=row('2026-09-24','new'), boundary=row('2026-09-23','boundary');
 const s=source([[old,fresh],[boundary],[row('2026-09-22','hidden')]]);
 const r=await collectSchedule(s.read,s.advance,{today,knownKeys:new Set(['old','boundary']),rowKey:r=>r.title});
 assert.equal(r.pages,2);assert.equal(r.stopReason,'known-page');assert.equal(r.complete,false);
 assert.deepEqual(r.rows.map(x=>x.title),['old','new','boundary']);
});

test('empty history establishes a full baseline and optional boundary does not affect full refresh', async()=>{
 for(const knownKeys of [null,new Set()]) {
  const s=source([[row('2026-09-25')],[row('2026-09-24')],[row('2026-09-18')]]);
  const r=await collectSchedule(s.read,s.advance,{today,knownKeys});assert.equal(r.pages,3);assert.equal(r.complete,true);
 }
});
