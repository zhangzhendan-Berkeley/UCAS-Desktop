import assert from 'node:assert/strict';
import {chromium} from '../vendor/ucas-humanity-lecture-bot/node_modules/playwright/index.mjs';
import {browserLaunchOptions} from '../adapters/browser_channel.mjs';
import {backgroundArgs,backgroundSep,revealSep} from '../vendor/ucas-humanity-lecture-bot/dist/src/background.js';
const browser=await chromium.launch({...browserLaunchOptions(),headless:false,args:backgroundArgs});
try {
 const context=await browser.newContext();await context.route('**/*',r=>r.abort());
 const page=await context.newPage();await backgroundSep(page,false);
 const session=await context.newCDPSession(page);
 const state=async()=>{const {windowId}=await session.send('Browser.getWindowForTarget');return (await session.send('Browser.getWindowBounds',{windowId})).bounds.windowState;};
 await page.waitForTimeout(300);assert.equal(await state(),'minimized');
 await page.setContent('<input id="fixture"><p>offline</p>');await page.locator('#fixture').fill('background');
 await page.locator('p').screenshot();assert.equal(await state(),'minimized');
 await revealSep(page);await page.waitForTimeout(300);assert.equal(await state(),'normal');
 await backgroundSep(page,false);await page.waitForTimeout(300);assert.equal(await state(),'minimized');
 console.log('Headed SEP minimize, background DOM/screenshot, reveal and return: PASS');
}finally{await browser.close();}
