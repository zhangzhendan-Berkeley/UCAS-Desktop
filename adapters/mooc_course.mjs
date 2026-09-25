// Chapter discovery includes nested learning frames and newly opened tabs.
export const CHAPTERS = '#coursetree .ncells:has(input.jobUnfinishCount), #coursetree .posCatalog_select:has(input.jobUnfinishCount)';
export async function findCourse(context) {
  for (const page of [...context.pages()].reverse()) {
    for (const frame of page.frames()) {
      if (await frame.locator(CHAPTERS).count().catch(()=>0)) return {page,frame};
    }
  }
  return null;
}

// Upstream helpers use both frame-local DOM and page-level response events.
export function courseScope({page,frame}) {
  return new Proxy(frame,{get(target,key){
    if (['on','off','request','waitForTimeout'].includes(key)) {
      const value=page[key];return typeof value==='function'?value.bind(page):value;
    }
    if(key==='frames')return ()=>{
      const descendants=[];const walk=f=>{descendants.push(f);for(const child of f.childFrames())walk(child);};walk(frame);return descendants;
    };
    const value=target[key];return typeof value==='function'?value.bind(target):value;
  }});
}

export async function waitForCourse(context,{timeout=600000,interval=1500,report=console.log}={}) {
  const deadline=Date.now()+timeout;let nextReport=0;
  while(Date.now()<deadline) {
    if(!context.pages().length)throw new Error('慕课浏览器已关闭，请重新启动任务。');
    const found=await findCourse(context);if(found)return found;
    if(Date.now()>=nextReport){
      const frames=context.pages().flatMap(p=>p.frames());
      const trees=await Promise.all(frames.map(f=>f.locator('#coursetree').count().catch(()=>0)));
      report(`等待打开课程章节：${context.pages().length} 个标签页、${frames.length} 个页面层级；${trees.some(Boolean)?'已看到课程目录，尚未识别任务点，请点开具体章节':'还未进入学习章节，请在本次打开的浏览器中进入个人空间 → 课程 → 章节'}。`);
      nextReport=Date.now()+30000;
    }
    await new Promise(resolve=>setTimeout(resolve,interval));
  }
  throw new Error('未识别到已适配的章节任务点。请使用“仅诊断章节页面”确认是否进入课程；课程主页/登录页不会自动开始。');
}

export async function chapterInfo(cell, index) {
  const modern = await cell.locator('.posCatalog_name').count();
  const name = modern ? cell.locator('.posCatalog_name').first() : cell.locator('h4').first();
  const title = (await name.textContent()).replace(/\s+/g,' ').trim();
  const id = (modern ? await cell.getAttribute('id') : await name.getAttribute('id')) || `${index}:${title}`;
  const value=await cell.locator('input.jobUnfinishCount').inputValue();
  if (!/^\d+$/.test(value)) throw new Error('章节任务点数量无法识别，请使用诊断功能核对页面。');
  return {cell,id,title,remaining:Number(value),manual:/quiz|exam|测验|考试|作业/i.test(title),modern};
}
export async function openChapter(target) {
  const current=target.modern ? (await target.cell.getAttribute('class')||'').split(/\s+/).includes('posCatalog_active') : !!(await target.cell.locator('h4.currents').count());
  if(!current) await target.cell.locator(target.modern?'.posCatalog_name[onclick]':'h4 span[onclick]').first().click();
}
