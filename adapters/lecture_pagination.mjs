// Read-only timetable traversal. Only the site's pagination control is clicked.
import {readScienceSchedule as readBaseSchedule} from '../vendor/ucas-humanity-lecture-bot/dist/src/portal.js';

export function beijingDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
  const part = name => parts.find(p=>p.type===name).value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

export async function collectSchedule(read, advance, {today=beijingDate(), maxPages=100, progress=()=>{}}={}) {
  const rows = [], seenRows = new Set(), seenPages = new Set();
  let previousDate = null, descending = true;
  for (let pages=1; pages<=maxPages; pages++) {
    const current = await read();
    const fingerprint = JSON.stringify(current.rows);
    if (seenPages.has(fingerprint)) throw new Error('讲座翻页返回了重复页面，未确认读取完整；保留上次结果。');
    seenPages.add(fingerprint);
    let beforeToday = false;
    for (const row of current.rows) {
      if (!row.start || !/^\d{4}-\d{2}-\d{2} /.test(row.start)) throw new Error('讲座日期无法识别，不能确定翻页边界；保留上次结果。');
      const key = JSON.stringify([row.title,row.time,row.location]);
      if (seenRows.has(key)) continue;
      seenRows.add(key);
      const date = row.start.slice(0,10);
      if (previousDate && date > previousDate) descending = false;
      previousDate = date;
      if (date < today) beforeToday = true;
      else rows.push(row);
    }
    progress({pages, count:rows.length, today});
    const reason = beforeToday && descending ? 'before-today' : !current.hasNext ? 'last-page' : null;
    if (reason) return {rows, scope:'today-and-future', complete:true, pages, today, stopReason:reason};
    if (!current.rows.length) throw new Error('讲座页面为空但仍有下一页，无法确认分页状态；保留上次结果。');
    if (pages === maxPages) throw new Error('讲座查询达到翻页上限，未确认读取完整；保留上次结果。');
    await advance(current);
  }
  throw new Error('无效的讲座翻页上限。');
}

export async function paginationState(page) {
  return page.evaluate(() => {
    const roots=[...document.querySelectorAll('.pagination,.pager')].filter(e=>e.getClientRects().length);
    const controls=roots.flatMap(e=>[...e.querySelectorAll('a,button,input[type=button]')]);
    const disabled=e=>e.disabled || e.getAttribute('aria-disabled')==='true' || !!e.closest('.disabled,[aria-disabled=true]');
    let next=controls.find(e=>/^(下一页|下页|next|next page|›|»|>)$/i.test((e.textContent||e.value||e.getAttribute('aria-label')||'').trim()) && !disabled(e));
    const text=roots.map(e=>e.textContent).join(' ');
    const match=text.match(/当前页\s*(\d+)\s*\/\s*(\d+)/) || text.match(/第\s*(\d+)\s*页\s*[/／]\s*共?\s*(\d+)\s*页/);
    const current=match ? Number(match[1]) : Number(roots.map(e=>e.querySelector('.active,[aria-current=page]')?.textContent.trim()).find(Boolean)) || null;
    const total=match ? Number(match[2]) : null;
    if (!next && current && (!total || current<total)) next=controls.find(e=>e.textContent.trim()===String(current+1) && !disabled(e));
    for(const e of document.querySelectorAll('[data-ucas-next-page]')) e.removeAttribute('data-ucas-next-page');
    if(next) next.setAttribute('data-ucas-next-page','1');
    return {current,total,hasNext:!!next,missingNext:!!(total && current<total && !next)};
  });
}

export async function readUpcomingSchedule(page, logger, options={}) {
  const initial=new URL(page.url());
  if(initial.hostname!=='xkcts.ucas.ac.cn' || !['/subject/lecture','/subject/humanityLecture'].includes(initial.pathname)) throw new Error('当前不是讲座预告列表，未执行翻页。');
  const read=async()=>{
    const url=new URL(page.url());
    if(url.origin!==initial.origin || url.pathname!==initial.pathname) throw new Error('讲座翻页时会话失效或离开列表，请重新登录；保留上次结果。');
    const rows=await readScienceSchedule(page), paging=await paginationState(page);
    if(paging.missingNext) throw new Error('讲座仍有后续页，但未找到可用的下一页按钮；保留上次结果。');
    return {rows,...paging};
  };
  return collectSchedule(read, async previous=>{
    const next=page.locator('[data-ucas-next-page="1"]');
    const href=await next.getAttribute('href');
    if(href && !href.startsWith('#') && !href.startsWith('javascript:')) {
      const target=new URL(href,page.url());
      if(target.origin!==initial.origin || target.pathname!==initial.pathname) throw new Error('下一页链接离开讲座列表，已停止。');
    }
    await next.click();
    const deadline=Date.now()+(options.pageTimeoutMs ?? 15000);
    while(Date.now()<deadline) {
      await page.waitForTimeout(250);
      const url=new URL(page.url());
      if(url.origin!==initial.origin || url.pathname!==initial.pathname) throw new Error('讲座翻页时会话失效，请重新登录；保留上次结果。');
      try {
        const candidate=await read();
        if(JSON.stringify(candidate.rows)!==JSON.stringify(previous.rows) &&
          (!previous.current || !candidate.current || candidate.current===previous.current+1)) return;
      } catch(error) {
        if(/会话失效|下一页按钮/.test(error.message)) throw error;
      }
    }
    throw new Error('讲座翻页超时或页面未变化，未确认读取完整；保留上次结果。');
  }, {...options,progress:data=>logger?.info('lecture.pagination',data)});
}

// Read status from the same table as the timetable, without submitting actions.
export async function readScienceSchedule(page) {
  const rows = await readBaseSchedule(page);
  const statuses = await page.locator('table tr').evaluateAll(elements => elements.map(row => {
    const cells = [...row.querySelectorAll('td')].map(td => (td.textContent || '').replace(/\s+/g, ' ').trim());
    const headers = [...(row.closest('table')?.querySelectorAll('th') || [])].map(th => th.textContent.trim());
    const status = cells.filter((_, i) => /报名|预约|操作|状态/.test(headers[i] || '')).join(' ');
    const departmentIndex = headers.findIndex(h => /^(部门|所属部门|主办部门)$/.test(h.replace(/\s+/g, '')));
    return {department: cells[departmentIndex] || '', title: cells[headers.indexOf('讲座名称')], time: cells[headers.indexOf('讲座时间')], location: cells[headers.indexOf('讲座地点')], status, rowText: cells.join(' ')};
  }));
  return rows.map(row => {
    const matches = statuses.filter(s => s.title === row.title && s.time === row.time && s.location === row.location);
    const status = matches.length === 1 ? matches[0].status : '';
    // Only an explicit successful terminal state may authorize calendar import.
    // The portal sometimes renders action/result text together, so reject failure,
    // cancellation, expiry and capacity states before looking for a positive word.
    const negative = /未报名|未预约|报名失败|预约失败|报名截止|预约截止|报名已结束|预约已结束|不可报名|无法报名|报名中|预约中|取消报名|取消预约|退选|人数已满|预约已满|名额已满|满额/;
    const registered = !negative.test(status) && /已(?:经)?报名(?:过)?|已(?:经)?预约(?:过)?/.test(status);
    const free = /无需报名|不需报名|无需预约|免预约|免报名/.test(status);
    return {...row, department: matches.length === 1 ? matches[0].department : '', registrationText: status, rowText: matches.length === 1 ? matches[0].rowText : '', registrationStatus: registered ? 'registered' : free ? 'not-required' : 'unknown-or-unregistered'};
  });
}
