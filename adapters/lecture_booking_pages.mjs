// Registration traversal: observation may stop at a known page; clicks always
// re-open the target page and pass the upstream fresh-row / campus validation.
import {extractLectureSnapshot} from '../vendor/ucas-humanity-lecture-bot/dist/src/lecture-page.js';
import {parseLectureStart} from '../vendor/ucas-humanity-lecture-bot/dist/src/time-window.js';
import {collectSchedule, paginationState, advanceLecturePage, readScienceSchedule} from './lecture_pagination.mjs';
import {lectureIdentity} from './lecture_history.mjs';

export function bookingTraversal(config, logger, knownKeys=null) {
  const pagesByLecture = new Map();
  const initial = new URL(config.humanityLectureUrl);
  if (initial.hostname !== 'xkcts.ucas.ac.cn' || !['/subject/lecture','/subject/humanityLecture'].includes(initial.pathname)) {
    throw new Error('当前不是讲座列表，未执行报名分页。');
  }
  const read = async page => {
    const url = new URL(page.url());
    if (url.origin !== initial.origin || url.pathname !== initial.pathname) throw new Error('讲座查询离开列表或会话失效。');
    const snapshot = await extractLectureSnapshot(page);
    const paging = await paginationState(page);
    if (paging.missingNext) throw new Error('讲座仍有下一页，但翻页入口不可用。');
    const schedule = await readScienceSchedule(page);
    const rows = snapshot.lectures.map(row => {
      const parsed = row.startTimeText && parseLectureStart(row.startTimeText);
      const detail = schedule.find(item => item.title === row.title && item.time === row.startTimeText && item.location === row.location) || {};
      const date = parsed ? [parsed.date.getFullYear(), parsed.date.getMonth()+1, parsed.date.getDate()].map((n,i)=>String(n).padStart(i?2:4,'0')).join('-') : null;
      return {...detail, ...row, time:row.startTimeText, start:detail.start || (date ? date+' 00:00:00' : null)};
    });
    return {...snapshot, rows, ...paging};
  };
  return {
    async readLectureSnapshot(page) {
      pagesByLecture.clear();
      let number=0, first;
      const result = await collectSchedule(async () => {
        const current = await read(page); number++;
        first ||= current;
        for (const row of current.rows) if (!pagesByLecture.has(lectureIdentity(row))) pagesByLecture.set(lectureIdentity(row),number);
        return current;
      }, previous => advanceLecturePage(page,previous,()=>read(page)), {
        knownKeys:config.scienceMode ? null : knownKeys, rowKey:lectureIdentity,
        progress:data=>logger?.info('lecture.booking-pages',data)
      });
      logger?.info('lecture.booking-boundary',{pages:result.pages,reason:result.stopReason,complete:result.complete});
      return {lectures:result.rows,quota:first.quota,pageText:first.pageText};
    },
    async beforeRegister(page, lecture) {
      const number = pagesByLecture.get(lectureIdentity(lecture));
      if (!number) throw new Error('未找到候选讲座所在页面，未提交报名。');
      await page.goto(config.humanityLectureUrl,{waitUntil:'domcontentloaded'});
      for (let index=1;index<number;index++) {
        const current = await read(page);
        if (!current.hasNext) throw new Error('报名期间讲座分页发生变化，未提交本场报名。');
        await advanceLecturePage(page,current,()=>read(page));
      }
    }
  };
}
