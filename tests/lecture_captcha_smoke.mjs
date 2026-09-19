// Exercises the real OCR subprocess from an unrelated cwd, plus manual fallback.
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {chromium} from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import {browserLaunchOptions} from '../adapters/browser_channel.mjs';
import {ensureAuthenticated} from '../vendor/ucas-humanity-lecture-bot/dist/src/login.js';
const root=fileURLToPath(new URL('../',import.meta.url));
const python=process.env.UCAS_PYTHON || join(root,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
const temporary=mkdtempSync(join(tmpdir(),'ucas captcha cwd '));
const original=process.cwd();
process.chdir(temporary);
const {solveCaptcha}=await import(pathToFileURL(join(root,'vendor/ucas-humanity-lecture-bot/dist/src/captcha.js')).href+'?cwd-test');
const browser=await chromium.launch({...browserLaunchOptions(),headless:true});
try {
 const context=await browser.newContext();
 await context.route('**/*',route=>route.abort());
 const page=await context.newPage();
 await page.setContent('<input id="certCode1"><img id="code">');
 await page.evaluate(()=>{
  const canvas=document.createElement('canvas');canvas.width=180;canvas.height=65;
  const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,180,65);ctx.font='44px Arial';ctx.fillStyle='black';ctx.fillText('1234',12,50);
  document.querySelector('#code').src=canvas.toDataURL();
 });
 await page.locator('#code').evaluate(img=>img.decode());
 const logs=[];
 const result=await solveCaptcha(page,{enabled:true,pythonExecutable:python},{info:(event,data)=>logs.push({event,...data})});
 assert.equal(result,'1234');assert.equal(await page.locator('#certCode1').inputValue(),'1234');
 assert(!JSON.stringify(logs).includes('1234'),'Do not log the recognized code');
 assert(!existsSync(join(temporary,'.cache')),'Do not write samples under arbitrary cwd');
 await context.close();
 const manual=await browser.newContext();let submitted=0;
 await manual.route('**/*',async route=>{
  const url=new URL(route.request().url());
  assert(['xkcts.ucas.ac.cn','sep.ucas.ac.cn'].includes(url.hostname));
  if(url.pathname==='/sepCard/card')return route.fulfill({contentType:'text/html; charset=utf-8',body:'<main>Fixture portal without application access</main>'});
  await route.fulfill({contentType:'text/html; charset=utf-8',body:`<input id="userName1"><input id="pwd1"><input id="certCode1"><img id="code" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='100' height='40'%3E%3C/svg%3E"><button id="sb1" onclick="location.href='https://sep.ucas.ac.cn/sepCard/card'">登录</button>`});
 });
 const p=await manual.newPage();let requested=false;
 const logger={info:()=>{},warn:event=>{
  if(event==='auth.manual-captcha-required') {
   requested=true;
   // Stand in for the person clicking login; do not navigate to any school server.
   p.locator('#certCode1').fill('fixture').then(()=>{submitted++;return p.locator('#sb1').click();}).catch(()=>{});
  }
 }};
 // The downstream missing-portal error proves fallback left the login form.
 await assert.rejects(ensureAuthenticated(p,{username:'fixture',password:'fixture',loginUrl:'https://sep.ucas.ac.cn/',humanityLectureUrl:'https://xkcts.ucas.ac.cn:8443/subject/lecture',headless:false,captcha:{enabled:false,maxAttempts:1,pythonExecutable:python}},logger),/SEP .*权限/);
 assert(requested);assert.equal(submitted,1);
 await manual.close();
 console.log('OCR subprocess with Chinese/space path and arbitrary cwd; manual verification fallback: PASS');
}finally{await browser.close();process.chdir(original);rmSync(temporary,{recursive:true,force:true});}
