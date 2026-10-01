// All requests intercepted. No school account or submissions are used.
import assert from 'node:assert/strict';
import {chromium} from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import {browserLaunchOptions} from '../adapters/browser_channel.mjs';
import {mountEvaluation} from '../adapters/evaluation_page.mjs';

const browser=await chromium.launch({...browserLaunchOptions(),headless:true});
try {
  const context=await browser.newContext();
  const form=`<form onsubmit="window.submitted=true;return false"><table><tr><td>1.1</td><td>课堂说明清晰</td>
    <td><input type=radio name=item_1 value=5></td><td><input type=radio name=item_1 value=4></td></tr>
    <tr><td>修读原因</td><td><label><input type=checkbox name=reason value="">兴趣</label><label><input type=checkbox name=reason value="">时间</label></td></tr></table>
    <p>对课程的建议</p><div><textarea name=advice maxlength=200></textarea></div>
    <textarea style="display:none" name=secret>hidden answer</textarea>
    <input id=adminValidateCode value=ABCD><button type=submit>保存</button></form>`;
  await context.route('**/*',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:form}));
  let templates={}, saves=0;
  await context.exposeBinding('ucasSaveEvaluation',(_source,data)=>{templates={...templates,...data.answers};saves++;});
  const page=await context.newPage();
  const open=async(kind='Course',options={})=>{await page.goto(`https://xkcts.ucas.ac.cn:8443/evaluate/evaluate${kind}/term/fixture/0`);await page.evaluate(mountEvaluation,{templates,...options});};
  await open();
  assert.equal(await page.locator('input:checked').count(),0,'no invented default ratings');
  await page.locator('input[name=item_1][value="4"]').check();
  await page.locator('input[name=reason]').first().check();
  await page.locator('textarea[name=advice]').fill('测试：这里是用户自己撰写的意见和建议。');
  await page.getByRole('button',{name:'记住本页答案',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#ucas-desktop-evaluation').textContent.includes('已在本机记住'));
  assert.equal(saves,1); assert.equal(Object.keys(templates).length,3);
  assert(!JSON.stringify(templates).includes('ABCD'));assert(!JSON.stringify(templates).includes('hidden answer'));
  await open();
  assert(await page.locator('input[name=item_1][value="4"]').isChecked());
  assert(await page.locator('input[name=reason]').first().isChecked());
  assert((await page.locator('textarea[name=advice]').inputValue()).includes('用户自己'));
  assert.equal(await page.evaluate(()=>Boolean(window.submitted)),false);
  await page.locator('textarea[name=advice]').fill('此课程专属的新意见');
  await page.getByRole('button',{name:'按模板填写空白项',exact:true}).click();
  assert.equal(await page.locator('textarea[name=advice]').inputValue(),'此课程专属的新意见');
  await open('Teacher');
  assert.equal(await page.locator('input:checked').count(),0,'separate teacher/course templates');
  await page.goto('https://xkcts.ucas.ac.cn:8443/evaluate/evaluateCourse/term/fixture/0');
  await page.locator('tr').first().locator('td').nth(1).evaluate(e=>e.textContent='不同的问卷问题');
  await page.evaluate(mountEvaluation,{templates});
  assert.equal(await page.locator('input[name=item_1]:checked').count(),0,'changed question is not filled by field id');
  await page.goto('https://example.org/evaluate/evaluateCourse/term/fixture/0');
  await page.evaluate(mountEvaluation,{templates});
  assert.equal(await page.locator('#ucas-desktop-evaluation').count(),0,'official origin only');
  await page.goto('https://xkcts.ucas.ac.cn:8443/evaluate/course/term');
  await page.setContent('<a href="#" onclick="window.modified=true">修改评估</a><a href="#" onclick="window.nextOpened=true">评估</a>');
  await page.evaluate(mountEvaluation,{batch:true});
  assert.equal(await page.evaluate(()=>Boolean(window.modified)),false);
  assert.equal(await page.evaluate(()=>Boolean(window.nextOpened)),true);
  console.log('Evaluation browser checks passed: template recall, exact questions, preserved edits, no submission, official origin and pending-only navigation.');
} finally {await browser.close();}
